import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple

import httpx
from sqlalchemy import select, update

from ..core.config import settings
from ..core.database import async_session_factory
from ..models.argo_data import ArgoProfile


def _parse_index(raw: bytes) -> List[Tuple[str, datetime | None, float | None, float | None, str]]:
    """Return list of tuples: (platform_number, date, lat, lon, file_path)."""
    if raw[:2] == b"\x1f\x8b":
        import gzip
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    text = raw.decode("utf-8", errors="ignore")
    lines = text.splitlines()

    def parse_dt(val: str) -> datetime | None:
        v = (val or "").strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(v)
        except Exception:
            pass
        for fmt in ("%Y-%m-%d", "%Y%m%d%H%M%S", "%Y%m%d"):
            try:
                return datetime.strptime(v, fmt)
            except Exception:
                continue
        return None

    out: List[Tuple[str, datetime | None, float | None, float | None, str]] = []
    for line in lines:
        if not line or line.startswith('#'):
            continue
        parts = line.split(',')
        if len(parts) < 2:
            continue
        file_path = parts[0].strip()
        date_str = parts[1].strip()
        lat = None
        lon = None
        try:
            lat = float(parts[2]) if len(parts) > 2 else None
            lon = float(parts[3]) if len(parts) > 3 else None
        except Exception:
            pass
        # Extract platform_number from path
        segs = [p for p in file_path.strip('/').split('/') if p]
        platform_number = None
        if len(segs) >= 2:
            platform_number = segs[-2]
            if platform_number.lower() in {"profiles", "dac"} and len(segs) >= 3:
                platform_number = segs[-3]
        else:
            platform_number = segs[-1] if segs else None
        if not platform_number:
            continue
        dt = parse_dt(date_str)
        out.append((platform_number, dt, lat, lon, file_path))
    return out


async def main(limit: int | None = None):
    base_url = str(settings.ARGO_INDEX_URL) if settings.ARGO_INDEX_URL else None
    if not base_url:
        raise RuntimeError("ARGO_INDEX_URL not configured")
    candidates = []
    if base_url.endswith('.gz'):
        candidates = [base_url, base_url[:-3]]
    else:
        candidates = [base_url + '.gz', base_url]
    candidates += [
        "https://usgodae.org/ftp/outgoing/argo/ar_index_global_prof.txt.gz",
        "https://usgodae.org/ftp/outgoing/argo/ar_index_global_prof.txt",
        "https://data-argo.ifremer.fr/ar_index_global_prof.txt",
    ]

    # Download index
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=60.0, pool=10.0)
    raw = None
    async with httpx.AsyncClient(timeout=timeout) as client:
        last_err = None
        for url in candidates:
            try:
                r = await client.get(url)
                r.raise_for_status()
                raw = r.content
                break
            except Exception as e:
                last_err = e
        if raw is None:
            raise RuntimeError(f"Failed to download index: {last_err}")

    rows = _parse_index(raw)
    # Bucket by platform for quick nearest-date lookup
    by_platform: Dict[str, List[Tuple[datetime | None, str]]] = defaultdict(list)
    for platform, dt, _la, _lo, path in rows:
        by_platform[platform].append((dt, path))

    async with async_session_factory() as session:
        # Pull profiles missing file_path
        stmt = select(ArgoProfile).where((ArgoProfile.file_path.is_(None)) | (ArgoProfile.file_path == ''))
        if limit and limit > 0:
            stmt = stmt.limit(limit)
        res = await session.execute(stmt)
        profs = res.scalars().all()

        updates = 0
        for p in profs:
            candidates = by_platform.get(p.platform_number)
            if not candidates:
                continue
            if p.profile_date is None:
                chosen = candidates[0][1]
            else:
                # Pick nearest date
                best = None
                best_delta = None
                for dt, path in candidates:
                    if dt is None:
                        continue
                    delta = abs((dt - p.profile_date).total_seconds())
                    if best is None or best_delta is None or delta < best_delta:
                        best = path
                        best_delta = delta
                chosen = best or candidates[0][1]
            await session.execute(
                update(ArgoProfile).where(ArgoProfile.id == p.id).values(file_path=chosen)
            )
            updates += 1
        await session.commit()
        print(f"Updated file_path for {updates} profiles")


if __name__ == "__main__":
    asyncio.run(main())
