from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ArgoProfileResponse(BaseModel):
    id: int
    platform_number: str
    cycle_number: int
    profile_date: Optional[datetime] = None
    latitude: float
    longitude: float
    ocean_region: Optional[str] = None

    class Config:
        from_attributes = True


class ArgoFloatResponse(BaseModel):
    id: int
    platform_number: str
    wmo_id: Optional[str] = None
    deployment_date: Optional[datetime] = None
    deployment_latitude: Optional[float] = None
    deployment_longitude: Optional[float] = None
    data_center: Optional[str] = None

    class Config:
        from_attributes = True
