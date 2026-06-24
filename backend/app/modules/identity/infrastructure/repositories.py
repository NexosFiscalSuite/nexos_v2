"""Repositórios do Identity. Encapsulam o acesso a dados (SQLAlchemy async).

Recebem a session por injeção — quem decide se é a session RLS (tenant_session)
ou a privilegiada (auth/signup) é a camada de cima.
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.modules.identity.infrastructure.models import (
    Plan,
    RefreshToken,
    Tenant,
    User,
)


class PlanRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_code(self, code: str) -> Plan | None:
        res = await self.session.execute(select(Plan).where(Plan.code == code))
        return res.scalar_one_or_none()


class TenantRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, tenant_id: UUID) -> Tenant | None:
        # eager-load do plan: login/refresh leem tenant.plan.code; sem isso o
        # acesso ao relacionamento dispara lazy-load (proibido em async).
        res = await self.session.execute(
            select(Tenant).options(joinedload(Tenant.plan)).where(Tenant.id == tenant_id)
        )
        return res.scalar_one_or_none()

    async def by_cnpj(self, cnpj: str) -> Tenant | None:
        res = await self.session.execute(select(Tenant).where(Tenant.cnpj == cnpj))
        return res.scalar_one_or_none()

    async def by_slug(self, slug: str) -> Tenant | None:
        res = await self.session.execute(select(Tenant).where(Tenant.slug == slug))
        return res.scalar_one_or_none()

    def add(self, tenant: Tenant) -> None:
        self.session.add(tenant)


class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, user_id: UUID) -> User | None:
        return await self.session.get(User, user_id)

    async def by_email(self, tenant_id: UUID, email: str) -> User | None:
        res = await self.session.execute(
            select(User).where(User.tenant_id == tenant_id, User.email == email)
        )
        return res.scalar_one_or_none()

    async def list_by_email_global(self, email: str) -> list[User]:
        """Busca por e-mail em TODOS os tenants. Só faz sentido na session
        privilegiada (login), antes de existir contexto de tenant."""
        res = await self.session.execute(select(User).where(User.email == email))
        return list(res.scalars().all())

    async def list_by_tenant(self, tenant_id: UUID) -> list[User]:
        res = await self.session.execute(
            select(User).where(User.tenant_id == tenant_id).order_by(User.full_name)
        )
        return list(res.scalars().all())

    def add(self, user: User) -> None:
        self.session.add(user)

    async def touch_last_login(self, user: User) -> None:
        user.last_login = datetime.now(UTC)


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_jti(self, jti: UUID) -> RefreshToken | None:
        res = await self.session.execute(
            select(RefreshToken).where(RefreshToken.jti == jti)
        )
        return res.scalar_one_or_none()

    def add(self, token: RefreshToken) -> None:
        self.session.add(token)
