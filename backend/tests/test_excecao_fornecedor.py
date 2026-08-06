"""Exceção do Item por FORNECEDOR (pedido do João, ago/2026).

O cProd é o código do produto no cadastro do FORNECEDOR — não é um identificador
universal. Fornecedores diferentes usam códigos diferentes para o mesmo produto
e, pior, o MESMO código para produtos distintos. Enquanto a exceção casava só
pelo código dentro da empresa, a regra criada para o item "1234" do fornecedor A
também desligava o ST do item "1234" do fornecedor B — imposto ficando de fora
sem ninguém perceber (bug silencioso).

Regras cobertas:
  - a exceção de um fornecedor NÃO alcança o item homônimo de outro;
  - CNPJ exato vence a regra genérica ("" = qualquer fornecedor);
  - a genérica ainda vale quando não há regra do fornecedor (legado migrado);
  - item com NCM/CEST de ST + exceção "tributado normalmente" sai do motor como
    decisão de cadastro, sem código de erro (o caso de uso literal do João);
  - `fonte_regime` só diz EXCECAO_ITEM para o fornecedor certo;
  - CNPJ formatado no cadastro casa com o CNPJ limpo do XML.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.domain.st import (
    Crt,
    FcpEmMemoria,
    ItemFiscal,
    Operacao,
    StatusAuditoria,
    StAuditEngine,
)
from app.modules.fiscal.domain.st.enums import Regime
from app.modules.fiscal.infrastructure.matrizes_loaders import (
    MatrizesLoader,
    _EnquadramentoSnapshot,
    _MvaSnapshot,
)
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.models import ExcecaoEnquadramentoStProduto

DATA = date(2026, 6, 15)
D = Decimal
NCM, CEST, UF = "84248219", "0102900", "MG"
CODIGO = "1234"                    # o mesmo código nos dois fornecedores
FORN_A = "11111111000111"
FORN_B = "22222222000122"
CPF_RURAL = "12345678901"          # produtor rural também emite


def _snap(excecoes, dados=None) -> _EnquadramentoSnapshot:
    """Portão dizendo ST para o NCM/CEST — é o cenário em que a exceção importa."""
    return _EnquadramentoSnapshot(
        dados if dados is not None else {(NCM, CEST, UF): Regime.ST}, excecoes
    )


def _regime(snap: _EnquadramentoSnapshot, cnpj: str, codigo: str = CODIGO) -> Regime:
    return snap.regime(
        NCM, CEST, "SP", UF, DATA, codigo_produto=codigo, cnpj_emitente=cnpj
    )


# ── O bug do João: vazamento entre fornecedores ──────────────────────────── #
def test_excecao_de_um_fornecedor_nao_alcanca_o_item_homonimo_de_outro():
    """Regra criada para o item 1234 do fornecedor A não pode desligar o ST do
    item 1234 do fornecedor B — são produtos diferentes com o mesmo código."""
    snap = _snap({(FORN_A, CODIGO): Regime.TN})

    assert _regime(snap, FORN_A) == Regime.TN     # a decisão vale para quem foi criada
    assert _regime(snap, FORN_B) == Regime.ST     # e o outro segue auditado (o bug)


def test_excecao_do_fornecedor_vence_a_generica():
    """Genérica ("") nunca sequestra a regra específica — mesma precedência da
    UF de origem na MVA (exata > curinga)."""
    snap = _snap({("", CODIGO): Regime.ST, (FORN_A, CODIGO): Regime.TN})

    assert _regime(snap, FORN_A) == Regime.TN     # específica manda
    assert _regime(snap, FORN_B) == Regime.ST     # cai na genérica
    assert _regime(snap, "") == Regime.ST         # nota sem CNPJ: só a genérica


def test_excecao_generica_vale_quando_nao_ha_regra_do_fornecedor():
    """Preserva o legado: a migração 0034 converteu tudo para "" (todos)."""
    snap = _snap({("", CODIGO): Regime.TN})

    assert _regime(snap, FORN_A) == Regime.TN
    assert _regime(snap, FORN_B) == Regime.TN
    assert _regime(snap, CPF_RURAL) == Regime.TN
    assert _regime(snap, FORN_A, codigo="OUTRO") == Regime.ST   # outro produto


def test_cnpj_com_pontuacao_no_cadastro_casa_com_o_do_xml():
    """O XML traz o documento limpo; o cadastro pode ter vindo formatado.
    Normalizado dos dois lados, o par continua casando (CNPJ e CPF)."""
    snap = _snap({
        ("11.111.111/0001-11", CODIGO): Regime.TN,
        ("123.456.789-01", "RURAL-9"): Regime.TN,
    })

    assert _regime(snap, FORN_A) == Regime.TN
    assert _regime(snap, "11.111.111/0001-11") == Regime.TN     # e vice-versa
    assert _regime(snap, CPF_RURAL, codigo="RURAL-9") == Regime.TN
    assert _regime(snap, FORN_B) == Regime.ST


def test_fonte_regime_aponta_a_excecao_so_para_o_fornecedor_certo():
    snap = _snap({(FORN_A, CODIGO): Regime.TN})

    assert snap.fonte_regime(CODIGO, FORN_A) == "EXCECAO_ITEM"
    assert snap.fonte_regime(CODIGO, FORN_B) == "MATRIZ"
    assert snap.fonte_regime(CODIGO, "") == "MATRIZ"
    assert snap.fonte_regime(" 1234 ", "11.111.111/0001-11") == "EXCECAO_ITEM"


def test_explicar_tn_so_absolve_o_fornecedor_da_excecao():
    """TN por exceção do fornecedor = decisão de cadastro (None, sem código).
    Para o outro fornecedor não há absolvição por essa via."""
    snap = _snap({(FORN_A, CODIGO): Regime.TN}, dados={})

    assert snap.explicar_tn(
        NCM, CEST, UF, codigo_produto=CODIGO, cnpj_emitente=FORN_A
    ) is None
    msg = snap.explicar_tn(NCM, CEST, UF, codigo_produto=CODIGO, cnpj_emitente=FORN_B)
    assert msg and "sem enquadramento cadastrado" in msg


# ── Motor de ponta a ponta ───────────────────────────────────────────────── #
def _item(**kw) -> ItemFiscal:
    base = dict(
        numero_item=1, ncm=NCM, cest=CEST, cfop="6404", orig="0",
        cst="10", mod_bc_st=4, codigo_produto=CODIGO,
        v_prod=D("1000"), q_com=D("1"),
        v_icms=D("120"), v_bc=D("1000"), p_icms=D("12"),
    )
    base.update(kw)
    return ItemFiscal(**base)


def _engine(enq: _EnquadramentoSnapshot) -> StAuditEngine:
    return StAuditEngine(
        mva_repo=_MvaSnapshot({(NCM, CEST, "*", UF): (D("40"), 7, None)}),
        enquadramento_repo=enq,
        fcp_repo=FcpEmMemoria(),
    )


def test_produto_com_ncm_de_st_sai_do_motor_pela_excecao_do_fornecedor():
    """O caso de uso do João: chega com NCM e CST de ST, mas é tributado
    normalmente. Marcado como exceção DAQUELE fornecedor, sai do motor como
    decisão de cadastro — NAO_AUDITAVEL sem código (não vira pendência)."""
    eng = _engine(_snap({(FORN_A, CODIGO): Regime.TN}))
    op = Operacao(uf_emit="SP", uf_dest=UF, crt=Crt.NORMAL, data=DATA)

    r = eng.auditar_item(_item(cnpj_emitente=FORN_A), op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == []
    assert "Exceção do Item" in (r.observacao or "")


def test_mesmo_produto_de_outro_fornecedor_continua_sendo_auditado():
    """O outro lado da moeda: sem a chave composta, este item sairia do motor
    junto — o imposto sumia da conta."""
    eng = _engine(_snap({(FORN_A, CODIGO): Regime.TN}))
    op = Operacao(uf_emit="SP", uf_dest=UF, crt=Crt.NORMAL, data=DATA)

    r = eng.auditar_item(_item(cnpj_emitente=FORN_B), op)

    assert r.status != StatusAuditoria.NAO_AUDITAVEL
    assert r.memoria.mva_original == D("40")     # foi calculado de verdade


# ── Loader: a chave composta vem do banco ────────────────────────────────── #
_TABELAS = [
    MatrizMva.__table__, MatrizEnquadramentoSt.__table__, MatrizFcp.__table__,
    MatrizProtocoloSt.__table__, MatrizAliquota.__table__,
    ExcecaoEnquadramentoStProduto.__table__,
]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def test_loader_monta_a_chave_composta_e_respeita_a_precedencia(sessao):
    """Prova o caminho real: a query traz `cnpj_fornecedor`, o snapshot casa por
    (fornecedor, código) e o CNPJ formatado no cadastro normaliza para o do XML."""
    tenant_id, empresa_id = uuid4(), uuid4()
    sessao.add(MatrizEnquadramentoSt(
        uf_destino=UF, ncm=NCM, cest=CEST, regime="ST",
        data_inicio_vigencia=date(2026, 1, 1),
    ))
    # Genérica (legado) diz ST; a do fornecedor A, formatada, diz TN.
    sessao.add(ExcecaoEnquadramentoStProduto(
        tenant_id=tenant_id, empresa_id=empresa_id, cnpj_fornecedor="",
        codigo_produto=CODIGO, data_inicio_vigencia=date(2026, 1, 1),
        tributado_icms=False,
    ))
    sessao.add(ExcecaoEnquadramentoStProduto(
        tenant_id=tenant_id, empresa_id=empresa_id,
        cnpj_fornecedor="11.111.111/0001-11",
        codigo_produto=CODIGO, data_inicio_vigencia=date(2026, 1, 1),
        tributado_icms=True,
    ))
    await sessao.flush()

    itens = [_item(cnpj_emitente=FORN_A)]
    op = Operacao(uf_emit="SP", uf_dest=UF, crt=Crt.NORMAL, data=DATA)
    matrizes = await MatrizesLoader(sessao).hidratar(itens, op, empresa_id=empresa_id)
    enq = matrizes.enquadramento

    assert enq.excecoes == {
        ("", CODIGO): Regime.ST,
        (FORN_A, CODIGO): Regime.TN,          # gravado com pontuação, lido limpo
    }
    assert _regime(enq, FORN_A) == Regime.TN     # específica vence
    assert _regime(enq, FORN_B) == Regime.ST     # genérica para os demais
    assert enq.fonte_regime(CODIGO, FORN_A) == "EXCECAO_ITEM"


async def test_loader_ignora_excecao_de_outra_empresa(sessao):
    """O isolamento por empresa que já existia não pode ter se perdido."""
    tenant_id, empresa_id = uuid4(), uuid4()
    sessao.add(MatrizEnquadramentoSt(
        uf_destino=UF, ncm=NCM, cest=CEST, regime="ST",
        data_inicio_vigencia=date(2026, 1, 1),
    ))
    sessao.add(ExcecaoEnquadramentoStProduto(
        tenant_id=tenant_id, empresa_id=uuid4(), cnpj_fornecedor=FORN_A,
        codigo_produto=CODIGO, data_inicio_vigencia=date(2026, 1, 1),
        tributado_icms=True,
    ))
    await sessao.flush()

    op = Operacao(uf_emit="SP", uf_dest=UF, crt=Crt.NORMAL, data=DATA)
    matrizes = await MatrizesLoader(sessao).hidratar(
        [_item(cnpj_emitente=FORN_A)], op, empresa_id=empresa_id
    )

    assert matrizes.enquadramento.excecoes == {}
    assert _regime(matrizes.enquadramento, FORN_A) == Regime.ST
