import asyncio
from datetime import datetime
from sqlalchemy import text
from ..core.database import engine
from ..core.database import Base
# Import models so metadata knows about all tables
from ..models import argo_data  # noqa: F401


async def main():
    async with engine.begin() as conn:
        # Create tables from ORM metadata (avoids multi-statement issues)
        await conn.run_sync(Base.metadata.create_all)

        # insert tiny sample if empty
        res = await conn.execute(text("SELECT COUNT(*) FROM argo_profiles"))
        count = res.scalar_one()
        if count == 0:
            await conn.execute(
                text(
                    "INSERT INTO argo_profiles (id, platform_number, cycle_number, profile_date, latitude, longitude, ocean_region, created_at) "
                    "VALUES (:id,:plat,:cyc,:dt,:lat,:lon,:reg,:cat)"
                ),
                [
                    {"id": 1, "plat": "PLAT-0001", "cyc": 1, "dt": datetime(2025, 1, 1), "lat": 19.07, "lon": 72.87, "reg": "Arabian Sea", "cat": datetime.utcnow()},
                    {"id": 2, "plat": "PLAT-0002", "cyc": 5, "dt": datetime(2025, 1, 2), "lat": 15.5, "lon": 73.2, "reg": "Arabian Sea", "cat": datetime.utcnow()},
                    {"id": 3, "plat": "PLAT-0003", "cyc": 3, "dt": datetime(2025, 1, 3), "lat": 12.9, "lon": 74.0, "reg": "Indian Ocean", "cat": datetime.utcnow()},
                ],
            )
            print("Seeded argo_profiles with 3 rows")
        else:
            print(f"argo_profiles has {count} rows; skipping seed")


if __name__ == "__main__":
    asyncio.run(main())
