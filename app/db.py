from collections.abc import AsyncIterator
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

engine: AsyncEngine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield a session inside an open transaction. Caller must close."""
    async with SessionLocal() as session:
        async with session.begin():
            yield session


async def set_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    """Set app.tenant_id for Postgres RLS within the current transaction.

    Deviation: uses set_config() because Postgres does not accept bind
    parameters in `SET LOCAL` statements (server-side syntax error).
    set_config(..., is_local=true) is equivalent to SET LOCAL.
    """
    await session.execute(
        text("SELECT set_config('app.tenant_id', :value, true)"),
        {"value": str(tenant_id)},
    )


async def _ensure_database(url: str, dbname: str) -> None:
    """Create dbname if missing, connecting to the default 'postgres' db."""
    admin_url = url.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            exists = await conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": dbname},
            )
            if exists.scalar() is None:
                await conn.execute(text(f'CREATE DATABASE "{dbname}"'))
    finally:
        await admin_engine.dispose()


async def create_test_database() -> None:
    await _ensure_database(settings.database_url_test, "smartap_test")


async def drop_test_database() -> None:
    admin_url = settings.database_url_test.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_async_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        async with admin_engine.connect() as conn:
            await conn.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = 'smartap_test' AND pid <> pg_backend_pid()"
                )
            )
            await conn.execute(text('DROP DATABASE IF EXISTS "smartap_test"'))
    finally:
        await admin_engine.dispose()