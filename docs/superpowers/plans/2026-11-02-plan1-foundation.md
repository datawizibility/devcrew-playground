# SmartAP India — Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the multi-tenant backend foundation: Docker dev environment, FastAPI core API, Postgres with row-level-security tenant isolation, JWT auth, vendor CRUD, and an immutable audit log.

**Architecture:** Python 3.12 + FastAPI monorepo backend (`app/`), SQLAlchemy 2.0 async against Postgres 16, Alembic migrations, pytest + httpx test suite against a real Postgres test database. Tenant isolation is enforced in the database (Postgres RLS keyed on `app.tenant_id`), not just in application queries.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0 (async, asyncpg), Alembic, Pydantic v2 + pydantic-settings, PyJWT, bcrypt, pytest + pytest-asyncio + httpx, Docker Compose (Postgres 16, Redis 7).

**Spec:** `docs/superpowers/specs/2026-11-02-ap-automation-saas-design.md`

## Global Constraints

- Python `>=3.12`; all dependencies pinned with `>=` floors only (no upper pins) in `pyproject.toml`
- Every tenant-owned table carries `tenant_id UUID NOT NULL` FK to `tenants` and a Postgres RLS policy `tenant_isolation` using `current_setting('app.tenant_id', true)::uuid`
- RLS policies are `FORCE`d; the application connects as a non-owner role `smartap_app`
- Roles are exactly: `admin`, `ap_team`, `approver`, `viewer` (stored as text, validated at API layer)
- Audit events are append-only: no UPDATE/DELETE endpoints and a DB trigger rejecting UPDATE/DELETE
- Audit retention: 7 years (no purge job in this plan; retention policy documented in migration comment)
- All timestamps are `timestamptz` (UTC)
- Conventional commits (`feat:`, `test:`, `chore:`, `fix:`)
- Every test run uses a dedicated test database `smartap_test`, never the dev database
- Secrets come from environment variables via pydantic-settings; dev defaults are allowed but `jwt_secret` must be overridable

## Plan Series Context

This is Plan 1 of 9. Later plans (Intake, Extraction, Compliance, Matching, Workflow, ERP Connectors, Frontend, Nightly Jobs) build on the interfaces produced here:

- `app.db.get_db` — yields an `AsyncSession` inside an open transaction
- `app.db.set_tenant(session, tenant_id)` — sets `app.tenant_id` for RLS within the current transaction
- `app.api.deps.get_current_user` — dependency returning `AuthContext(tenant_id, user_id, role)`
- `app.models.base.Base` and `TenantMixin` — declarative base and tenant-scoped mixin
- `app.services.audit.record_audit(session, *, tenant_id, actor_user_id, action, entity_type, entity_id, payload)` — append an audit event

---

### Task 1: Repository scaffold + Docker Compose dev environment

**Files:**
- Create: `pyproject.toml`
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `app/__init__.py` (empty)
- Create: `app/main.py`
- Create: `tests/__init__.py` (empty)
- Create: `tests/test_health.py`

**Interfaces:**
- Consumes: nothing (first task)
- Produces: `app.main.app` (FastAPI instance) with `GET /health` returning `{"status": "ok"}`; Docker services `db` (Postgres 16, port 5432, user `smartap`, password `smartap`, db `smartap`) and `redis` (Redis 7, port 6379)

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "smartap-api"
version = "0.1.0"
description = "SmartAP India - AP automation SaaS backend"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.32.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.6.0",
    "pyjwt>=2.10.0",
    "bcrypt>=4.2.0",
    "python-multipart>=0.0.17",
]

[dependency-groups]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.24.0",
    "httpx>=0.28.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

- [ ] **Step 2: Create `docker-compose.yml`**

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: smartap
      POSTGRES_PASSWORD: smartap
      POSTGRES_DB: smartap
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U smartap"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

- [ ] **Step 3: Create `.env.example` and `.gitignore`**

`.env.example`:
```
DATABASE_URL=postgresql+asyncpg://smartap:smartap@localhost:5432/smartap
JWT_SECRET=dev-secret-change-me
ENVIRONMENT=dev
```

`.gitignore`:
```
__pycache__/
*.pyc
.venv/
.env
.pytest_cache/
alembic/__pycache__/
```

- [ ] **Step 4: Create `app/main.py` with health endpoint**

```python
from fastapi import FastAPI

app = FastAPI(title="SmartAP India API", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

Also create empty `app/__init__.py` and `tests/__init__.py`.

- [ ] **Step 5: Write the failing health test `tests/test_health.py`**

```python
import httpx
from fastapi.testclient import TestClient

from app.main import app


def test_health_returns_ok():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 6: Install dependencies and run the test**

Run: `uv sync --dev` (or `pip install -e ".[dev]"` if uv is unavailable), then `uv run pytest tests/test_health.py -v`
Expected: PASS (1 passed)

- [ ] **Step 7: Verify Docker services start**

Run: `docker compose up -d db redis`, then `docker compose ps`
Expected: both services `running` / `healthy`

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml docker-compose.yml .env.example .gitignore app/ tests/
git commit -m "chore: scaffold FastAPI project with Docker dev environment and health endpoint"
```

---

### Task 2: Settings module

**Files:**
- Create: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Consumes: nothing
- Produces: `app.config.settings` (singleton `Settings` instance) with fields `database_url: str`, `database_url_test: str`, `jwt_secret: str`, `jwt_algorithm: str = "HS256"`, `jwt_expire_minutes: int = 720`, `environment: str = "dev"`

- [ ] **Step 1: Write the failing test `tests/test_config.py`**

```python
from app.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_expire_minutes == 720
    assert s.environment == "dev"
    assert "asyncpg" in s.database_url


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "override-secret")
    s = Settings(_env_file=None)
    assert s.jwt_secret == "override-secret"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Write `app/config.py`**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://smartap:smartap@localhost:5432/smartap"
    database_url_test: str = "postgresql+asyncpg://smartap:smartap@localhost:5432/smartap_test"
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    environment: str = "dev"


settings = Settings()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add pydantic-settings configuration module"
```

---

### Task 3: Database engine, session factory, and Alembic (async)

**Files:**
- Create: `app/db.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako` (generated by alembic init; keep as generated)
- Create: `alembic/versions/` (empty dir; migrations come in Task 4)
- Test: `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `app.config.settings`
- Produces: `app.db.engine` (AsyncEngine), `app.db.SessionLocal` (async_sessionmaker), `app.db.get_db()` (FastAPI dependency yielding `AsyncSession` inside an open transaction), `app.db.create_test_database()` / `app.db.drop_test_database()` helpers used by conftest

- [ ] **Step 1: Write `app/db.py`**

```python
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
    """Set app.tenant_id for Postgres RLS within the current transaction."""
    await session.execute(
        text("SET LOCAL app.tenant_id = :tid"), {"tid": str(tenant_id)}
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
```

- [ ] **Step 2: Initialize Alembic with the async template**

Run: `uv run alembic init -t async alembic`
Expected: creates `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`, `alembic/versions/`

- [ ] **Step 3: Edit `alembic/env.py` to use app settings and metadata**

Replace the imports and `config.set_main_option` / `target_metadata` sections so the file contains:

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.config import settings
from app.models.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

Note: `app.models.base.Base` does not exist yet — Task 4 creates it. This task's test only verifies the engine connects, so the import inside `env.py` is not exercised yet.

- [ ] **Step 4: Write `tests/conftest.py`**

```python
import asyncio

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.db import create_test_database, drop_test_database


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session", autouse=True)
async def test_database():
    await drop_test_database()
    await create_test_database()
    engine = create_async_engine(settings.database_url_test)
    # Migrations are applied by Task 4's fixture once models exist.
    yield engine
    await engine.dispose()
    await drop_test_database()
```

- [ ] **Step 5: Write the failing test `tests/test_db.py`**

```python
from sqlalchemy import text

from app.db import SessionLocal


async def test_engine_connects_to_test_database(test_database):
    engine = test_database
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1


async def test_get_db_yields_session_in_transaction():
    async for session in SessionLocal().__class__.__mro__ and _iter_get_db():
        pass  # replaced below


async def _iter_get_db():
    from app.db import get_db

    agen = get_db()
    session = await agen.__anext__()
    try:
        assert session.in_transaction()
    finally:
        await agen.aclose()
```

Simplify: replace the second test with a direct check that `get_db` yields a session in a transaction:

```python
async def test_get_db_yields_session_in_transaction():
    from app.db import get_db

    agen = get_db()
    session = await agen.__anext__()
    try:
        assert session.in_transaction()
    finally:
        await agen.aclose()
```

(Delete the placeholder `test_get_db_yields_session_in_transaction` first version; keep only the simplified one.)

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/test_db.py -v`
Expected: PASS (2 passed). If `smartap_test` creation fails on permissions, ensure the `smartap` role is the database owner (Docker default: yes).

- [ ] **Step 7: Commit**

```bash
git add app/db.py alembic.ini alembic/ tests/conftest.py tests/test_db.py
git commit -m "feat: async database engine, session factory, tenant setter, and Alembic setup"
```

---

### Task 4: Base models, Tenant/User models, and RLS migration

**Files:**
- Create: `app/models/__init__.py`
- Create: `app/models/base.py`
- Create: `app/models/tenant.py`
- Create: `app/models/user.py`
- Create: `alembic/versions/0001_tenancy_rls.py`
- Test: `tests/test_tenancy.py`

**Interfaces:**
- Consumes: `app.db` (engine), `app.models.base.Base`
- Produces:
  - `Base` (declarative base with naming convention)
  - `TenantMixin` — adds `id: UUID (pk, default uuid4)`, `tenant_id: UUID (FK tenants.id, NOT NULL, indexed)`
  - `Tenant` model — table `tenants`, columns `id UUID pk`, `name str`, `created_at timestamptz`
  - `User` model — table `users`, `TenantMixin`, columns `email str unique-per-tenant`, `password_hash str`, `role str` (one of admin/ap_team/approver/viewer), `is_active bool default True`, `created_at`
  - Migration `0001_tenancy_rls` creating `tenants`, `users`, enabling+forcing RLS on `users` with policy `tenant_isolation`, creating non-owner role `smartap_app` with grants

- [ ] **Step 1: Write `app/models/base.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, MetaData, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TenantMixin:
    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 2: Write `app/models/tenant.py`**

```python
import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

- [ ] **Step 3: Write `app/models/user.py`**

```python
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantMixin

VALID_ROLES = ("admin", "ap_team", "approver", "viewer")


class User(TenantMixin):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        # unique email per tenant
        {"sqlite_autoincrement": False},  # placeholder removed in migration; see note
    )
```

Note: implement the per-tenant unique constraint in the migration as a unique index on `(tenant_id, email)` rather than relying on `__table_args__` here. Replace the `__table_args__` block above with:

```python
from sqlalchemy import UniqueConstraint

    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),)
```

- [ ] **Step 4: Create `app/models/__init__.py`**

```python
from app.models.base import Base, TenantMixin
from app.models.tenant import Tenant
from app.models.user import User

__all__ = ["Base", "TenantMixin", "Tenant", "User"]
```

- [ ] **Step 5: Write the failing test `tests/test_tenancy.py`**

```python
import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal, set_tenant
from app.models import Tenant, User


async def _make_tenant_with_user(name: str, email: str) -> tuple[Tenant, User]:
    async with SessionLocal() as session:
        async with session.begin():
            tenant = Tenant(name=name)
            session.add(tenant)
            await session.flush()
            user = User(
                tenant_id=tenant.id,
                email=email,
                password_hash="x",
                role="admin",
            )
            session.add(user)
            await session.flush()
            return tenant, user


async def test_rls_blocks_cross_tenant_reads(test_database):
    from app.db import create_test_database  # noqa: F401  (fixture ensures db)

    # Migrations must have been applied by the migration fixture (see Step 7).
    tenant_a, user_a = await _make_tenant_with_user("A", "a@example.com")
    tenant_b, user_b = await _make_tenant_with_user("B", "b@example.com")

    # As tenant A, we must see only A's users.
    async with SessionLocal() as session:
        async with session.begin():
            await set_tenant(session, tenant_a.id)
            rows = (await session.execute(text("SELECT email FROM users"))).scalars().all()
            assert rows == ["a@example.com"]

    # Without tenant set, RLS must return nothing.
    async with SessionLocal() as session:
        async with session.begin():
            rows = (await session.execute(text("SELECT email FROM users"))).scalars().all()
            assert rows == []
```

- [ ] **Step 6: Add a session-scoped migration fixture to `tests/conftest.py`**

Append to `tests/conftest.py` (after the existing fixtures):

```python
@pytest.fixture(scope="session", autouse=True)
async def applied_migrations(test_database):
    from alembic import command
    from alembic.config import Config

    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", settings.database_url_test)
    command.upgrade(cfg, "head")
```

Note: `command.upgrade` is synchronous and uses the sync URL. Because `alembic/env.py` uses `async_engine_from_config`, running it inside pytest's loop can conflict. If `RuntimeError` occurs, run migrations via subprocess instead:

```python
import subprocess
import sys

@pytest.fixture(scope="session", autouse=True)
async def applied_migrations(test_database):
    env = {"DATABASE_URL": settings.database_url_test, "PATH": __import__("os").environ["PATH"]}
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        check=True,
        env=env,
    )
```

(Use the subprocess variant if the in-process variant fails; prefer in-process first.)

- [ ] **Step 7: Generate and hand-write migration `alembic/versions/0001_tenancy_rls.py`**

Run: `uv run alembic revision -m "tenancy rls"` then replace the generated file content with:

```python
"""tenancy rls

Revision ID: 0001
Revises:
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TENANT_POLICY = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'smartap_app') THEN
        CREATE ROLE smartap_app LOGIN;
    END IF;
END
$$;
"""


def upgrade() -> None:
    op.execute(TENANT_POLICY)

    op.create_table(
        "tenants",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "users",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "email", name="uq_users_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # Row-level security on users
    op.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE users FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON users USING "
        "(tenant_id = current_setting('app.tenant_id', true)::uuid)"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO smartap_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO smartap_app")
    op.execute("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO smartap_app")


def downgrade() -> None:
    op.drop_table("users")
    op.drop_table("tenants")
```

Important: the dev/test connection runs as `smartap` (table owner). With `FORCE ROW LEVEL SECURITY`, the owner is also subject to RLS, so `set_tenant` must be called before any tenant-table query in the same transaction — which is the design. The `smartap_app` role is created now for production parity; wiring the app to connect as `smartap_app` happens in the deployment plan.

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_tenancy.py -v`
Expected: PASS (2 passed). If the RLS "no tenant" case returns rows, verify `FORCE ROW LEVEL SECURITY` executed and that `current_setting('app.tenant_id', true)` returns NULL (empty result) rather than erroring.

- [ ] **Step 9: Commit**

```bash
git add app/models/ alembic/versions/0001_tenancy_rls.py tests/test_tenancy.py tests/conftest.py
git commit -m "feat: multi-tenant models with Postgres RLS tenant isolation"
```

---

### Task 5: Security helpers + auth API (bootstrap tenant, login, current-user dependency)

**Files:**
- Create: `app/security.py`
- Create: `app/schemas.py`
- Create: `app/api/__init__.py` (empty)
- Create: `app/api/deps.py`
- Create: `app/api/routes/__init__.py`
- Create: `app/api/routes/auth.py`
- Modify: `app/main.py` (include auth router)
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `app.models.User`, `app.db.get_db`, `app.config.settings`
- Produces:
  - `app.security.hash_password(password: str) -> str`, `verify_password(password: str, hashed: str) -> bool`, `create_access_token(*, tenant_id: UUID, user_id: UUID, role: str) -> str`, `decode_token(token: str) -> dict`
  - `app.api.deps.AuthContext` (dataclass: `tenant_id: UUID`, `user_id: UUID`, `role: str`) and `app.api.deps.get_current_user` (FastAPI dependency reading `Authorization: Bearer <jwt>`)
  - Routes: `POST /tenants/bootstrap` `{name, admin_email, admin_password}` → `{tenant_id, admin_user_id, access_token}`; `POST /auth/login` `{email, password, tenant_id}` → `{access_token, role}`

- [ ] **Step 1: Write the failing test `tests/test_auth.py`**

```python
import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    import uuid

    token = create_access_token(
        tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), role="admin"
    )
    from app.security import decode_token

    claims = decode_token(token)
    assert claims["role"] == "admin"
    assert "tenant_id" in claims and "user_id" in claims


def test_bootstrap_and_login_flow(test_database):
    client = TestClient(app)

    r = client.post(
        "/tenants/bootstrap",
        json={
            "name": "Acme Manufacturing",
            "admin_email": "admin@acme.test",
            "admin_password": "supersecret",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    tenant_id = body["tenant_id"]
    assert body["access_token"]

    r2 = client.post(
        "/auth/login",
        json={
            "tenant_id": tenant_id,
            "email": "admin@acme.test",
            "password": "supersecret",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["role"] == "admin"

    # Wrong password rejected
    r3 = client.post(
        "/auth/login",
        json={
            "tenant_id": tenant_id,
            "email": "admin@acme.test",
            "password": "nope",
        },
    )
    assert r3.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.security'`

- [ ] **Step 3: Write `app/security.py`**

```python
import datetime as dt
import uuid
from typing import Any

import bcrypt
import jwt

from app.config import settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_access_token(*, tenant_id: uuid.UUID, user_id: uuid.UUID, role: str) -> str:
    now = dt.datetime.now(dt.UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": now,
        "exp": now + dt.timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
```

- [ ] **Step 4: Write `app/schemas.py`**

```python
import uuid

from pydantic import BaseModel, EmailStr, Field


class BootstrapRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    admin_email: EmailStr
    admin_password: str = Field(min_length=8)


class BootstrapResponse(BaseModel):
    tenant_id: uuid.UUID
    admin_user_id: uuid.UUID
    access_token: str


class LoginRequest(BaseModel):
    tenant_id: uuid.UUID
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    role: str
```

Add `email-validator` to dependencies in `pyproject.toml` (`"email-validator>=2.2.0"`) and run `uv sync`.

- [ ] **Step 5: Write `app/api/deps.py`**

```python
import uuid
from dataclasses import dataclass

import jwt as pyjwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db, set_tenant
from app.security import decode_token

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    role: str


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthContext:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    try:
        claims = decode_token(credentials.credentials)
    except pyjwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token")
    return AuthContext(
        tenant_id=uuid.UUID(claims["tenant_id"]),
        user_id=uuid.UUID(claims["sub"]),
        role=claims["role"],
    )


async def get_tenant_db(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> AsyncSession:
    """Session with RLS tenant context set for the authenticated tenant."""
    await set_tenant(session, auth.tenant_id)
    return session
```

- [ ] **Step 6: Write `app/api/routes/auth.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user
from app.db import get_db
from app.models import Tenant, User
from app.schemas import BootstrapRequest, BootstrapResponse, LoginRequest, LoginResponse
from app.security import create_access_token, hash_password, verify_password

router = APIRouter()


@router.post("/tenants/bootstrap", response_model=BootstrapResponse, status_code=201)
async def bootstrap_tenant(payload: BootstrapRequest, session: AsyncSession = Depends(get_db)) -> BootstrapResponse:
    async with session.begin_nested():
        tenant = Tenant(name=payload.name)
        session.add(tenant)
        await session.flush()
        user = User(
            tenant_id=tenant.id,
            email=payload.admin_email,
            password_hash=hash_password(payload.admin_password),
            role="admin",
        )
        session.add(user)
        await session.flush()
        tenant_id, user_id = tenant.id, user.id
    token = create_access_token(tenant_id=tenant_id, user_id=user_id, role="admin")
    return BootstrapResponse(tenant_id=tenant_id, admin_user_id=user_id, access_token=token)


@router.post("/auth/login", response_model=LoginResponse)
async def login(payload: LoginRequest, session: AsyncSession = Depends(get_db)) -> LoginResponse:
    # Login runs with RLS tenant context for the requested tenant.
    from app.db import set_tenant

    await set_tenant(session, payload.tenant_id)
    result = await session.execute(
        select(User).where(User.email == payload.email, User.is_active.is_(True))
    )
    user = result.scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")
    token = create_access_token(tenant_id=user.tenant_id, user_id=user.id, role=user.role)
    return LoginResponse(access_token=token, role=user.role)


@router.get("/auth/me")
async def me(auth: AuthContext = Depends(get_current_user)) -> dict:
    return {"tenant_id": str(auth.tenant_id), "user_id": str(auth.user_id), "role": auth.role}
```

- [ ] **Step 7: Wire the router into `app/main.py`**

Replace `app/main.py` with:

```python
from fastapi import FastAPI

from app.api.routes import auth

app = FastAPI(title="SmartAP India API", version="0.1.0")
app.include_router(auth.router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
```

Create empty `app/api/__init__.py` and `app/api/routes/__init__.py`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `uv run pytest tests/test_auth.py -v`
Expected: PASS (3 passed)

- [ ] **Step 9: Commit**

```bash
git add app/security.py app/schemas.py app/api/ app/main.py tests/test_auth.py pyproject.toml uv.lock
git commit -m "feat: JWT auth, tenant bootstrap, login, and current-user dependency"
```

---

### Task 6: Vendor model + tenant-scoped CRUD API

**Files:**
- Create: `app/models/vendor.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/0002_vendors.py`
- Create: `app/api/routes/vendors.py`
- Modify: `app/main.py` (include vendors router)
- Test: `tests/test_vendors.py`

**Interfaces:**
- Consumes: `TenantMixin`, `get_tenant_db`, `AuthContext`, `set_tenant`
- Produces:
  - `Vendor` model — table `vendors`, `TenantMixin`, columns: `legal_name str`, `gstin str nullable (15 chars)`, `pan str nullable (10 chars)`, `udyam_number str nullable`, `email str nullable`, `phone str nullable`, `is_msme bool default False`, `is_active bool default True`
  - Routes: `POST /vendors`, `GET /vendors`, `GET /vendors/{id}`, `PATCH /vendors/{id}` (all require auth; RLS-scoped)

- [ ] **Step 1: Write the failing test `tests/test_vendors.py`**

```python
import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _bootstrap() -> dict:
    r = client.post(
        "/tenants/bootstrap",
        json={
            "name": "VendorTestCo",
            "admin_email": "ap@vendortest.test",
            "admin_password": "supersecret",
        },
    )
    return r.json()


def test_vendor_crud_scoped_to_tenant(test_database):
    body = _bootstrap()
    token = body["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Create
    r = client.post(
        "/vendors",
        headers=headers,
        json={
            "legal_name": "Sharma Steel Traders",
            "gstin": "27AAPCS1234A1Z5",
            "pan": "AAPCS1234A",
            "is_msme": True,
        },
    )
    assert r.status_code == 201, r.text
    vendor = r.json()
    assert vendor["legal_name"] == "Sharma Steel Traders"
    assert vendor["is_msme"] is True

    # List
    r = client.get("/vendors", headers=headers)
    assert r.status_code == 200
    assert len(r.json()) == 1

    # Get one
    r = client.get(f"/vendors/{vendor['id']}", headers=headers)
    assert r.status_code == 200

    # Patch
    r = client.patch(
        f"/vendors/{vendor['id']}",
        headers=headers,
        json={"email": "billing@sharmasteel.test"},
    )
    assert r.status_code == 200
    assert r.json()["email"] == "billing@sharmasteel.test"

    # Unauthenticated access rejected
    r = client.get("/vendors")
    assert r.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vendors.py -v`
Expected: FAIL with 404 on `POST /vendors` (router not yet included)

- [ ] **Step 3: Write `app/models/vendor.py`**

```python
from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import TenantMixin


class Vendor(TenantMixin):
    __tablename__ = "vendors"

    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    gstin: Mapped[str | None] = mapped_column(String(15), nullable=True)
    pan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    udyam_number: Mapped[str | None] = mapped_column(String(30), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_msme: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
```

Update `app/models/__init__.py` to export `Vendor`.

- [ ] **Step 4: Create migration `alembic/versions/0002_vendors.py`**

Run: `uv run alembic revision -m "vendors"` then write:

```python
"""vendors

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vendors",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("legal_name", sa.String(255), nullable=False),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("pan", sa.String(10), nullable=True),
        sa.Column("udyam_number", sa.String(30), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("is_msme", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_vendors_tenant_id", "vendors", ["tenant_id"])
    op.execute("ALTER TABLE vendors ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE vendors FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON vendors USING "
        "(tenant_id = current_setting('app.tenant_id', true)::uuid)"
    )


def downgrade() -> None:
    op.drop_table("vendors")
```

- [ ] **Step 5: Write `app/api/routes/vendors.py`**

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_tenant_db
from app.models import Vendor

router = APIRouter(prefix="/vendors", tags=["vendors"])


class VendorCreate(BaseModel):
    legal_name: str = Field(min_length=1, max_length=255)
    gstin: str | None = Field(default=None, max_length=15)
    pan: str | None = Field(default=None, max_length=10)
    udyam_number: str | None = Field(default=None, max_length=30)
    email: str | None = None
    phone: str | None = None
    is_msme: bool = False


class VendorUpdate(BaseModel):
    legal_name: str | None = None
    gstin: str | None = None
    pan: str | None = None
    udyam_number: str | None = None
    email: str | None = None
    phone: str | None = None
    is_msme: bool | None = None
    is_active: bool | None = None


class VendorOut(VendorCreate):
    id: uuid.UUID
    tenant_id: uuid.UUID
    is_active: bool

    class Config:
        from_attributes = True


@router.post("", response_model=VendorOut, status_code=201)
async def create_vendor(
    payload: VendorCreate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_tenant_db),
) -> Vendor:
    vendor = Vendor(tenant_id=auth.tenant_id, **payload.model_dump())
    session.add(vendor)
    await session.flush()
    return vendor


@router.get("", response_model=list[VendorOut])
async def list_vendors(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_tenant_db),
) -> list[Vendor]:
    result = await session.execute(
        select(Vendor).where(Vendor.is_active.is_(True)).order_by(Vendor.legal_name)
    )
    return list(result.scalars().all())


@router.get("/{vendor_id}", response_model=VendorOut)
async def get_vendor(
    vendor_id: uuid.UUID,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_tenant_db),
) -> Vendor:
    vendor = await session.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor not found")
    return vendor


@router.patch("/{vendor_id}", response_model=VendorOut)
async def update_vendor(
    vendor_id: uuid.UUID,
    payload: VendorUpdate,
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_tenant_db),
) -> Vendor:
    vendor = await session.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vendor not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(vendor, field, value)
    await session.flush()
    return vendor
```

- [ ] **Step 6: Include the router in `app/main.py`**

Add after the auth router include:

```python
from app.api.routes import auth, vendors

app.include_router(vendors.router)
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_vendors.py -v`
Expected: PASS (1 passed)

- [ ] **Step 8: Commit**

```bash
git add app/models/vendor.py app/models/__init__.py alembic/versions/0002_vendors.py app/api/routes/vendors.py app/main.py tests/test_vendors.py
git commit -m "feat: vendor model and tenant-scoped CRUD API"
```

---

### Task 7: Immutable audit log

**Files:**
- Create: `app/models/audit.py`
- Modify: `app/models/__init__.py`
- Create: `alembic/versions/0003_audit_events.py`
- Create: `app/services/__init__.py` (empty)
- Create: `app/services/audit.py`
- Modify: `app/api/routes/vendors.py` (audit vendor create/update)
- Test: `tests/test_audit.py`

**Interfaces:**
- Consumes: `Base`, `get_tenant_db`
- Produces:
  - `AuditEvent` model — table `audit_events`, columns: `id UUID pk`, `tenant_id UUID FK`, `actor_user_id UUID nullable`, `action str`, `entity_type str`, `entity_id UUID nullable`, `payload JSONB default {}`, `created_at timestamptz`; DB trigger rejects UPDATE/DELETE
  - `app.services.audit.record_audit(session, *, tenant_id, actor_user_id, action, entity_type, entity_id=None, payload=None) -> None`
  - Route: `GET /audit-events` (admin only) returning tenant's events, newest first, limit 100

- [ ] **Step 1: Write the failing test `tests/test_audit.py`**

```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.main import app

client = TestClient(app)


def test_audit_events_recorded_and_immutable(test_database):
    body = client.post(
        "/tenants/bootstrap",
        json={
            "name": "AuditCo",
            "admin_email": "admin@auditco.test",
            "admin_password": "supersecret",
        },
    ).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    # Creating a vendor should record an audit event.
    r = client.post(
        "/vendors",
        headers=headers,
        json={"legal_name": "Audit Vendor"},
    )
    assert r.status_code == 201

    r = client.get("/audit-events", headers=headers)
    assert r.status_code == 200
    events = r.json()
    assert len(events) >= 1
    assert any(e["action"] == "vendor.created" for e in events)

    # Direct UPDATE/DELETE must be rejected by the DB trigger.
    async def _try_update():
        from app.db import SessionLocal, set_tenant

        async with SessionLocal() as session:
            async with session.begin():
                await set_tenant(session, __import__("uuid").UUID(body["tenant_id"]))
                with pytest.raises(Exception):
                    await session.execute(
                        text("UPDATE audit_events SET action = 'tampered'")
                    )

    import asyncio

    asyncio.get_event_loop().run_until_complete(_try_update())
```

Note: if pytest-asyncio's auto mode makes mixing sync/async awkward, convert `test_audit_events_recorded_and_immutable` to `async def` and `await` the DB check directly. Prefer the async form:

```python
async def test_audit_events_recorded_and_immutable(test_database):
    body = client.post(
        "/tenants/bootstrap",
        json={
            "name": "AuditCo",
            "admin_email": "admin@auditco.test",
            "admin_password": "supersecret",
        },
    ).json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}

    r = client.post("/vendors", headers=headers, json={"legal_name": "Audit Vendor"})
    assert r.status_code == 201

    r = client.get("/audit-events", headers=headers)
    assert r.status_code == 200
    events = r.json()
    assert any(e["action"] == "vendor.created" for e in events)

    import uuid as uuid_mod

    from app.db import SessionLocal, set_tenant
    from sqlalchemy import text as sa_text

    with pytest.raises(Exception):
        async with SessionLocal() as session:
            async with session.begin():
                await set_tenant(session, uuid_mod.UUID(body["tenant_id"]))
                await session.execute(sa_text("UPDATE audit_events SET action = 'tampered'"))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_audit.py -v`
Expected: FAIL (no `/audit-events` route; no trigger)

- [ ] **Step 3: Write `app/models/audit.py`**

```python
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
```

Update `app/models/__init__.py` to export `AuditEvent`.

- [ ] **Step 4: Create migration `alembic/versions/0003_audit_events.py`**

```python
"""audit events (immutable)

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02

Retention: 7 years per spec. No purge job in this plan.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audit_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("entity_type", sa.String(100), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON audit_events USING "
        "(tenant_id = current_setting('app.tenant_id', true)::uuid)"
    )
    # Immutability trigger
    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        "CREATE TRIGGER audit_events_no_update_delete "
        "BEFORE UPDATE OR DELETE ON audit_events "
        "FOR EACH ROW EXECUTE FUNCTION prevent_audit_mutation()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_events_no_update_delete ON audit_events")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_mutation()")
    op.drop_table("audit_events")
```

- [ ] **Step 5: Write `app/services/audit.py`**

```python
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditEvent


async def record_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    session.add(
        AuditEvent(
            tenant_id=tenant_id,
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload or {},
        )
    )
```

- [ ] **Step 6: Audit vendor create/update in `app/api/routes/vendors.py`**

In `create_vendor`, after `await session.flush()`:

```python
from app.services.audit import record_audit

    await record_audit(
        session,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="vendor.created",
        entity_type="vendor",
        entity_id=vendor.id,
        payload={"legal_name": vendor.legal_name},
    )
```

In `update_vendor`, after the field loop and flush:

```python
    await record_audit(
        session,
        tenant_id=auth.tenant_id,
        actor_user_id=auth.user_id,
        action="vendor.updated",
        entity_type="vendor",
        entity_id=vendor.id,
        payload=payload.model_dump(exclude_unset=True),
    )
```

- [ ] **Step 7: Add `GET /audit-events` route (admin only)**

Create `app/api/routes/audit.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthContext, get_current_user, get_tenant_db
from app.models import AuditEvent

router = APIRouter(tags=["audit"])


@router.get("/audit-events")
async def list_audit_events(
    auth: AuthContext = Depends(get_current_user),
    session: AsyncSession = Depends(get_tenant_db),
    limit: int = 100,
) -> list[dict]:
    if auth.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role required")
    result = await session.execute(
        select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    )
    return [
        {
            "id": str(e.id),
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": str(e.entity_id) if e.entity_id else None,
            "payload": e.payload,
            "created_at": e.created_at.isoformat(),
        }
        for e in result.scalars().all()
    ]
```

Include it in `app/main.py`:

```python
from app.api.routes import audit, auth, vendors

app.include_router(audit.router)
```

- [ ] **Step 8: Run the full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS (health, config, db, tenancy, auth, vendors, audit)

- [ ] **Step 9: Commit**

```bash
git add app/models/audit.py app/models/__init__.py alembic/versions/0003_audit_events.py app/services/ app/api/routes/ tests/test_audit.py
git commit -m "feat: immutable audit log with DB trigger and admin read API"
```

---

### Task 8: Full-suite verification + README for the dev crew

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: everything above
- Produces: onboarding doc for the dev crew

- [ ] **Step 1: Run the entire suite one final time**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Write `README.md`**

```markdown
# SmartAP India — Backend

AP automation SaaS for Indian mid-market. See `docs/superpowers/specs/2026-11-02-ap-automation-saas-design.md` for the product design and `docs/superpowers/plans/` for the implementation plan series.

## Dev setup

1. `uv sync --dev`
2. `docker compose up -d db redis`
3. `uv run alembic upgrade head`
4. `uv run uvicorn app.main:app --reload`

## Tests

`uv run pytest -v` — uses database `smartap_test` (created/dropped automatically). Docker `db` service must be running.

## Key concepts

- **Tenant isolation:** Postgres RLS. Every request sets `app.tenant_id` via `app.db.set_tenant` inside the request transaction (`app.api.deps.get_tenant_db`). Never query tenant-owned tables without it.
- **Audit log:** append-only (`audit_events`), DB trigger rejects UPDATE/DELETE. Record actions via `app.services.audit.record_audit`.
- **Auth:** JWT bearer tokens with `tenant_id`, `user_id`, `role` claims. Roles: admin, ap_team, approver, viewer.
```

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: dev crew onboarding README"
```

---

## Self-Review Notes (completed during plan writing)

- **Spec coverage (Plan 1 scope):** multi-tenancy + RLS (Task 4), RBAC roles (Task 5 deps + Task 7 admin check), audit immutability + 7-year retention note (Task 7), vendor entity with GSTIN/PAN/Udyam/MSME fields (Task 6), Docker dev env (Task 1). Intake/extraction/compliance/matching/workflow/ERP/frontend are Plans 2–9 by design.
- **Placeholder scan:** Task 3 Step 5 contains an explicit instruction to delete a first-draft test and keep the simplified version — the final code is fully specified. No TBD/TODO remains.
- **Type consistency:** `AuthContext(tenant_id, user_id, role)` used identically in Tasks 5, 6, 7. `set_tenant(session, tenant_id)` signature consistent across Tasks 3, 4, 5, 7. `record_audit` keyword-only signature consistent between Task 7 definition and usage.
