from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import StreamingResponse
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.argo_data import ArgoProfile, ArgoFloat, ArgoMeasurement
from ..schemas.argo_data import ArgoProfileResponse, ArgoFloatResponse, MeasurementsResponse

import asyncio
import os
import logging
import math
from typing import Tuple

BASE_DATA_HOST = "https://data-argo.ifremer.fr/"

async def _fetch_and_store_measurements(profile_id: int, db: AsyncSession) -> bool:
    """If measurements for profile are missing, attempt to fetch NetCDF from Ifremer and store minimal arrays.

    Returns True if any rows were inserted, False otherwise.
    """
    # Lazy imports to avoid hard dependency if env is not prepared
    try:
        import httpx  # type: ignore
        import tempfile
        import netCDF4  # type: ignore
        import numpy as np  # type: ignore
    except Exception as e:
        logging.warning("Measurements fetch skipped due to missing deps: %s", e)
        return False

    # Get profile info
    prof_res = await db.execute(select(ArgoProfile).where(ArgoProfile.id == profile_id).limit(1))
    prof = prof_res.scalars().first()
    if not prof:
        return False

    async def _discover_file_path() -> str | None:
        # Try to locate the NetCDF path by matching platform_number and nearest profile_date in the global index
        try:
            import httpx, gzip
            from datetime import datetime
            from ..core.config import settings
        except Exception as e:  # pragma: no cover
            logging.warning("Cannot import deps/config for index discovery: %s", e)
            return None

        base_url = str(settings.ARGO_INDEX_URL) if settings.ARGO_INDEX_URL else None
        if not base_url:
            return None
        candidates = []
        if base_url.endswith(".gz"):
            candidates = [base_url, base_url[:-3]]
        else:
            candidates = [base_url + ".gz", base_url]
        candidates += [
            "https://usgodae.org/ftp/outgoing/argo/ar_index_global_prof.txt.gz",
            "https://usgodae.org/ftp/outgoing/argo/ar_index_global_prof.txt",
            "https://data-argo.ifremer.fr/ar_index_global_prof.txt",
        ]

        timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            last_err: Exception | None = None
            raw: bytes | None = None
            for url in candidates:
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    raw = r.content
                    break
                except Exception as e:
                    last_err = e
                    continue
            if raw is None:
                logging.warning("Index discovery failed to download: %s", last_err)
                return None

        if raw[:2] == b"\x1f\x8b":
            try:
                import gzip
                raw = gzip.decompress(raw)
            except Exception:
                pass
        text = raw.decode("utf-8", errors="ignore")
        lines = text.splitlines()

        # Find best match by same platform_number and nearest date
        from datetime import datetime

        def parse_dt(val: str) -> datetime | None:
            v = (val or "").strip().replace("Z", "+00:00")
            for parser in (lambda x: datetime.fromisoformat(x),):
                try:
                    return parser(v)
                except Exception:
                    pass
            for fmt in ("%Y-%m-%d", "%Y%m%d%H%M%S", "%Y%m%d"):
                try:
                    return datetime.strptime(v, fmt)
                except Exception:
                    continue
            return None

        target_dt = prof.profile_date
        best_path: str | None = None
        best_delta: float | None = None
        for line in lines:
            if not line or line.startswith('#'):
                continue
            parts = line.split(',')
            if len(parts) < 2:
                continue
            path = parts[0].strip()
            date_str = parts[1].strip()
            # Extract platform from path segments
            segs = [p for p in path.strip('/').split('/') if p]
            candidate = None
            if len(segs) >= 2:
                candidate = segs[-2]
                if candidate.lower() in {"profiles", "dac"} and len(segs) >= 3:
                    candidate = segs[-3]
            else:
                candidate = segs[-1] if segs else None

            if not candidate or candidate != prof.platform_number:
                continue

            if target_dt is None:
                # If no date on profile, just take the first match
                best_path = path
                break
            dt = parse_dt(date_str)
            if not dt:
                continue
            delta = abs((dt - target_dt).total_seconds())
            if best_delta is None or delta < best_delta:
                best_delta = delta
                best_path = path

        if best_path:
            # Persist so future calls don't need discovery
            try:
                await db.execute(
                    update(ArgoProfile).where(ArgoProfile.id == profile_id).values(file_path=best_path)
                )
                await db.commit()
            except Exception:
                pass
        return best_path

    def _normalize_rel_path(p: str) -> str:
        p2 = p.lstrip("/")
        # If the path doesn't already start with 'dac/', add it (Ifremer layout)
        if not p2.startswith("dac/"):
            p2 = "dac/" + p2
        return p2

    fp = (getattr(prof, "file_path", None) or "").strip() or None
    if not fp:
        fp = await _discover_file_path()
        if not fp:
            logging.info("Profile %s: could not discover file_path from index", profile_id)
            return False
    # Normalize and persist if needed
    file_path = fp
    if not file_path.startswith("http"):
        normalized = _normalize_rel_path(file_path)
        if normalized != file_path:
            try:
                await db.execute(update(ArgoProfile).where(ArgoProfile.id == profile_id).values(file_path=normalized))
                await db.commit()
            except Exception:
                pass
            file_path = normalized
    url = file_path if file_path.startswith("http") else (BASE_DATA_HOST + file_path.lstrip("/"))

    # Download file
    try:
        # httpx requires specifying all four timeouts when not using a default
        timeout = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(url)
            r.raise_for_status()
            content = r.content
    except Exception as e:
        logging.warning("Failed to download NetCDF for profile %s: %s", profile_id, e)
        return False

    # Write to temp file for netCDF4 to open
    try:
        # On Windows, NamedTemporaryFile(delete=True) cannot be reopened by another process.
        # Use delete=False and remove manually after netCDF4 is done.
        fd, tmp_path = tempfile.mkstemp(suffix=".nc")
        try:
            with os.fdopen(fd, "wb") as tf:
                tf.write(content)
                tf.flush()
            ds = netCDF4.Dataset(tmp_path, mode='r')
            try:
                # Variables can be [n_prof, n_levels] or [n_levels]
                def pick_var(name_main: str, name_alt: str | None = None):
                    for nm in [name_main, name_alt]:
                        if nm and nm in ds.variables:
                            return ds.variables[nm]
                    return None

                v_pres = pick_var('PRES_ADJUSTED', 'PRES') or pick_var('PRESSURE', None)
                v_temp = pick_var('TEMP_ADJUSTED', 'TEMP')
                v_psal = pick_var('PSAL_ADJUSTED', 'PSAL')
                if v_pres is None and v_temp is None and v_psal is None:
                    return False

                def read_first_profile(var) -> np.ndarray | None:
                    if var is None:
                        return None
                    data = var[:]
                    arr = np.array(data)
                    # Handle masked arrays
                    if hasattr(data, 'mask'):
                        arr = np.array(data.filled(np.nan))
                    if arr.ndim == 1:
                        return arr
                    if arr.ndim >= 2:
                        # choose the first profile with finite values if possible
                        for i in range(arr.shape[0]):
                            row = arr[i]
                            if np.isfinite(row).sum() > 0:
                                return row
                        return arr[0]
                    return None

                pres = read_first_profile(v_pres)
                temp = read_first_profile(v_temp)
                psal = read_first_profile(v_psal)

                # Choose depth from pressure (approx 1 dbar ~ 1 m). If both depth and pressure exist pick depth variable if present.
                depth = pres.copy() if pres is not None else None

                # Sanitize lengths to min common
                arrays = [a for a in [depth, temp, psal] if a is not None]
                if not arrays:
                    return False
                n = min(int(a.shape[0]) for a in arrays)
                depth_l = depth[:n].tolist() if depth is not None else [None] * n
                temp_l = temp[:n].tolist() if temp is not None else [None] * n
                psal_l = psal[:n].tolist() if psal is not None else [None] * n

                # Build rows skipping all-None entries and coercing non-finite to None
                def _as_float_or_none(x):
                    try:
                        v = float(x)
                        return v if np.isfinite(v) else None
                    except Exception:
                        return None

                payload = []
                for i in range(n):
                    d = _as_float_or_none(depth_l[i]) if i < len(depth_l) else None
                    t = _as_float_or_none(temp_l[i]) if i < len(temp_l) else None
                    s = _as_float_or_none(psal_l[i]) if i < len(psal_l) else None
                    if d is None and t is None and s is None:
                        continue
                    payload.append({
                        'profile_id': profile_id,
                        'depth': d,
                        'pressure': d,  # store same as depth approx
                        'temperature': t,
                        'salinity': s,
                        'measurement_level': i,
                        'created_at': None,
                    })

                if not payload:
                    return False

                await db.execute(ArgoMeasurement.__table__.insert(), payload)
                await db.commit()
                logging.info("Profile %s: inserted %s measurement rows", profile_id, len(payload))
                return True
            finally:
                ds.close()
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass
    except Exception as e:
        logging.warning("Failed to parse/store NetCDF for profile %s: %s", profile_id, e)
        return False


router = APIRouter(prefix="/argo", tags=["argo"])


@router.get("/profiles", response_model=List[ArgoProfileResponse])
async def get_argo_profiles(
    lat_min: float = Query(-90),
    lat_max: float = Query(90),
    lon_min: float = Query(-180),
    lon_max: float = Query(180),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    ocean_region: Optional[str] = Query(None, description="Filter by ocean_region exact match"),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ArgoProfile).where(
        ArgoProfile.latitude >= lat_min,
        ArgoProfile.latitude <= lat_max,
        ArgoProfile.longitude >= lon_min,
        ArgoProfile.longitude <= lon_max,
    )
    if start_date:
        stmt = stmt.where(ArgoProfile.profile_date >= start_date)
    if end_date:
        stmt = stmt.where(ArgoProfile.profile_date <= end_date)
    if ocean_region:
        stmt = stmt.where(ArgoProfile.ocean_region == ocean_region)
    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    rows = res.scalars().all()
    return rows


@router.get("/floats", response_model=List[ArgoFloatResponse])
async def get_argo_floats(
    platform: Optional[str] = None,
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ArgoFloat)
    if platform:
        stmt = stmt.where(ArgoFloat.platform_number == platform)
    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/profiles/{profile_id}/measurements", response_model=MeasurementsResponse)
async def get_profile_measurements(
    profile_id: int,
    db: AsyncSession = Depends(get_db),
):
    # Fetch all measurements for this profile, ordered by pressure/depth ascending when available
    stmt = select(ArgoMeasurement).where(ArgoMeasurement.profile_id == profile_id)
    # Prefer ordering by depth if present else by pressure else by id
    stmt = stmt.order_by(
        (ArgoMeasurement.depth.is_(None)).asc(),
        ArgoMeasurement.depth.asc().nulls_last(),
        (ArgoMeasurement.pressure.is_(None)).asc(),
        ArgoMeasurement.pressure.asc().nulls_last(),
        ArgoMeasurement.id.asc(),
    )
    res = await db.execute(stmt)
    rows = res.scalars().all()
    if rows is None or len(rows) == 0:
        # Attempt on-demand fetch
        created = await _fetch_and_store_measurements(profile_id, db)
        if not created:
            # Return empty arrays gracefully
            return MeasurementsResponse(depth=[], temperature=[], salinity=[])
        # Re-run query
        res = await db.execute(stmt)
        rows = res.scalars().all()

    def _finite_or_none(v):
        if v is None:
            return None
        try:
            f = float(v)
            return f if math.isfinite(f) else None
        except Exception:
            return None

    depth: list[float] = []
    temp: list[float] = []
    sal: list[float] = []
    for m in rows:
        # Prefer depth value if present, otherwise derive a rough depth from pressure using ~1 dbar ≈ 1 m (simplification)
        d_val = _finite_or_none(m.depth)
        if d_val is None:
            d_val = _finite_or_none(m.pressure)
        t_val = _finite_or_none(m.temperature)
        s_val = _finite_or_none(m.salinity)
        if d_val is None:
            # Skip points with no vertical coordinate
            continue
        depth.append(float(d_val))
        temp.append(float(t_val) if t_val is not None else None)
        sal.append(float(s_val) if s_val is not None else None)

    # If empty, return empty arrays
    if not depth:
        return MeasurementsResponse(depth=[], temperature=[], salinity=[])

    # Optionally filter out points where depth is missing; keep None for temp/sal allowed by schema
    triples = [(d, t, s) for d, t, s in zip(depth, temp, sal) if d is not None]
    if not triples:
        return MeasurementsResponse(depth=[], temperature=[], salinity=[])

    triples_sorted = sorted(triples, key=lambda x: (x[0] is None, x[0] if x[0] is not None else 0))
    d_sorted = [x[0] for x in triples_sorted]
    t_sorted = [x[1] for x in triples_sorted]
    s_sorted = [x[2] for x in triples_sorted]

    return MeasurementsResponse(depth=d_sorted, temperature=t_sorted, salinity=s_sorted)


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    prof_count = await db.scalar(select(func.count()).select_from(ArgoProfile))
    float_count = await db.scalar(select(func.count()).select_from(ArgoFloat))
    return {"profiles": prof_count or 0, "floats": float_count or 0}


@router.get("/export", response_class=StreamingResponse)
async def export_profiles_csv(
    lat_min: float = Query(-90),
    lat_max: float = Query(90),
    lon_min: float = Query(-180),
    lon_max: float = Query(180),
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    ocean_region: Optional[str] = Query(None),
    limit: int = Query(1000, le=10000),
    db: AsyncSession = Depends(get_db),
):
    """Export filtered profiles as CSV"""
    stmt = select(
        ArgoProfile.platform_number,
        ArgoProfile.cycle_number,
        ArgoProfile.profile_date,
        ArgoProfile.latitude,
        ArgoProfile.longitude,
        ArgoProfile.ocean_region,
    ).where(
        ArgoProfile.latitude >= lat_min,
        ArgoProfile.latitude <= lat_max,
        ArgoProfile.longitude >= lon_min,
        ArgoProfile.longitude <= lon_max,
    )
    if start_date:
        stmt = stmt.where(ArgoProfile.profile_date >= start_date)
    if end_date:
        stmt = stmt.where(ArgoProfile.profile_date <= end_date)
    if ocean_region:
        stmt = stmt.where(ArgoProfile.ocean_region == ocean_region)
    stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    rows = res.all()

    def iter_csv():
        yield "platform_number,cycle_number,profile_date,latitude,longitude,ocean_region\n"
        for r in rows:
            platform_number, cycle_number, profile_date, latitude, longitude, ocean_region = r
            date_str = profile_date.isoformat() if profile_date else ""
            region = ocean_region or ""
            yield f"{platform_number},{cycle_number},{date_str},{latitude},{longitude},{region}\n"

    return StreamingResponse(iter_csv(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=argo_profiles.csv"})
