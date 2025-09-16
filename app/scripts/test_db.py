import asyncio
import os
from sqlalchemy import select, func
from sqlalchemy.exc import SQLAlchemyError
from ..core.config import settings
from ..core.database import async_session_factory, engine
from ..models.argo_data import ArgoProfile, ArgoFloat


async def main():
    print(f"DATABASE_URL={settings.DATABASE_URL}")
    try:
        async with engine.begin() as conn:
            await conn.execute(select(func.now()) if settings.DATABASE_URL.startswith("postgresql") else select(func.count().label("c")).select_from(ArgoProfile))
        print("Engine connect OK")
    except SQLAlchemyError as e:
        print(f"Engine connect failed: {e}")
        raise

    async with async_session_factory() as session:
        try:
            profs = await session.scalar(select(func.count()).select_from(ArgoProfile))
            floats = await session.scalar(select(func.count()).select_from(ArgoFloat))
            print({"profiles": profs or 0, "floats": floats or 0})
        except SQLAlchemyError as e:
            print(f"Query failed: {e}")
            raise


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        os._exit(1)
