from pydantic_settings import BaseSettings
from pydantic import Field, AnyHttpUrl
from typing import List


def parse_origins(origins: str | None) -> List[str] | str:
    """Return '*' or list[str] parsed from comma-separated origins.

    - None or '*' => '*'
    - Otherwise => list of trimmed non-empty origins
    """
    if origins is None:
        return "*"
    val = origins.strip()
    if val == "*" or not val:
        return "*"
    return [o.strip() for o in val.split(",") if o.strip()]


class Settings(BaseSettings):
    APP_NAME: str = "FloatChat API"
    ENV: str = Field(default="dev")
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./floatchat.db",
        description="SQLAlchemy URL; default local SQLite for P0"
    )
    API_PREFIX: str = "/api"

    # CORS: comma-separated origins, e.g. http://localhost:5173,https://yourapp.vercel.app
    CORS_ORIGINS: str = Field(
        default="*",
        description="Comma-separated origins (e.g. http://localhost:5173,https://yourapp.vercel.app). Use * for all."
    )

    # Ingestion/index source (HTTP to avoid FTP complexity for P0)
    ARGO_INDEX_URL: AnyHttpUrl | None = Field(
        default="https://data-argo.ifremer.fr/ar_index_global_prof.txt",
        description="URL to the ARGO global profile index (txt or gz)"
    )
    INGEST_DAYS_BACK: int = Field(default=7)
    INGEST_REGION: str | None = Field(default=None, description="Region filter: I|P|A or full name like 'Indian'")
    INGEST_LIMIT: int = Field(default=500)

    # AI key (used later in P1)
    GEMINI_API_KEY: str | None = None

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
