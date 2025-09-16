from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from typing import List, Optional
from datetime import datetime
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.database import get_db
from ..models.argo_data import ArgoProfile, ArgoFloat
from ..schemas.argo_data import ArgoProfileResponse, ArgoFloatResponse


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
