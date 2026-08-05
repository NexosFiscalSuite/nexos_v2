"""Relatório de cobertura de matrizes: a fila de curadoria dirigida pelos dados.

Prova que os grupos NCM×CEST×UF da carteira são classificados contra as
matrizes VIGENTES e ordenados por valor — o topo da lista é o que mais gera
NAO_AUDITAVEL (ou TN silencioso) se ficar sem cadastro.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.cobertura_service import CoberturaService
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizMva,
)
from app.modules.fiscal.infrastructure.models import Nota, NotaItem

_TABELAS = [
    MatrizMva.__table__, MatrizEnquadramentoSt.__table__, MatrizAliquota.__table__,
    Nota.__table__, NotaItem.__table__,
]
_INICIO = date(2024, 1, 1)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _nota(tenant, empresa, uf: str, chave: str) -> Nota:
    return Nota(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa, chave_acesso=chave,
        tipo="NFe", fluxo="entrada", modelo="55", uf_dest=uf,
        data_emissao="2026-06-01", ano="2026", mes="06",
    )


def _item(tenant, nota: Nota, n: int, ncm: str, cest: str, valor: str) -> NotaItem:
    return NotaItem(
        id=uuid4(), tenant_id=tenant, nota_id=nota.id, numero_item=n,
        ncm=ncm, cest=cest, valor_produto=Decimal(valor),
    )


async def _cenario(s: AsyncSession):
    """MG: pneu coberto; cachaça ST sem MVA; NCM órfão sem enquadramento.
    BA: enquadrado ST mas a UF não tem alíquota vigente."""
    tenant, empresa = uuid4(), uuid4()
    s.add_all([
        MatrizEnquadramentoSt(uf_destino="MG", ncm="40111000", cest="0100500",
                              regime="ST", data_inicio_vigencia=_INICIO),
        MatrizMva(ncm="40111000", cest="0100500", uf_destino="MG",
                  mva_original=Decimal("42.00"), data_inicio_vigencia=_INICIO),
        MatrizAliquota(uf_destino="MG", aliq_modal=Decimal("18.00"),
                       aliq_fcp_integrado=Decimal("0"), data_inicio_vigencia=_INICIO),
        MatrizEnquadramentoSt(uf_destino="MG", ncm="22084000", cest="0202200",
                              regime="ST", data_inicio_vigencia=_INICIO),
        MatrizEnquadramentoSt(uf_destino="BA", ncm="40111000", cest="0100500",
                              regime="ST", data_inicio_vigencia=_INICIO),
    ])
    nota_mg = _nota(tenant, empresa, "MG", "1" * 44)
    nota_ba = _nota(tenant, empresa, "BA", "2" * 44)
    s.add_all([
        nota_mg, nota_ba,
        _item(tenant, nota_mg, 1, "40111000", "0100500", "1000"),   # OK
        _item(tenant, nota_mg, 2, "22084000", "0202200", "5000"),   # ST_SEM_MVA
        _item(tenant, nota_mg, 3, "99999999", "9999999", "8000"),   # SEM_ENQUADRAMENTO
        _item(tenant, nota_ba, 1, "40111000", "0100500", "3000"),   # SEM_ALIQUOTA
    ])
    await s.flush()
    return empresa


async def test_cobertura_classifica_e_prioriza_por_valor(sessao):
    await _cenario(sessao)

    r = await CoberturaService(sessao).cobertura()

    status_por_grupo = {(g["uf"], g["ncm"]): g["status"] for g in r["grupos"]}
    assert status_por_grupo[("MG", "40111000")] == "OK"
    assert status_por_grupo[("MG", "22084000")] == "ST_SEM_MVA"
    assert status_por_grupo[("MG", "99999999")] == "SEM_ENQUADRAMENTO"
    assert status_por_grupo[("BA", "40111000")] == "SEM_ALIQUOTA"

    # Fila de curadoria: maior valor descoberto primeiro (8000 > 5000 > 3000 > 1000).
    assert [g["valor"] for g in r["grupos"]] == [8000.0, 5000.0, 3000.0, 1000.0]
    assert r["grupos"][0]["status"] == "SEM_ENQUADRAMENTO"

    # Resumo: só o pneu MG (1000 de 17000) está coberto → 5,9%.
    assert r["resumo"]["grupos"] == 4
    assert r["resumo"]["valor_total"] == 17000.0
    assert r["resumo"]["pct_valor_coberto"] == 5.9
    assert r["resumo"]["por_status"]["SEM_ENQUADRAMENTO"]["valor"] == 8000.0


async def test_cobertura_respeita_vigencia_e_filtro_uf(sessao):
    await _cenario(sessao)

    # Filtro por UF: só os grupos de MG.
    r_mg = await CoberturaService(sessao).cobertura(uf="MG")
    assert {g["uf"] for g in r_mg["grupos"]} == {"MG"}

    # Encerrando a MVA do pneu ANTES da emissão (2026-06-01), o grupo que era OK
    # passa a ST_SEM_MVA — a classificação usa a matriz vigente na data, não a atual.
    from sqlalchemy import update
    await sessao.execute(update(MatrizMva).values(data_fim_vigencia=date(2026, 5, 31)))
    r2 = await CoberturaService(sessao).cobertura(uf="MG")
    status = {g["ncm"]: g["status"] for g in r2["grupos"]}
    assert status["40111000"] == "ST_SEM_MVA"


async def test_cobertura_pagina_sem_truncar_o_resumo(sessao):
    await _cenario(sessao)

    primeira = await CoberturaService(sessao).cobertura(page=1, page_size=2)
    segunda = await CoberturaService(sessao).cobertura(page=2, page_size=2)

    assert primeira["total"] == 4
    assert primeira["total_pages"] == 2
    assert primeira["page"] == 1
    assert primeira["page_size"] == 2
    assert [g["valor"] for g in primeira["grupos"]] == [8000.0, 5000.0]
    assert [g["valor"] for g in segunda["grupos"]] == [3000.0, 1000.0]
    # Cards e percentuais continuam representando toda a carteira, não só a página.
    assert primeira["resumo"]["grupos"] == 4
    assert primeira["resumo"]["valor_total"] == 17000.0
