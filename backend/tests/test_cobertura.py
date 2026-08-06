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


def _nota(tenant, empresa, uf: str, chave: str, uf_emit: str | None = None) -> Nota:
    return Nota(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa, chave_acesso=chave,
        tipo="NFe", fluxo="entrada", modelo="55", uf_dest=uf, uf_emit=uf_emit,
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


async def _cenario_lacunas(sessao: AsyncSession):
    """MG comprando de SP e de MG:
      · pneu  — MVA curinga na matriz → coberto venha de onde vier;
      · autopeça — MVA só para origem SP → a compra INTERNA (MG) é lacuna;
      · cachaça — ST sem MVA nenhuma → lacuna;
      · fralda — TN (não consome MVA) → fora da fila;
      · NCM órfão — sem enquadramento → só contado no resumo."""
    tenant, empresa = uuid4(), uuid4()
    sessao.add_all([
        MatrizAliquota(uf_destino="MG", aliq_modal=Decimal("18.00"),
                       data_inicio_vigencia=_INICIO),
        MatrizEnquadramentoSt(uf_destino="MG", ncm="40111000", cest="0100500",
                              regime="ST", data_inicio_vigencia=_INICIO),
        MatrizMva(ncm="40111000", cest="0100500", uf_origem="*", uf_destino="MG",
                  mva_original=Decimal("42.00"), data_inicio_vigencia=_INICIO),
        MatrizEnquadramentoSt(uf_destino="MG", ncm="87082919", cest="0107500",
                              regime="ST", data_inicio_vigencia=_INICIO),
        MatrizMva(ncm="87082919", cest="0107500", uf_origem="SP", uf_destino="MG",
                  mva_original=Decimal("71.78"), data_inicio_vigencia=_INICIO),
        MatrizEnquadramentoSt(uf_destino="MG", ncm="22084000", cest="0202200",
                              regime="ST", data_inicio_vigencia=_INICIO),
        MatrizEnquadramentoSt(uf_destino="MG", ncm="48181000", cest="",
                              regime="TN", data_inicio_vigencia=_INICIO),
    ])
    de_sp = _nota(tenant, empresa, "MG", "1" * 44, uf_emit="SP")
    de_mg = _nota(tenant, empresa, "MG", "2" * 44, uf_emit="MG")
    sessao.add_all([
        de_sp, de_mg,
        _item(tenant, de_sp, 1, "40111000", "0100500", "1000"),   # coberto (curinga)
        _item(tenant, de_sp, 2, "87082919", "0107500", "2000"),   # coberto (origem SP)
        _item(tenant, de_sp, 3, "22084000", "0202200", "5000"),   # LACUNA SP→MG
        _item(tenant, de_mg, 1, "87082919", "0107500", "9000"),   # LACUNA MG→MG
        _item(tenant, de_mg, 2, "48181000", "", "7000"),          # TN: fora
        _item(tenant, de_mg, 3, "99999999", "9999999", "8000"),   # sem enquadramento
    ])
    await sessao.flush()
    return empresa


async def test_lacunas_mva_lista_o_par_origem_destino_por_impacto(sessao):
    await _cenario_lacunas(sessao)

    r = await CoberturaService(sessao).lacunas_mva()

    chaves = [(g["uf_origem"], g["uf_destino"], g["ncm"], g["valor"]) for g in r["lacunas"]]
    assert chaves == [
        ("MG", "MG", "87082919", 9000.0),    # interna: a MVA cadastrada é só de SP
        ("SP", "MG", "22084000", 5000.0),    # nenhuma MVA para o par
    ]
    assert all(g["motivo"] == "SEM_MVA" and g["regime"] == "ST" for g in r["lacunas"])

    # TN e itens cobertos ficam fora; o sem-enquadramento só é CONTADO.
    assert r["total"] == 2
    assert r["resumo"]["valor"] == 14000.0
    assert r["resumo"]["cobertos"] == {"grupos": 2, "valor": 3000.0}
    assert r["resumo"]["sem_enquadramento"] == {"grupos": 1, "valor": 8000.0}
    assert r["resumo"]["por_uf"]["MG"] == {"lacunas": 2, "itens": 2, "valor": 14000.0}
    # 14000 dos 17000 avaliados (só ST/ST_ENTRADA) estão sem MVA.
    assert r["resumo"]["pct_valor_sem_mva"] == 82.4


async def test_lacunas_mva_incluindo_o_que_nem_tem_enquadramento(sessao):
    await _cenario_lacunas(sessao)

    r = await CoberturaService(sessao).lacunas_mva(incluir_sem_enquadramento=True)

    orfao = next(g for g in r["lacunas"] if g["ncm"] == "99999999")
    assert orfao["motivo"] == "SEM_ENQUADRAMENTO" and orfao["regime"] is None
    assert r["lacunas"][0]["valor"] == 9000.0        # ordem por dinheiro continua


async def test_lacunas_mva_saem_no_layout_do_importador_sem_valor_preenchido(sessao):
    """O CSV baixado sobe de volta pelo Importar planilha: o usuário preenche
    SÓ a coluna de MVA. Nenhuma margem é sugerida pelo sistema."""
    await _cenario_lacunas(sessao)

    csv_txt = await CoberturaService(sessao).lacunas_mva_csv()

    linhas = csv_txt.strip().split("\n")
    assert linhas[0] == (
        "ncm;cest;uf_origem;uf_destino;mva_original;base_legal;"
        "data_inicio_vigencia;data_fim_vigencia"
    )
    assert linhas[1] == "87082919;0107500;MG;MG;;;2026-06-01;"
    assert linhas[2] == "22084000;0202200;SP;MG;;;2026-06-01;"
    assert len(linhas) == 3


async def test_lacunas_mva_sem_uf_de_emitente_so_e_coberta_por_regra_geral(sessao):
    """Nota sem UF do emitente entra como curinga: uma MVA específica de SP não
    a cobre (não se sabe de onde veio) — a lacuna aparece, fail-closed."""
    tenant, empresa = uuid4(), uuid4()
    sessao.add_all([
        MatrizEnquadramentoSt(uf_destino="MG", ncm="87082919", cest="0107500",
                              regime="ST", data_inicio_vigencia=_INICIO),
        MatrizMva(ncm="87082919", cest="0107500", uf_origem="SP", uf_destino="MG",
                  mva_original=Decimal("71.78"), data_inicio_vigencia=_INICIO),
    ])
    sem_emit = _nota(tenant, empresa, "MG", "3" * 44)
    sessao.add_all([sem_emit, _item(tenant, sem_emit, 1, "87082919", "0107500", "400")])
    await sessao.flush()

    r = await CoberturaService(sessao).lacunas_mva()
    assert [g["uf_origem"] for g in r["lacunas"]] == ["*"]


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


# ── Contrato de rota com o front ─────────────────────────────────────────────
def test_rotas_de_lacunas_mva_registradas():
    """Sem elas o relatório de lacunas é código morto: a tela não o alcança."""
    from app.modules.fiscal.api.matrizes_routers import router

    caminhos = {r.path for r in router.routes}
    assert "/matrizes/lacunas-mva" in caminhos
    assert "/matrizes/lacunas-mva/export" in caminhos


def test_export_de_lacunas_sai_no_layout_do_import_da_mva():
    """O CSV baixado tem que subir de volta sem o usuário mexer em coluna: as
    colunas são as MESMAS que o bulk da MVA espera, na mesma ordem."""
    from app.modules.fiscal.api.matrizes_bulk import MATRIZES
    from app.modules.fiscal.application.cobertura_service import COLUNAS_CSV_MVA

    assert list(COLUNAS_CSV_MVA) == MATRIZES["mva"].colunas
