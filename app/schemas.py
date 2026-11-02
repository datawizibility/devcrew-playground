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