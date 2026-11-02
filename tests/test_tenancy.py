from sqlalchemy import text

from app.db import SessionLocal, set_tenant
from app.models import Tenant, User


# Deviation: with FORCE RLS active the owner connection is subject to the
# tenant_isolation policy, so user inserts (not reads) also require the
# app.tenant_id GUC to be set for the tenant being seeded.
async def _make_tenant_with_user(name: str, email: str) -> tuple[Tenant, User]:
    async with SessionLocal() as session:
        async with session.begin():
            tenant = Tenant(name=name)
            session.add(tenant)
            await session.flush()
            await set_tenant(session, tenant.id)
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
    tenant_a, _user_a = await _make_tenant_with_user("A", "a@example.com")
    _tenant_b, _user_b = await _make_tenant_with_user("B", "b@example.com")

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