from pydantic_settings import BaseSettings
from pydantic import Field, AnyHttpUrl
from typing import List
from pathlib import Path
import os


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


# Resolve the project root (flotchat-backend) and .env path even when cwd is different
_DEFAULT_ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "FloatChat API"
    ENV: str = Field(default="dev")
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./floatchat.db",
        description="SQLAlchemy URL; default local SQLite for P0"
    )
    # SSL controls for Postgres (used when DATABASE_URL points to Postgres)
    # Values: disable | require | verify-ca | verify-full
    # - disable: no TLS (NOT recommended)
    # - require: TLS but do not verify certificate/hostname (dev-only)
    # - verify-ca: verify certificate chain using provided CA bundle, skip hostname check
    # - verify-full: verify certificate chain and hostname (RECOMMENDED)
    DB_SSLMODE: str | None = Field(default="verify-full")
    # Path to a PEM bundle containing trusted root CAs (use if corporate proxy inserts certs)
    DB_SSLROOTCERT: str | None = Field(default=None)
    # Use certifi CA bundle if no DB_SSLROOTCERT is provided
    DB_USE_CERTIFI: bool = Field(default=True)
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
        # Always pick up the intended backend .env regardless of cwd; allow override via ENV_FILE
        env_file = os.getenv("ENV_FILE", str(_DEFAULT_ENV_PATH))
        extra = "ignore"


settings = Settings()
