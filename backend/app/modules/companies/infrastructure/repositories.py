"""Repositório de empresas."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.infrastructure.models import Empresa


class EmpresaRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, empresa_id: UUID) -> Empresa | None:
        return await self.session.get(Empresa, empresa_id)

    async def by_cnpj(self, tenant_id: UUID, cnpj: str) -> Empresa | None:
        res = await self.session.execute(
            select(Empresa).where(Empresa.tenant_id == tenant_id, Empresa.cnpj == cnpj)
        )
        return res.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: UUID) -> list[Empresa]:
        res = await self.session.execute(
            select(Empresa).where(Empresa.tenant_id == tenant_id).order_by(Empresa.razao_social)
        )
        return list(res.scalars().all())

    async def list_by_ids(self, tenant_id: UUID, ids) -> list[Empresa]:
        res = await self.session.execute(
            select(Empresa)
            .where(Empresa.tenant_id == tenant_id, Empresa.id.in_(list(ids)))
            .order_by(Empresa.razao_social)
        )
        return list(res.scalars().all())

    def add(self, empresa: Empresa) -> None:
        self.session.add(empresa)
