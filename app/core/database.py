from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from .config import settings
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import os
import ssl
try:
    import certifi  # provided via httpx dependency; used for trusted CA bundle
except Exception:  # pragma: no cover
    certifi = None


Base = declarative_base()


def _extract_ssl_mode(url: str) -> tuple[str, str | None]:
    """Return (clean_url, ssl_mode) by removing ssl/sslmode from the URL.

    ssl_mode is one of: disable, allow, prefer, require, verify-ca, verify-full, or None.
    """
    try:
        parts = urlsplit(url)
        query_list = list(parse_qsl(parts.query, keep_blank_values=True))
        q = {k: v for k, v in query_list}

        ssl_mode = None
        # Prefer explicit sslmode
        if "sslmode" in q:
            ssl_mode = (q.get("sslmode") or "").lower() or None
            q.pop("sslmode", None)
        # If ssl=true/yes/1 provided, map to 'require'
        elif q.get("ssl", "").lower() in {"true", "1", "yes"}:
            ssl_mode = "require"
            q.pop("ssl", None)

        new_query = urlencode(q)
        clean = urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))
        return clean, ssl_mode
    except Exception:
        return url, None


def _to_async_dsn(url: str) -> str:
    # Convert driver
    new_url = url
    if url.startswith("postgresql://"):
        new_url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    if new_url.startswith("sqlite://") and "+aiosqlite" not in new_url:
        new_url = new_url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    # Strip ssl/sslmode from the URL; we'll pass via connect_args
    if new_url.startswith("postgresql+asyncpg://"):
        new_url, _ = _extract_ssl_mode(new_url)
    return new_url


ASYNC_DATABASE_URL_RAW = settings.DATABASE_URL
ASYNC_DATABASE_URL = _to_async_dsn(ASYNC_DATABASE_URL_RAW)

def _build_ssl_context(db_sslmode: str | None, rootcert: str | None, use_certifi: bool) -> ssl.SSLContext | bool | None:
    """Translate sslmode/rootcert settings to an asyncpg-compatible value.

    Returns:
      - ssl.SSLContext when TLS is desired
      - False when TLS is disabled
      - None to let driver decide (not used here)
    """
    mode = (db_sslmode or "").strip().lower() or None
    if mode == "disable":
        return False

    # Create default context; try specific CA bundle if provided
    cafile = None
    if rootcert:
        rootcert = os.path.expanduser(rootcert)
        if os.path.isfile(rootcert):
            cafile = rootcert
    if cafile is None and use_certifi and certifi is not None:
        cafile = certifi.where()

    ctx = ssl.create_default_context(cafile=cafile)
    # Map modes to Python SSL behavior similar to libpq
    if mode == "require":
        # Encrypt, but do NOT verify cert/hostname (DEV ONLY)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    elif mode == "verify-ca":
        # Verify CA chain only
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_REQUIRED
    else:  # None or 'verify-full' or unknown -> be strict
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED

    return ctx

# Determine connect_args (only for asyncpg)
connect_args: dict = {}
if ASYNC_DATABASE_URL.startswith("postgresql+asyncpg://"):
    # Ignore any ssl/sslmode in the URL and prefer explicit env-configured values
    _, url_ssl_mode = _extract_ssl_mode(
        ASYNC_DATABASE_URL_RAW.replace("postgresql://", "postgresql+asyncpg://", 1)
        if ASYNC_DATABASE_URL_RAW.startswith("postgresql://") else ASYNC_DATABASE_URL_RAW
    )
    # Merge precedence: Settings.DB_SSLMODE > URL sslmode > default
    effective_mode = (settings.DB_SSLMODE or url_ssl_mode or "verify-full")
    ctx = _build_ssl_context(effective_mode, settings.DB_SSLROOTCERT, settings.DB_USE_CERTIFI)
    connect_args["ssl"] = ctx

engine = create_async_engine(ASYNC_DATABASE_URL, future=True, echo=False, connect_args=connect_args)
async_session_factory = sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        yield session
