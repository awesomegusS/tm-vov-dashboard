from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
import os
from .config import settings
from .prefect_secrets import load_prefect_secret

# Lazy engine/session creation so flows can set DATABASE_URL at runtime
_engine = None
_sessionmaker = None


def _get_database_url() -> str:
    # Prefer the explicit environment variable if set (set by Prefect Secret at runtime)
    env_db = os.getenv("DATABASE_URL")
    if env_db:
        url = env_db
    else:
        # Try Prefect Secret block at runtime (works in Prefect Cloud runs)
        secret_db = load_prefect_secret("database-url")
        if secret_db:
            os.environ["DATABASE_URL"] = secret_db
            url = secret_db
        elif settings.DATABASE_URL is not None:
            url = str(settings.DATABASE_URL)
        else:
            raise RuntimeError(
                "DATABASE_URL is not set. Set the DATABASE_URL env var or create a Prefect Secret block "
                "named 'database-url' containing your Postgres connection string."
            )
    # Ensure asyncpg driver is used
    return url.replace("postgresql://", "postgresql+asyncpg://")


def AsyncSessionLocal() -> AsyncSession:
    """Return a new AsyncSession instance. This function creates the engine
    and sessionmaker lazily using the current `DATABASE_URL` environment
    variable (or the `settings.DATABASE_URL` fallback). Call sites use
    `async with AsyncSessionLocal() as session:` as before.
    """
    global _engine, _sessionmaker
    url = _get_database_url()
    if _engine is None or str(_engine.url) != url:
        _engine = create_async_engine(url, echo=settings.DEBUG)
        _sessionmaker = async_sessionmaker(bind=_engine, class_=AsyncSession, expire_on_commit=False)
    return _sessionmaker()


# Base class for our models
class Base(DeclarativeBase):
    pass