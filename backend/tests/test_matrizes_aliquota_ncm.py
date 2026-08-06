"""Alíquota do estado × alíquota do produto: schema (guardas + normalização) e
o filtro da listagem da tela.

A matriz de Alíquotas era só por UF: um remédio de 12% em MG calculava com os
18% do estado. Agora cada UF tem a linha 'GERAL' (a regra do estado) e, quando a
lei dá alíquota própria ao produto, uma linha por NCM ao lado dela.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.modules.fiscal.api.matrizes_routers import _filtrar_aliquota
from app.modules.fiscal.api.matrizes_schemas import (
    MatrizAliquotaCreate,
    MatrizAliquotaResponse,
    MatrizAliquotaUpdate,
)
from app.modules.fiscal.infrastructure.matrizes_models import MatrizAliquota

_BASE = {"uf_destino": "MG", "aliq_modal": "18.00", "data_inicio_vigencia": "2026-01-01"}


@pytest.fixture
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[MatrizAliquota.__table__])
    with Session(engine) as s:
        s.add_all([
            MatrizAliquota(uf_destino="MG", ncm="GERAL", aliq_modal=Decimal("18.00"),
                           data_inicio_vigencia=date(2026, 1, 1)),
            MatrizAliquota(uf_destino="MG", ncm="30049099", aliq_modal=Decimal("12.00"),
                           data_inicio_vigencia=date(2026, 1, 1)),
            MatrizAliquota(uf_destino="MG", ncm="22030000", aliq_modal=Decimal("18.00"),
                           p_red_bc_st=Decimal("38.89"),
                           data_inicio_vigencia=date(2026, 1, 1)),
            MatrizAliquota(uf_destino="SP", ncm="GERAL", aliq_modal=Decimal("18.00"),
                           data_inicio_vigencia=date(2026, 1, 1)),
        ])
        s.flush()
        yield s


# ── Schema ───────────────────────────────────────────────────────────────────
def test_ncm_em_branco_vira_a_regra_do_estado():
    """Igual ao FCP: vazio, 'geral' ou o NCM formatado — sempre canônico. NCM
    gravado em branco seria uma linha que nenhuma busca encontraria."""
    assert MatrizAliquotaCreate(**_BASE).normalizado()["ncm"] == "GERAL"
    assert MatrizAliquotaCreate(**_BASE, ncm=" geral ").normalizado()["ncm"] == "GERAL"
    assert MatrizAliquotaCreate(**_BASE, ncm="3004.90.99").normalizado()["ncm"] == "30049099"


def test_aliquota_zero_continua_recusada():
    """0% não é "produto isento" (isso é enquadramento/exceção de item): uma
    linha assim zeraria o débito do ST em silêncio."""
    with pytest.raises(ValueError):
        MatrizAliquotaCreate(**{**_BASE, "aliq_modal": "0"})


def test_reducao_de_base_exige_ncm_do_produto():
    """A guarda do bloco: redução na linha do estado reduziria a base de TODO
    produto da UF. Recusa com o motivo, para quem não é do fisco entender."""
    for ncm in ("GERAL", "", "geral"):
        with pytest.raises(ValueError) as e:
            MatrizAliquotaCreate(**_BASE, ncm=ncm, p_red_bc_st="38.89")
        assert "informe o NCM" in str(e.value)

    # Com o NCM do produto, passa.
    ok = MatrizAliquotaCreate(**_BASE, ncm="22030000", p_red_bc_st="38.89")
    assert ok.normalizado()["p_red_bc_st"] == Decimal("38.89")

    # E editar não é a porta dos fundos da criação.
    with pytest.raises(ValueError):
        MatrizAliquotaUpdate(**_BASE, p_red_bc_st="10")


def test_leitura_nao_esconde_linha_torta():
    """A validação é da ESCRITA. Se uma linha inconsistente chegou ao banco por
    outro caminho, ela precisa APARECER na tela para o curador corrigir."""
    torta = MatrizAliquotaResponse(
        id=1, **_BASE, ncm="GERAL", p_red_bc_st="38.89",
    )
    assert torta.p_red_bc_st == Decimal("38.89")


# ── Filtro da listagem ───────────────────────────────────────────────────────
def _listar(sessao, uf=None, ncm=None):
    stmt = _filtrar_aliquota(select(MatrizAliquota), uf, ncm, None)
    return [(x.uf_destino, x.ncm) for x in sessao.execute(stmt).scalars()]


def test_listagem_ordena_por_uf_e_ncm(sessao):
    assert _listar(sessao) == [
        ("MG", "22030000"), ("MG", "30049099"), ("MG", "GERAL"), ("SP", "GERAL"),
    ]


def test_filtro_por_ncm_mantem_a_linha_do_estado(sessao):
    """Procurar o remédio tem de mostrar TAMBÉM os 18% gerais: é a alíquota que
    o cálculo usa quando o produto não tem regra própria (mesma razão do
    Protocolo de par inteiro). Esconder a GERAL faria a tela responder "não tem
    alíquota" para um produto que tem."""
    assert _listar(sessao, ncm="30049099") == [("MG", "30049099"), ("MG", "GERAL"),
                                               ("SP", "GERAL")]
    # Prefixo funciona (o cadastro pode estar em 4 ou 6 dígitos).
    assert ("MG", "22030000") in _listar(sessao, ncm="2203")
    # NCM sem linha própria: sobra a regra do estado.
    assert _listar(sessao, uf="MG", ncm="84212300") == [("MG", "GERAL")]
    # Pesquisar o texto "GERAL" pede as regras de estado — e NÃO a matriz toda
    # (só os dígitos de "GERAL" é "", e um LIKE '%' casaria tudo).
    assert _listar(sessao, ncm="GERAL") == [("MG", "GERAL"), ("SP", "GERAL")]


def test_filtro_por_uf_aceita_nome_por_extenso(sessao):
    assert _listar(sessao, uf="minas gerais") == [
        ("MG", "22030000"), ("MG", "30049099"), ("MG", "GERAL"),
    ]
