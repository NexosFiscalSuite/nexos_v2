"""Modelos ORM do bounded context Identity: Plan, Tenant, User, RefreshToken.

Convenções multi-tenant:
* PKs são UUID (evita enumeração de IDs entre tenants).
* Toda tabela tenant-scoped tem `tenant_id` (alvo do RLS). `plans` é dado de
  referência global (sem tenant_id, sem RLS).
* `users` e `refresh_tokens` ganham FK explícita para o tenant.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(80))
    rate_limit_per_min: Mapped[int] = mapped_column(Integer, default=120)
    max_empresas: Mapped[int] = mapped_column(Integer, default=5)
    max_users: Mapped[int] = mapped_column(Integer, default=3)
    price_cents: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Tenant(Base):
    """Escritório contábil = cliente pagante do SaaS. É a raiz do isolamento."""

    __tablename__ = "tenants"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    cnpj: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    razao_social: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(60), unique=True, index=True)
    plan_id: Mapped[UUID] = mapped_column(ForeignKey("plans.id"))
    status: Mapped[str] = mapped_column(String(20), default="trial")  # trial|active|suspended
    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    plan: Mapped[Plan] = relationship(lazy="joined")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(String(255), index=True)
    full_name: Mapped[str] = mapped_column(String(200))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="user")  # admin|supervisor|user
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RefreshToken(Base):
    """Refresh tokens persistidos (hash) para rotação e revogação."""

    __tablename__ = "refresh_tokens"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    jti: Mapped[UUID] = mapped_column(Uuid, unique=True, index=True)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(255))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
