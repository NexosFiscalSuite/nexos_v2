"""Agregações para os dashboards (sob RLS — tudo já restrito ao tenant).

Tudo é calculado a partir de `notas` (e contagem de `empresas`). Sem novas tabelas.
"""
from uuid import UUID

from sqlalchemy import case, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cfop_rules.infrastructure.models import CfopRegra
from app.modules.companies.infrastructure.models import Empresa
from app.modules.fiscal.infrastructure.models import AuditoriaIcmsSt, Nota, NotaItem

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

    async def saude(self, ano: str, mes: str) -> list[dict]:
        """Saúde dos clientes na competência: por empresa, 4 indicadores —
        divergências de ST (erro do fornecedor × antecipação devida), gargalos
        (notas sem De/Para de CFOP), volume de XMLs e impacto financeiro (R$)."""
        n, a, it = Nota, AuditoriaIcmsSt, NotaItem
        empresas = (
            await self.session.execute(
                select(Empresa.id, Empresa.razao_social).order_by(Empresa.razao_social)
            )
        ).all()

        volume = {
            eid: int(q)
            for eid, q in (
                await self.session.execute(
                    select(n.empresa_id, func.count(n.id))
                    .where(n.ano == ano, n.mes == mes)
                    .group_by(n.empresa_id)
                )
            ).all()
        }

        # ERRO_111 = antecipação do destinatário; demais DIVERGENTE = erro do emissor.
        e_antecip = a.codigo_erro.like("%ERRO_111%")
        div = {
            eid: {"fornecedor": int(forn), "antecipacao": int(ante), "impacto": _f(imp)}
            for eid, ante, forn, imp in (
                await self.session.execute(
                    select(
                        a.empresa_id,
                        func.coalesce(func.sum(case((e_antecip, 1), else_=0)), 0),
                        func.coalesce(func.sum(case((e_antecip, 0), else_=1)), 0),
                        func.coalesce(func.sum(func.abs(a.vicms_st_divergencia)), 0),
                    )
                    .join(n, a.nota_id == n.id)
                    .where(a.status == "DIVERGENTE", n.ano == ano, n.mes == mes)
                    .group_by(a.empresa_id)
                )
            ).all()
        }

        # Gargalo: nota de ENTRADA com item cujo CFOP não tem regra De/Para (global).
        sem_regra = ~exists().where(CfopRegra.cfop_origem == it.cfop_original)
        gargalos = {
            eid: int(q)
            for eid, q in (
                await self.session.execute(
                    select(n.empresa_id, func.count(func.distinct(n.id)))
                    .join(it, it.nota_id == n.id)
                    .where(
                        n.fluxo == "entrada", n.ano == ano, n.mes == mes,
                        it.cfop_original.isnot(None), it.cfop_original != "", sem_regra,
                    )
                    .group_by(n.empresa_id)
                )
            ).all()
        }

        out = []
        for eid, razao in empresas:
            d = div.get(eid, {})
            out.append({
                "empresa_id": str(eid),
                "razao_social": razao,
                "volume_mes": volume.get(eid, 0),
                "divergencias_fornecedor": d.get("fornecedor", 0),
                "antecipacoes": d.get("antecipacao", 0),
                "gargalos_cfop": gargalos.get(eid, 0),
                "impacto_financeiro": d.get("impacto", 0.0),
            })
        return out

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
