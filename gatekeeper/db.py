"""Database setup — SQLAlchemy async with SQLite."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from gatekeeper.config import settings

engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    future=True,
)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """Create all tables."""
    from gatekeeper.models import ApiKey, AuditLog, GoogleToken, RoutePolicy  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Dependency that yields an async DB session."""
    async with async_session() as session:
        yield session