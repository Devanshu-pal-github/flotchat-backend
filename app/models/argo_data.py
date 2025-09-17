from sqlalchemy import Column, Integer, Float, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column
from ..core.database import Base


class ArgoFloat(Base):
    __tablename__ = "argo_floats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    platform_number: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    wmo_id: Mapped[str | None] = mapped_column(String(20), index=True, nullable=True)
    deployment_date: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    deployment_latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    deployment_longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_center: Mapped[str | None] = mapped_column(String(10), nullable=True)
    project_name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    created_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class ArgoProfile(Base):
    __tablename__ = "argo_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    platform_number: Mapped[str] = mapped_column(String(20), index=True, nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)
    profile_date: Mapped[DateTime | None] = mapped_column(DateTime, index=True, nullable=True)
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    position_qc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    positioning_system: Mapped[str | None] = mapped_column(String(10), nullable=True)
    vertical_sampling_scheme: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_center: Mapped[str | None] = mapped_column(String(10), nullable=True)
    ocean_region: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    created_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class ArgoMeasurement(Base):
    __tablename__ = "argo_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    profile_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    pressure: Mapped[float | None] = mapped_column(Float, nullable=True)
    pressure_qc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_qc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salinity: Mapped[float | None] = mapped_column(Float, nullable=True)
    salinity_qc: Mapped[int | None] = mapped_column(Integer, nullable=True)
    depth: Mapped[float | None] = mapped_column(Float, nullable=True)
    measurement_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)


class QueryHistory(Base):
    __tablename__ = "query_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True, autoincrement=True)
    session_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    generated_sql: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    result_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[DateTime | None] = mapped_column(DateTime, nullable=True)
