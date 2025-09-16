import asyncio
import gzip
from datetime import datetime, timedelta
from typing import Optional, Sequence

import httpx
from sqlalchemy import select, insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import settings
from ..core.database import async_session_factory
from ..models.argo_data import ArgoProfile, ArgoFloat
from ..core.database import Base, engine


def _matches_region(line: str, region: Optional[str]) -> bool:
    if not region:
        return True
    r = region.lower()
    if r.startswith("i"):
        return any(x in line.lower() for x in ["indian"]) or \
               "/indian_ocean/" in line.lower()
    if r.startswith("p"):
        return any(x in line.lower() for x in ["pacific"]) or \
               "/pacific_ocean/" in line.lower()
    if r.startswith("a"):
        return any(x in line.lower() for x in ["atlantic"]) or \
               "/atlantic_ocean/" in line.lower()
    return r in line.lower()


async def _ensure_float(session: AsyncSession, platform_number: str):
    # Minimal upsert: insert if not exists
    res = await session.execute(select(ArgoFloat).where(ArgoFloat.platform_number == platform_number).limit(1))
    if res.scalars().first() is None:
        await session.execute(insert(ArgoFloat).values(platform_number=platform_number, created_at=datetime.utcnow()))


async def _fetch_with_retries(urls: Sequence[str]) -> bytes:
    timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        last_err: Exception | None = None
        for url in urls:
            for attempt in range(3):
                try:
                    r = await client.get(url)
                    r.raise_for_status()
                    return r.content
                except Exception as e:
                    last_err = e
                    await asyncio.sleep(1.5 * (attempt + 1))
        if last_err:
            raise last_err
        raise RuntimeError("Failed to fetch any index URL")


async def ingest_from_index(days_back: int, region: Optional[str], limit: int):
    base_url = str(settings.ARGO_INDEX_URL) if settings.ARGO_INDEX_URL else None
    if not base_url:
        raise RuntimeError("ARGO_INDEX_URL not configured")

    # Prefer gz (smaller), then txt, then known mirror(s)
    candidates = []
    if base_url.endswith(".gz"):
        candidates = [base_url, base_url[:-3]]
    else:
        candidates = [base_url + ".gz", base_url]
    # Mirrors
    candidates += [
        "https://usgodae.org/ftp/outgoing/argo/ar_index_global_prof.txt.gz",
        "https://usgodae.org/ftp/outgoing/argo/ar_index_global_prof.txt",
    ]

    raw = await _fetch_with_retries(candidates)
    # Decompress if gz
    if raw[:2] == b"\x1f\x8b":
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    text = raw.decode("utf-8", errors="ignore")
    lines = text.splitlines()

    cutoff = datetime.utcnow() - timedelta(days=days_back)

    # Index format: skip comment lines starting with '#'
    filtered = []
    for line in lines:
        if not line or line.startswith('#'):
            continue
        # Basic split; ARGO index columns are 'file, date, lat, lon, ocean, ...'
        parts = line.split(',')
        if len(parts) < 5:
            continue
        file_path = parts[0].strip()
        date_str = parts[1].strip()
        lat_str = parts[2].strip()
        lon_str = parts[3].strip()
        ocean_col = parts[4].strip() if len(parts) > 4 else None
        # parse date, tolerate various formats
        try:
            dt = datetime.strptime(date_str.split('T')[0], "%Y-%m-%d")
        except Exception:
            continue
        if dt < cutoff:
            continue
        if not _matches_region(line, region):
            continue
        try:
            lat = float(lat_str)
            lon = float(lon_str)
        except Exception:
            continue
        # Extract WMO/platform from path: usually the immediate parent folder
        platform_number = file_path.strip('/').split('/')[-2] if '/' in file_path else file_path
        # Prefer ocean value from index if present
        ocean_val = ocean_col or (region or None)
        filtered.append((platform_number, dt, lat, lon, ocean_val))
        if len(filtered) >= limit:
            break

    if not filtered:
        print("No recent entries matched filters.")
        return 0

    # Ensure tables exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with async_session_factory() as session:
        async with session.begin():
            for platform_number, dt, lat, lon, ocean_val in filtered:
                await _ensure_float(session, platform_number)
                await session.execute(
                    insert(ArgoProfile).values(
                        platform_number=platform_number,
                        cycle_number=1,
                        profile_date=dt,
                        latitude=lat,
                        longitude=lon,
                        ocean_region=ocean_val,
                        created_at=datetime.utcnow(),
                    )
                )
        await session.commit()
    print(f"Ingested {len(filtered)} recent profiles from index.")
    return len(filtered)


if __name__ == "__main__":
    asyncio.run(ingest_from_index(settings.INGEST_DAYS_BACK, settings.INGEST_REGION, settings.INGEST_LIMIT))
    
