"""Repositório de contrapartes."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, or_, select
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

    async def list(
        self, empresa_id: UUID, tipo: str | None = None, search: str | None = None,
        page: int = 1, page_size: int = 25,
    ) -> tuple[list[Contraparte], int]:
        """Página de contrapartes + total do filtro. Uma empresa acumula
        milhares de fornecedores (upsert dos XMLs) — a lista nunca vem inteira."""
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
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        ) or 0
        res = await self.session.execute(
            stmt.order_by(Contraparte.razao_social)
            .offset((page - 1) * page_size).limit(page_size)
        )
        return list(res.scalars().all()), total

    async def sem_regime(self, empresa_id: UUID) -> list[Contraparte]:
        """Contrapartes ainda sem regime definido — candidatas à consulta optante."""
        res = await self.session.execute(
            select(Contraparte).where(
                Contraparte.empresa_id == empresa_id,
                or_(Contraparte.regime.is_(None), Contraparte.regime == ""),
            )
        )
        return list(res.scalars().all())

    def add(self, c: Contraparte) -> None:
        self.session.add(c)
