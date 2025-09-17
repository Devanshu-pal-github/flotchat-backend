import asyncio
from sqlalchemy import text
from ..core.database import engine, Base
# Ensure models are imported so metadata contains tables
from ..models import argo_data  # noqa: F401


async def main():
    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Simple sanity check query depending on dialect
        try:
            await conn.execute(text("SELECT 1"))
            print("Database connection OK and tables ensured.")
        except Exception as e:
            print(f"Connection check failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
