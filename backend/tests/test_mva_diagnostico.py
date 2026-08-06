"""Diagnóstico da MVA: dizer o que EXISTE na matriz e por que não casou.

O caso que motivou isto (nota 350735, agosto/2026): o João carregou o Anexo VII
inteiro — milhares de linhas — e o motor continuou calculando sem margem. A
mensagem "não há MVA cadastrada para NCM/CEST/UF na data" não distingue matriz
vazia de matriz cheia com vigência futura, nem de âmbito que não alcança o
estado do fornecedor. Cada veredicto abaixo é uma dessas conversas.

O último teste é a trava mais importante: o diagnóstico e o `_MvaSnapshot` do
motor têm de concordar sempre.
"""
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.exceptions import DomainError
from app.modules.fiscal.application.mva_diagnostico import diagnosticar_mva
from app.modules.fiscal.infrastructure.matrizes_loaders import (
    montar_mva_snapshot,
    stmt_mva_do_motor,
)
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.modules.fiscal.infrastructure.propostas_models import MatrizProposta

D = Decimal
NCM, CEST = "85444900", "1200700"          # o item da nota 350735
PISO = date(2026, 6, 1)                    # vigência-piso da carga do Anexo VII
ANTES = date(2026, 5, 10)                  # emissão anterior ao piso
DEPOIS = date(2026, 6, 20)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        # A fila entra junto: o diagnóstico também conta as propostas ainda
        # PENDENTES do produto — é o que separa "não existe regra" de "a regra
        # está esperando aprovação na aba Revisão".
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[MatrizMva.__table__, MatrizProposta.__table__],
        )
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _mva(**kw) -> MatrizMva:
    base = dict(
        ncm=NCM, cest=CEST, uf_origem="*", uf_destino="MG",
        mva_original=D("42.00"), data_inicio_vigencia=PISO,
        base_legal="RICMS/MG Anexo VII",
    )
    base.update(kw)
    return MatrizMva(**base)


async def _diag(sessao, **kw) -> dict:
    padrao = dict(ncm=NCM, cest=CEST, uf_origem="SP", uf_destino="MG", data=DEPOIS)
    padrao.update(kw)
    return await diagnosticar_mva(sessao, **padrao)


# ── ENCONTRADA ────────────────────────────────────────────────────────────── #
async def test_encontrada_traz_a_linha_aplicada(sessao):
    sessao.add(_mva())
    await sessao.flush()

    r = await _diag(sessao)

    assert r["veredicto"] == "ENCONTRADA"
    assert r["aplicada"]["mva_original"] == "42.00"
    assert r["aplicada"]["uf_origem"] == "*"
    assert r["aplicada"]["data_inicio_vigencia"] == "2026-06-01"
    assert r["aplicada"]["base_legal"] == "RICMS/MG Anexo VII"
    assert "42.00%" in r["explicacao"]
    # A linha aplicada também aparece nas candidatas, marcada e em primeiro lugar.
    assert r["candidatas"][0]["casou"] is True
    assert r["consulta"] == {
        "ncm": NCM, "cest": CEST, "uf_origem": "SP",
        "uf_destino": "MG", "data": "2026-06-20",
    }


async def test_origem_exata_vence_curinga_e_a_perdedora_explica_por_que(sessao):
    sessao.add_all([_mva(mva_original=D("42.00")),
                    _mva(uf_origem="SP", mva_original=D("58.00"))])
    await sessao.flush()

    r = await _diag(sessao)

    assert r["veredicto"] == "ENCONTRADA"
    assert r["aplicada"]["uf_origem"] == "SP"
    perdedora = next(c for c in r["candidatas"] if c["uf_origem"] == "*")
    assert perdedora["casou"] is False
    assert "precedência" in perdedora["motivo"]


# ── SEM_LINHA_NENHUMA ─────────────────────────────────────────────────────── #
async def test_matriz_vazia_para_o_ncm(sessao):
    sessao.add(_mva(ncm="22030000", cest="0300100"))    # outro produto
    await sessao.flush()

    r = await _diag(sessao)

    assert r["veredicto"] == "SEM_LINHA_NENHUMA"
    assert r["aplicada"] is None
    assert r["candidatas"] == []
    assert NCM in r["explicacao"]
    assert "854449" in r["explicacao"] and "8544" in r["explicacao"]   # a escada 8→6→4


# ── FORA_DA_VIGENCIA (a hipótese nº 1 do caso real) ───────────────────────── #
async def test_linhas_existem_mas_so_valem_depois_da_emissao(sessao):
    """Matriz CHEIA e motor sem margem: a carga do Anexo VII entrou com
    vigência-piso 01/06/2026 e a nota é de maio."""
    sessao.add_all([
        _mva(uf_origem="SP", mva_original=D("58.00")),
        _mva(uf_origem="RJ", mva_original=D("53.00")),
        _mva(mva_original=D("42.00")),
    ])
    await sessao.flush()

    r = await _diag(sessao, data=ANTES)

    assert r["veredicto"] == "FORA_DA_VIGENCIA"
    assert r["aplicada"] is None
    # A data a partir da qual as linhas valem SALTA aos olhos.
    assert "01/06/2026" in r["explicacao"]
    assert "10/05/2026" in r["explicacao"]
    assert len(r["candidatas"]) == 3
    assert all(c["casou"] is False for c in r["candidatas"])
    assert all("01/06/2026" in c["motivo"] for c in r["candidatas"])
    assert "vigência" in r["acao_sugerida"].lower()


async def test_linhas_encerradas_antes_da_emissao(sessao):
    sessao.add(_mva(
        uf_origem="SP", data_inicio_vigencia=date(2024, 1, 1),
        data_fim_vigencia=date(2025, 12, 31),
    ))
    await sessao.flush()

    r = await _diag(sessao)

    assert r["veredicto"] == "FORA_DA_VIGENCIA"
    assert "31/12/2025" in r["explicacao"]
    assert "terminou" in r["candidatas"][0]["motivo"]


# ── ORIGEM_NAO_COBERTA (a hipótese nº 2) ──────────────────────────────────── #
async def test_so_ha_linha_para_sp_e_a_nota_veio_do_rj(sessao):
    sessao.add(_mva(uf_origem="SP", mva_original=D("58.00")))
    await sessao.flush()

    r = await _diag(sessao, uf_origem="RJ")

    assert r["veredicto"] == "ORIGEM_NAO_COBERTA"
    assert r["aplicada"] is None
    assert "SP" in r["explicacao"]          # quais origens EXISTEM
    assert "RJ" in r["explicacao"]
    assert r["candidatas"][0]["casou"] is False
    assert "vale só para a origem SP" in r["candidatas"][0]["motivo"]


async def test_sem_uf_de_origem_so_o_curinga_conta(sessao):
    sessao.add(_mva(uf_origem="SP"))
    await sessao.flush()

    r = await _diag(sessao, uf_origem=None)

    assert r["veredicto"] == "ORIGEM_NAO_COBERTA"
    assert r["consulta"]["uf_origem"] == "*"
    assert "não informou a UF de origem" in r["explicacao"]


# ── CEST_NAO_BATE ─────────────────────────────────────────────────────────── #
async def test_ncm_cadastrado_com_outro_cest(sessao):
    sessao.add(_mva(cest="1200800", uf_origem="SP"))
    await sessao.flush()

    r = await _diag(sessao)

    assert r["veredicto"] == "CEST_NAO_BATE"
    assert "1200800" in r["explicacao"] and CEST in r["explicacao"]
    assert "CEST" in r["candidatas"][0]["motivo"]


# ── AMBIGUA ───────────────────────────────────────────────────────────────── #
async def test_item_sem_cest_com_margens_diferentes_trava(sessao):
    """Fail-closed: sem CEST no XML e duas margens no mesmo NCM, o motor não
    escolhe — e o diagnóstico diz quais são as margens em conflito."""
    sessao.add_all([
        _mva(cest="1200700", uf_origem="SP", mva_original=D("58.00")),
        _mva(cest="1200800", uf_origem="SP", mva_original=D("71.78")),
    ])
    await sessao.flush()

    r = await _diag(sessao, cest=None)

    assert r["veredicto"] == "AMBIGUA"
    assert r["aplicada"] is None
    assert "58.00%" in r["explicacao"] and "71.78%" in r["explicacao"]
    assert r["consulta"]["cest"] == ""


async def test_item_sem_cest_com_margem_unica_encontra(sessao):
    sessao.add(_mva(uf_origem="SP", mva_original=D("58.00")))
    await sessao.flush()

    r = await _diag(sessao, cest=None)

    assert r["veredicto"] == "ENCONTRADA"
    assert r["aplicada"]["mva_original"] == "58.00"


# ── Entradas inválidas ────────────────────────────────────────────────────── #
async def test_ncm_e_uf_invalidos_viram_erro_de_dominio(sessao):
    with pytest.raises(DomainError):
        await _diag(sessao, ncm="abc")
    with pytest.raises(DomainError):
        await _diag(sessao, uf_destino="Xingu")
    with pytest.raises(DomainError):
        await _diag(sessao, uf_origem="Atlantida")


async def test_uf_por_extenso_e_ncm_pontuado_sao_aceitos(sessao):
    sessao.add(_mva(uf_origem="SP"))
    await sessao.flush()

    r = await _diag(
        sessao, ncm="8544.49.00", uf_origem="São Paulo", uf_destino="Minas Gerais"
    )

    assert r["veredicto"] == "ENCONTRADA"
    assert r["consulta"]["ncm"] == NCM
    assert r["consulta"]["uf_origem"] == "SP" and r["consulta"]["uf_destino"] == "MG"


# ── A trava: diagnóstico × motor não podem divergir ───────────────────────── #
@pytest.mark.parametrize(
    ("ncm_consulta", "cest_consulta", "origem"),
    [
        (NCM, CEST, "SP"),        # origem exata
        (NCM, CEST, "PR"),        # cai no curinga
        (NCM, "", "SP"),          # XML sem CEST
        ("854449", CEST, "SP"),   # fallback de NCM (6 dígitos)
        (NCM, CEST, "RS"),        # sem cobertura → os dois devolvem "nada"
    ],
)
async def test_veredicto_bate_com_o_que_o_motor_responderia(
    sessao, ncm_consulta, cest_consulta, origem
):
    """Mesma chave, duas leituras: o `_MvaSnapshot` hidratado como o motor faz e
    o diagnóstico. Se um diz ENCONTRADA e o outro não acha (ou acha outra
    linha), o diagnóstico está mentindo para o analista."""
    sessao.add_all([
        _mva(uf_origem="SP", mva_original=D("58.00")),
        _mva(mva_original=D("42.00")),                               # curinga
        _mva(ncm="854449", uf_origem="SP", mva_original=D("30.00")),  # 6 dígitos
    ])
    await sessao.flush()

    niveis = [ncm_consulta, ncm_consulta[:6], ncm_consulta[:4]]
    rows = (await sessao.execute(
        stmt_mva_do_motor(origem, "MG", niveis, DEPOIS)
    )).scalars().all()
    do_motor = montar_mva_snapshot(rows).buscar(
        ncm_consulta, cest_consulta, origem, "MG", DEPOIS
    )

    r = await diagnosticar_mva(
        sessao, ncm=ncm_consulta, cest=cest_consulta, uf_origem=origem,
        uf_destino="MG", data=DEPOIS,
    )

    if do_motor is None:
        assert r["veredicto"] != "ENCONTRADA"
        assert r["aplicada"] is None
    else:
        assert r["veredicto"] == "ENCONTRADA"
        assert r["aplicada"]["id"] == do_motor.matriz_id
        assert D(r["aplicada"]["mva_original"]) == do_motor.mva_original
        assert r["aplicada"]["ncm"] == do_motor.ncm_casado
        assert r["aplicada"]["uf_origem"] == do_motor.uf_origem_casada
