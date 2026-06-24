"""Schemas Pydantic (contrato HTTP) do Identity."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class RegisterTenantRequest(BaseModel):
    cnpj: str = Field(..., examples=["12.345.678/0001-95"])
    razao_social: str = Field(..., min_length=2, max_length=200)
    slug: str = Field(..., min_length=2, max_length=60, examples=["sol-contabilidade"])
    admin_email: EmailStr
    admin_full_name: str = Field(..., min_length=2, max_length=200)
    admin_password: str = Field(..., min_length=8, max_length=128)
    plan_code: str = "trial"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)
    tenant_slug: str | None = Field(
        default=None, description="Necessário só se o e-mail existir em >1 escritório."
    )


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class CreateUserRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=2, max_length=200)
    password: str = Field(..., min_length=8, max_length=128)
    role: str = Field(default="user", examples=["user", "supervisor", "admin"])


class UserResponse(BaseModel):
    id: UUID
    tenant_id: UUID
    email: EmailStr
    full_name: str
    role: str
    is_active: bool
    created_at: datetime | None = None
    last_login: datetime | None = None
