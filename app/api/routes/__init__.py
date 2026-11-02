===END===

===FILE: app/api/routes/auth.py===
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