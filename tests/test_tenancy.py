import uuid

import pytest
from sqlalchemy import text

from app.db import SessionLocal, set_tenant
from app.models import Tenant, User


async def _make_tenant_with_user(name: str, email: str):
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
    tenant_a, user_a = await _make_tenant_with_user("A", "a@example.com")
    tenant_b, user_b = await _make_tenant_with_user("B", "b@example.com")

    async with SessionLocal() as session:
        async with session.begin():
            await set_tenant(session, tenant_a.id)
            rows = (await session.execute(text("SELECT email FROM users"))).scalars().all()
            assert rows == ["a@example.com"]

    async with SessionLocal() as session:
        async with session.begin():
            rows = (await session.execute(text("SELECT email FROM users"))).scalars().all()
            assert rows == []