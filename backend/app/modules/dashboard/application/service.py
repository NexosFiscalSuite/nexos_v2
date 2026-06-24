"""Agregações para os dashboards (sob RLS — tudo já restrito ao tenant).

Tudo é calculado a partir de `notas` (e contagem de `empresas`). Sem novas tabelas.
"""
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.infrastructure.models import Empresa
from app.modules.fiscal.infrastructure.models import Nota

_FLUXO_COUNT = {
    "entradas": "entrada",
    "saidas": "saida",
    "servicos": "servico",
    "ctes": "cte",
}


def _f(v) -> float:
    return float(v or 0)


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def geral(self) -> dict:
        total_empresas = await self.session.scalar(select(func.count()).select_from(Empresa)) or 0
        rows = (
            await self.session.execute(
                select(
                    Nota.ano, Nota.mes,
                    func.count(Nota.id),
                    func.coalesce(func.sum(Nota.valor_total), 0),
                )
                .where(Nota.ano.isnot(None), Nota.ano != "")
                .group_by(Nota.ano, Nota.mes)
                .order_by(Nota.ano.desc(), Nota.mes.desc())
                .limit(12)
            )
        ).all()
        fiscal_mes = [
            {"mes": f"{ano}-{mes}", "notas": int(qtd), "valor": _f(valor)}
            for (ano, mes, qtd, valor) in rows
        ]
        return {"total_empresas": int(total_empresas), "fiscal_mes": fiscal_mes}

    async def empresa(self, empresa_id: UUID) -> dict:
        totais_row = (
            await self.session.execute(
                select(
                    func.count(Nota.id),
                    func.coalesce(func.sum(Nota.valor_total), 0),
                    func.sum(case((Nota.fluxo == "entrada", 1), else_=0)),
                    func.sum(case((Nota.fluxo == "saida", 1), else_=0)),
                    func.sum(case((Nota.fluxo == "servico", 1), else_=0)),
                    func.sum(case((Nota.fluxo == "cte", 1), else_=0)),
                    func.sum(case((Nota.status == "cancelada", 1), else_=0)),
                ).where(Nota.empresa_id == empresa_id)
            )
        ).one()
        totais = {
            "notas": int(totais_row[0] or 0),
            "valor": _f(totais_row[1]),
            "entradas": int(totais_row[2] or 0),
            "saidas": int(totais_row[3] or 0),
            "servicos": int(totais_row[4] or 0),
            "ctes": int(totais_row[5] or 0),
            "canceladas": int(totais_row[6] or 0),
        }
        rows = (
            await self.session.execute(
                select(
                    Nota.ano, Nota.mes,
                    func.count(Nota.id),
                    func.coalesce(func.sum(Nota.valor_total), 0),
                )
                .where(Nota.empresa_id == empresa_id, Nota.ano.isnot(None), Nota.ano != "")
                .group_by(Nota.ano, Nota.mes)
                .order_by(Nota.ano.desc(), Nota.mes.desc())
                .limit(12)
            )
        ).all()
        por_mes = [
            {"mes": f"{ano}-{mes}", "notas": int(qtd), "valor": _f(valor)}
            for (ano, mes, qtd, valor) in rows
        ]
        return {"totais": totais, "por_mes": por_mes}
