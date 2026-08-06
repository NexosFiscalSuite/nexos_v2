"""MVA aprendida das próprias notas: vira PROPOSTA, nunca linha na matriz.

O que estes testes travam (nesta ordem de importância):

1. **Só aprende onde o `pMVAST` É a MVA original por lei** — operação interna
   ou emitente do Simples. Interestadual com emitente do regime normal declara
   a MVA AJUSTADA; aprender dali cadastraria margem errada em escala.
2. Independência acima de volume: 1 fornecedor com 50 notas não faz consenso.
3. Ambiguidade não vira palpite (fail-closed).
4. Curadoria já feita nunca é desafiada — nem pelo NCM de 4 dígitos.
5. Rejeitar uma sugestão vale para sempre (supressão por hash).
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.api.matrizes_routers import router as matrizes_router
from app.modules.fiscal.application.mva_aprendida import (
    FONTE_APRENDIDA,
    gerar_propostas_mva_aprendida,
    levantar_mva_aprendida,
    previa_mva_aprendida,
)
from app.modules.fiscal.application.propostas_service import PropostasService
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.modules.fiscal.infrastructure.models import Nota, NotaItem
from app.modules.fiscal.infrastructure.propostas_models import (
    FonteSnapshot,
    MatrizProposta,
)

_TABELAS = [
    Nota.__table__, NotaItem.__table__, MatrizMva.__table__,
    FonteSnapshot.__table__, MatrizProposta.__table__,
]
TENANT, EMPRESA = uuid4(), uuid4()
NCM, CEST = "40111000", "0100500"


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


_seq = iter(range(1, 10_000))


def _nota(*, uf_emit: str, uf_dest: str = "MG", cnpj: str, crt: str = "3",
          emissao: str = "2026-06-15") -> Nota:
    n = next(_seq)
    return Nota(
        id=uuid4(), tenant_id=TENANT, empresa_id=EMPRESA,
        chave_acesso=f"{n:044d}", tipo="NFe", fluxo="entrada", modelo="55",
        status="ativa", cnpj_emit=cnpj, uf_emit=uf_emit, uf_dest=uf_dest,
        crt_emit=crt, data_emissao=emissao, ano=emissao[:4], mes=emissao[5:7],
    )


def _item(nota: Nota, mva: str, *, ncm: str = NCM, cest: str = CEST,
          valor: str = "1000", mod_bc_st: int | None = 4) -> NotaItem:
    return NotaItem(
        id=uuid4(), tenant_id=TENANT, nota_id=nota.id, numero_item=1,
        ncm=ncm, cest=cest, descricao="Pneu novo", valor_produto=Decimal(valor),
        mod_bc_st=mod_bc_st, p_mva_st=Decimal(mva),
    )


async def _povoar(s: AsyncSession, notas_e_mvas, **kw) -> None:
    """[(cnpj, mva)] → uma nota de entrada por par, todas na mesma chave."""
    for cnpj, mva in notas_e_mvas:
        nota = _nota(cnpj=cnpj, **kw)
        s.add_all([nota, _item(nota, mva)])
    await s.flush()


# ── o coração: onde o declarado É a original ────────────────────────────────
async def test_tres_fornecedores_internos_viram_uma_proposta_sem_tocar_a_matriz(sessao):
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.00"), ("3" * 14, "42.00")],
                  uf_emit="MG")

    r = await gerar_propostas_mva_aprendida(sessao)
    assert r["criadas"] == 1 and r["fonte"] == FONTE_APRENDIDA

    # A matriz continua VAZIA — dado aprendido nunca entra sozinho.
    assert (await sessao.execute(select(MatrizMva))).scalars().all() == []

    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    assert (p.tipo_matriz, p.acao, p.fonte) == ("mva", "INSERIR", FONTE_APRENDIDA)
    assert p.payload["mva_original"] == "42.00"
    assert p.payload["uf_origem"] == "MG" and p.payload["uf_destino"] == "MG"
    # base_legal VAZIA: número aprendido não tem norma, e esse campo sai nas cartas.
    assert p.payload["base_legal"] is None
    assert p.evidencia["fornecedores"] == 3 and p.evidencia["notas"] == 3
    assert len(p.evidencia["cnpjs_amostra"]) == 3
    assert "interna" in p.evidencia["por_que_e_original"]
    assert "MG → MG" in p.chave_resumo


async def test_interestadual_de_emitente_normal_nao_e_aprendido(sessao):
    """SP→MG com CRT 3: o pMVAST declarado é a MVA AJUSTADA, não a original."""
    await _povoar(sessao, [("1" * 14, "50.00"), ("2" * 14, "50.00"), ("3" * 14, "50.00")],
                  uf_emit="SP", crt="3")

    candidatos, resumo = await levantar_mva_aprendida(sessao)
    assert candidatos == [] and resumo["grupos_avaliados"] == 0


async def test_interestadual_do_simples_e_aprendido(sessao):
    """SP→MG com CRT 1/4: o Simples não ajusta (Conv. 142/2018) → é a original."""
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.00")],
                  uf_emit="SP", crt="1")
    nota = _nota(uf_emit="SP", cnpj="4" * 14, crt="4")     # MEI também não ajusta
    sessao.add_all([nota, _item(nota, "42.00")])
    await sessao.flush()

    candidatos, _ = await levantar_mva_aprendida(sessao)
    assert len(candidatos) == 1
    assert candidatos[0]["uf_origem"] == "SP" and candidatos[0]["elegibilidade"] == "simples"
    assert "Simples" in candidatos[0]["evidencia"]["por_que_e_original"]


# ── as travas do consenso ───────────────────────────────────────────────────
async def test_volume_de_um_unico_fornecedor_nao_faz_consenso(sessao):
    await _povoar(sessao, [("1" * 14, "42.00")] * 50, uf_emit="MG")

    candidatos, resumo = await levantar_mva_aprendida(sessao)
    assert candidatos == [] and resumo["sem_consenso"] == 1


async def test_dois_valores_com_apoio_relevante_sao_ambiguidade(sessao):
    await _povoar(
        sessao,
        [("1" * 14, "42.00"), ("2" * 14, "42.00"), ("3" * 14, "42.00"),
         ("4" * 14, "55.00"), ("5" * 14, "55.00")],
        uf_emit="MG",
    )

    candidatos, resumo = await levantar_mva_aprendida(sessao)
    assert candidatos == [] and resumo["ambiguos"] == 1


async def test_valor_isolado_nao_derruba_o_consenso(sessao):
    await _povoar(
        sessao,
        [("1" * 14, "42.00"), ("2" * 14, "42.00"), ("3" * 14, "42.00"), ("4" * 14, "55.00")],
        uf_emit="MG",
    )

    candidatos, _ = await levantar_mva_aprendida(sessao)
    assert len(candidatos) == 1 and candidatos[0]["mva_original"] == "42.00"
    distribuicao = candidatos[0]["evidencia"]["distribuicao"]
    assert {d["mva"]: d["escolhido"] for d in distribuicao} == {"42.00": True, "55.00": False}


async def test_tolerancia_de_um_centesimo_junta_o_mesmo_numero(sessao):
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.01"), ("3" * 14, "42.00")],
                  uf_emit="MG")

    candidatos, _ = await levantar_mva_aprendida(sessao)
    assert len(candidatos) == 1 and candidatos[0]["fornecedores"] == 3
    assert candidatos[0]["mva_original"] == "42.00"       # o mais apoiado vence


async def test_minimo_de_fornecedores_e_parametro(sessao):
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.00")], uf_emit="MG")

    candidatos_3, _ = await levantar_mva_aprendida(sessao)
    candidatos_2, _ = await levantar_mva_aprendida(sessao, min_fornecedores=2)
    assert candidatos_3 == [] and len(candidatos_2) == 1


async def test_item_sem_base_por_mva_e_ignorado(sessao):
    """modBCST 6 (valor da operação) não declara margem original nenhuma."""
    for cnpj in ("1" * 14, "2" * 14, "3" * 14):
        nota = _nota(uf_emit="MG", cnpj=cnpj)
        sessao.add_all([nota, _item(nota, "42.00", mod_bc_st=6)])
    await sessao.flush()

    candidatos, _ = await levantar_mva_aprendida(sessao)
    assert candidatos == []


# ── nunca competir com curadoria já feita ───────────────────────────────────
async def test_linha_vigente_na_matriz_bloqueia_a_proposta(sessao):
    sessao.add(MatrizMva(
        ncm="4011", cest=CEST, uf_origem="*", uf_destino="MG",
        mva_original=Decimal("38.00"), data_inicio_vigencia=date(2024, 1, 1),
    ))
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.00"), ("3" * 14, "42.00")],
                  uf_emit="MG")

    candidatos, resumo = await levantar_mva_aprendida(sessao)
    # Casou pelo NCM de 4 dígitos e pelo curinga de origem, como o motor faz.
    assert candidatos == [] and resumo["ja_cobertos"] == 1


async def test_linha_encerrada_antes_do_periodo_nao_bloqueia(sessao):
    sessao.add(MatrizMva(
        ncm=NCM, cest=CEST, uf_origem="*", uf_destino="MG",
        mva_original=Decimal("38.00"), data_inicio_vigencia=date(2020, 1, 1),
        data_fim_vigencia=date(2023, 12, 31),
    ))
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.00"), ("3" * 14, "42.00")],
                  uf_emit="MG")

    candidatos, _ = await levantar_mva_aprendida(sessao)
    assert len(candidatos) == 1


# ── fila: vigência, prévia e supressão ──────────────────────────────────────
async def test_vigencia_e_o_primeiro_dia_do_mes_da_nota_mais_antiga(sessao):
    await _povoar(sessao, [("1" * 14, "42.00")], uf_emit="MG", emissao="2026-03-20")
    await _povoar(sessao, [("2" * 14, "42.00"), ("3" * 14, "42.00")],
                  uf_emit="MG", emissao="2026-06-15")

    candidatos, _ = await levantar_mva_aprendida(sessao)
    assert candidatos[0]["data_inicio_vigencia"] == "2026-03-01"
    assert candidatos[0]["evidencia"]["periodo"] == {
        "primeira_emissao": "2026-03-20", "ultima_emissao": "2026-06-15",
    }


async def test_previa_nao_grava_nada_e_pagina(sessao):
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.00"), ("3" * 14, "42.00")],
                  uf_emit="MG")

    r = await previa_mva_aprendida(sessao, page=1, page_size=10)
    assert r["total"] == 1 and r["total_pages"] == 1 and r["page_size"] == 10
    assert r["propostas"][0]["ja_na_fila"] is False
    assert (await sessao.execute(select(MatrizProposta))).scalars().all() == []


async def test_rejeitar_suprime_a_reproposta_para_sempre(sessao):
    await _povoar(sessao, [("1" * 14, "42.00"), ("2" * 14, "42.00"), ("3" * 14, "42.00")],
                  uf_emit="MG")
    assert (await gerar_propostas_mva_aprendida(sessao))["criadas"] == 1

    # Rodar de novo com a proposta PENDENTE não duplica.
    assert (await gerar_propostas_mva_aprendida(sessao))["suprimidas"] == 1

    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    await PropostasService(sessao).rejeitar(p.id, revisor="ana@sol.com", motivo="MVA errada")

    r = await gerar_propostas_mva_aprendida(sessao)
    assert r["criadas"] == 0 and r["suprimidas"] == 1


async def test_endpoints_registrados():
    caminhos = {r.path for r in matrizes_router.routes}
    assert "/matrizes/mva-aprendida" in caminhos
    metodos = {
        m for r in matrizes_router.routes
        if r.path == "/matrizes/mva-aprendida" for m in r.methods
    }
    assert {"GET", "POST"} <= metodos


def test_resposta_da_fila_carrega_a_evidencia():
    """Contrato com a tela: sem `evidencia` na resposta, a aba Revisão mostraria
    a MVA aprendida como qualquer outra proposta e o curador aprovaria um
    número sem saber quantos fornecedores o sustentam."""
    from app.modules.fiscal.api.propostas_routers import PropostaResponse

    assert "evidencia" in PropostaResponse.model_fields
    assert PropostaResponse.model_config.get("from_attributes") is True
