"""Repositório das regras De/Para CFOP."""
import re
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cfop_rules.infrastructure.models import CfopRegra


def norm_cfop(cfop: str) -> str:
    return re.sub(r"\D", "", cfop or "")


class CfopRegraRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, rid: UUID) -> CfopRegra | None:
        return await self.session.get(CfopRegra, rid)

    async def by_origem(self, cfop_origem: str) -> CfopRegra | None:
        res = await self.session.execute(
            select(CfopRegra).where(CfopRegra.cfop_origem == norm_cfop(cfop_origem))
        )
        return res.scalar_one_or_none()

    async def list(self) -> list[CfopRegra]:
        res = await self.session.execute(select(CfopRegra).order_by(CfopRegra.cfop_origem))
        return list(res.scalars().all())

    async def as_map(self) -> dict[str, CfopRegra]:
        """{cfop_origem -> regra} para lookup rápido na importação."""
        return {r.cfop_origem: r for r in await self.list()}

    def add(self, regra: CfopRegra) -> None:
        self.session.add(regra)
