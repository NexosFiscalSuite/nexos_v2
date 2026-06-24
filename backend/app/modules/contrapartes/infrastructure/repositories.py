"""Repositório de contrapartes."""
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.contrapartes.infrastructure.models import Contraparte


class ContraparteRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, cid: UUID) -> Contraparte | None:
        return await self.session.get(Contraparte, cid)

    async def by_cnpj(self, empresa_id: UUID, tipo: str, cnpj: str) -> Contraparte | None:
        res = await self.session.execute(
            select(Contraparte).where(
                Contraparte.empresa_id == empresa_id,
                Contraparte.tipo == tipo,
                Contraparte.cnpj == cnpj,
            )
        )
        return res.scalar_one_or_none()

    async def list(self, empresa_id: UUID, tipo: str | None = None, search: str | None = None) -> list[Contraparte]:
        stmt = select(Contraparte).where(Contraparte.empresa_id == empresa_id)
        if tipo:
            stmt = stmt.where(Contraparte.tipo == tipo)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(
                Contraparte.cnpj.like(like),
                Contraparte.razao_social.ilike(like),
                Contraparte.nome_fantasia.ilike(like),
            ))
        res = await self.session.execute(stmt.order_by(Contraparte.razao_social))
        return list(res.scalars().all())

    def add(self, c: Contraparte) -> None:
        self.session.add(c)
