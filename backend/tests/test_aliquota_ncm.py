"""Alíquota interna POR NCM e redução de base pela matriz (regra de ouro).

Dois furos da mesma família, um passo adiante do que já se corrigiu na MVA:

1. a alíquota interna era só da UF — produto com alíquota própria (cesta básica
   a 12%, medicamento) saía calculado com a modal do estado (18% em MG), ST a
   maior direto no custo do cliente;
2. a redução de base vinha só do XML — o motor repetia a conta do fornecedor,
   então redução esquecida (ST a maior) e redução indevida (ST a menor) não
   apareciam em lugar nenhum.

A regra é a mesma da MVA: quem decide é a MATRIZ CURADA. Linha do produto vence
a regra do estado; linha do produto com redução 0,00 é DECISÃO ("este produto
não tem redução"), não ausência de dado. Só a GERAL casando = redução não
curada → segue o XML, sem erro, com a fonte registrada na memória.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.fiscal.domain.st import (
    AliquotaEmMemoria,
    Crt,
    EnquadramentoEmMemoria,
    FcpEmMemoria,
    ItemFiscal,
    MvaEmMemoria,
    Operacao,
    ProtocoloEmMemoria,
    StatusAuditoria,
    StAuditEngine,
)
from app.modules.fiscal.domain.st.mva import calcular_mva

DATA = date(2026, 6, 1)
NCM = "19053100"          # biscoito (exemplo de cesta básica com alíquota própria)
CEST = "1701200"


def _engine(aliquota=None, **kw) -> StAuditEngine:
    base = dict(
        mva_repo=kw.get("mva", MvaEmMemoria({(NCM, CEST, "MG"): "40.00"})),
        enquadramento_repo=kw.get("enq", EnquadramentoEmMemoria()),
        fcp_repo=kw.get("fcp", FcpEmMemoria()),
        protocolo_repo=kw.get("protocolo", ProtocoloEmMemoria()),
    )
    if aliquota is not None:
        base["aliquota_repo"] = aliquota
    return StAuditEngine(**base)


def _item(**kw) -> ItemFiscal:
    base = dict(
        numero_item=1, ncm=NCM, cest=CEST, cfop="5405", orig="0",
        cst="00", mod_bc_st=4, v_prod=Decimal("1000"), q_com=Decimal("1"),
        v_icms=Decimal("180"), v_bc=Decimal("1000"), p_icms=Decimal("18"),
        p_mva_st=Decimal("40.00"),
    )
    base.update(kw)
    return ItemFiscal(**base)


OP_MG = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)


# --------------------------------------------------------------------------- #
# Tarefa 1 — a alíquota é do PRODUTO, não só da UF
# --------------------------------------------------------------------------- #
def test_linha_do_ncm_vence_a_geral():
    """MG cobra 18% em geral, mas 12% neste NCM: manda a linha do produto."""
    repo = AliquotaEmMemoria({
        ("MG", "GERAL"): ("18", "0"),
        ("MG", NCM): ("12", "0", "0", "RICMS/MG anexo IV, item 19"),
    })

    aliq = repo.buscar(NCM, "MG", DATA)

    assert aliq.modal == Decimal("12")
    assert aliq.ncm_casado == NCM and aliq.especifica is True
    assert aliq.base_legal == "RICMS/MG anexo IV, item 19"


def test_geral_responde_quando_nao_ha_linha_do_produto():
    repo = AliquotaEmMemoria({("MG", "GERAL"): ("18", "0"), ("MG", NCM): ("12", "0")})

    aliq = repo.buscar("85122011", "MG", DATA)

    assert aliq.modal == Decimal("18")
    assert aliq.ncm_casado == "GERAL" and aliq.especifica is False


@pytest.mark.parametrize(
    "cadastrado,esperado",
    [("19053100", "19053100"), ("190531", "190531"), ("1905", "1905")],
)
def test_fallback_8_6_4(cadastrado, esperado):
    """Mesma convenção da MVA e do protocolo: 8→6→4 e só então GERAL."""
    repo = AliquotaEmMemoria({("MG", "GERAL"): ("18", "0"), ("MG", cadastrado): ("12", "0")})

    aliq = repo.buscar(NCM, "MG", DATA)

    assert aliq.modal == Decimal("12") and aliq.ncm_casado == esperado


def test_o_mais_especifico_ganha_do_menos_especifico():
    repo = AliquotaEmMemoria({
        ("MG", "1905"): ("12", "0"), ("MG", NCM): ("7", "0"), ("MG", "GERAL"): ("18", "0"),
    })

    assert repo.buscar(NCM, "MG", DATA).modal == Decimal("7")


def test_uf_sem_nenhuma_linha_continua_travando():
    """ALIQUOTA_NAO_ENCONTRADA vale quando NÃO HÁ NENHUMA linha vigente na UF —
    nem a GERAL. Fail-closed: o motor não assume a taxa do estado vizinho."""
    r = _engine(AliquotaEmMemoria({("SP", "GERAL"): ("18", "0")})).auditar_item(
        _item(), OP_MG
    )

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert "ERRO_ALIQUOTA_NAO_ENCONTRADA" in r.codigos_erro


def test_produto_de_12_num_estado_de_18_calcula_com_12():
    """O caso que motivou tudo: interna MG→MG, produto a 12%.

    Base = 1000 × 1,40 = 1400. Débito = 1400 × 12% = 168,00. Dedução = vICMS
    real (120,00, o próprio destacado a 12%). ST = 48,00. Com a modal do estado
    (18%) o motor cobraria 252,00 − 120,00 = 132,00 — quase 3× o devido.
    """
    repo = AliquotaEmMemoria({("MG", "GERAL"): ("18", "0"), ("MG", NCM): ("12", "0")})
    item = _item(
        v_icms=Decimal("120"), p_icms=Decimal("12"),
        v_bc_st=Decimal("1400"), v_icms_st=Decimal("48"),
    )

    r = _engine(repo).auditar_item(item, OP_MG)

    assert r.status == StatusAuditoria.OK
    assert r.memoria.alq_intra == Decimal("12")
    assert r.memoria.aliquota_ncm_casado == NCM
    assert r.memoria.base_st_calculada == Decimal("1400.00")
    assert r.memoria.icms_st_debito == Decimal("168.00")
    assert r.memoria.icms_st_calculado == Decimal("48.00")


def test_ajuste_de_mva_usa_a_carga_efetiva_do_produto():
    """R-07: o denominador do ajuste passa a ser a carga EFETIVA do produto.

    SP→MG (12% inter), produto a 12% em MG: carga interna igual à interestadual
    dispara a TRAVA do ajuste (não há vantagem a neutralizar) — com a modal de
    18% o motor inflaria a MVA de 40% para ~50,24% e a base junto.
    """
    repo = AliquotaEmMemoria({("MG", "GERAL"): ("18", "0"), ("MG", NCM): ("12", "0")})
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    mva = MvaEmMemoria({(NCM, CEST, "MG"): "40.00"})
    item = _item(cfop="6404", v_icms=Decimal("120"), p_icms=Decimal("12"))

    r = _engine(repo, mva=mva).auditar_item(item, op)

    assert r.memoria.mva_foi_ajustada is False
    assert r.memoria.mva_aplicada == Decimal("40.00")
    # Referência: com 18% (a modal do estado) o ajuste subiria a MVA.
    assert calcular_mva(
        mva_original=Decimal("40"), alq_inter=Decimal("12"), alq_intra=Decimal("18"),
        crt=Crt.NORMAL, interestadual=True,
    ).ajustada is True


# --------------------------------------------------------------------------- #
# Tarefa 2 — redução de base: a matriz manda quando a linha é do produto
# --------------------------------------------------------------------------- #
def test_reducao_da_matriz_vence_o_xml_e_a_memoria_diz_a_fonte():
    """Linha específica com 33,33%: a base sai reduzida mesmo que o XML tenha
    aplicado a mesma coisa — a fonte da decisão é a matriz, não o documento."""
    repo = AliquotaEmMemoria({
        ("MG", "GERAL"): ("18", "0"), ("MG", NCM): ("18", "0", "33.33"),
    })
    item = _item(
        p_red_bc_st=Decimal("33.33"),
        v_bc_st=Decimal("933.38"), v_icms_st=Decimal("-1"),   # comparação: só a base importa
    )

    r = _engine(repo).auditar_item(item, OP_MG)

    assert r.memoria.reducao_fonte == "matriz"
    assert r.memoria.reducao_base_st == Decimal("33.33")
    assert r.memoria.base_st_calculada == Decimal("933.38")   # 1400 × (1 − 33,33%)
    assert "ERRO_112_REDUCAO_BASE_ST_MAIOR_QUE_NORMA" not in r.codigos_erro
    assert "ERRO_113_REDUCAO_BASE_ST_MENOR_QUE_NORMA" not in r.codigos_erro


def test_xml_reduziu_mais_que_a_norma_st_a_menos():
    """Nota reduziu 33,33% onde a norma prevê 20% → base menor → ST retido a
    MENOS que o devido (complemento a recolher)."""
    repo = AliquotaEmMemoria({("MG", NCM): ("18", "0", "20.00", "RICMS/MG art. 1")})
    item = _item(p_red_bc_st=Decimal("33.33"))

    r = _engine(repo).auditar_item(item, OP_MG)

    assert r.status == StatusAuditoria.DIVERGENTE
    assert "ERRO_112_REDUCAO_BASE_ST_MAIOR_QUE_NORMA" in r.codigos_erro
    assert r.memoria.base_st_calculada == Decimal("1120.00")   # 1400 × (1 − 20%)
    assert r.memoria.reducao_base_st == Decimal("20.00")
    assert r.memoria.reducao_base_st_xml == Decimal("33.33")
    assert "33,33%" in r.observacao and "20,00%" in r.observacao
    assert "complemento a recolher" in r.observacao
    assert "RICMS/MG art. 1" in r.observacao


def test_xml_nao_reduziu_e_a_norma_previa_st_a_mais():
    """Nota sem redução onde a norma prevê 33,33% → base maior → ST retido a
    MAIS: custo indevido, cabe correção."""
    repo = AliquotaEmMemoria({("MG", NCM): ("18", "0", "33.33")})
    item = _item(p_red_bc_st=Decimal("0"))

    r = _engine(repo).auditar_item(item, OP_MG)

    assert r.status == StatusAuditoria.DIVERGENTE
    assert "ERRO_113_REDUCAO_BASE_ST_MENOR_QUE_NORMA" in r.codigos_erro
    assert r.memoria.base_st_calculada == Decimal("933.38")
    assert "custo indevido" in r.observacao


def test_linha_especifica_com_reducao_zero_e_decisao_curada():
    """Redução 0,00 numa linha DO PRODUTO não é ausência de dado: é a decisão de
    que aquele produto não tem redução. XML reduzindo → divergência (ST a menos)."""
    repo = AliquotaEmMemoria({("MG", "GERAL"): ("18", "0"), ("MG", NCM): ("18", "0", "0")})
    item = _item(p_red_bc_st=Decimal("33.33"))

    r = _engine(repo).auditar_item(item, OP_MG)

    assert "ERRO_112_REDUCAO_BASE_ST_MAIOR_QUE_NORMA" in r.codigos_erro
    assert r.memoria.reducao_fonte == "matriz"
    assert r.memoria.reducao_base_st == Decimal("0")
    assert r.memoria.base_st_calculada == Decimal("1400.00")   # base cheia


def test_so_a_geral_casando_usa_o_xml_sem_erro():
    """Redução NÃO curada é o caso comum — não vira erro. O motor segue o XML e
    a memória registra que a fonte foi o documento (nunca silencioso)."""
    repo = AliquotaEmMemoria({("MG", "GERAL"): ("18", "0", "0")})
    item = _item(p_red_bc_st=Decimal("33.33"))

    r = _engine(repo).auditar_item(item, OP_MG)

    assert r.memoria.reducao_fonte == "xml"
    assert r.memoria.reducao_base_st == Decimal("33.33")
    assert r.memoria.aliquota_ncm_casado == "GERAL"
    assert r.memoria.base_st_calculada == Decimal("933.38")
    assert not [c for c in r.codigos_erro if "REDUCAO_BASE_ST" in c]


def test_diferenca_de_centavo_no_percentual_nao_vira_divergencia():
    """Tolerância de pontos (0,01) — arredondamento do emissor não é achado."""
    repo = AliquotaEmMemoria({("MG", NCM): ("18", "0", "33.33")})
    item = _item(p_red_bc_st=Decimal("33.34"))

    r = _engine(repo).auditar_item(item, OP_MG)

    assert not [c for c in r.codigos_erro if "REDUCAO_BASE_ST" in c]


# --------------------------------------------------------------------------- #
# Não-regressão: com só a GERAL (redução 0), nada muda
# --------------------------------------------------------------------------- #
def test_nao_regressao_matriz_so_com_a_geral():
    """Todo o legado virou linha GERAL com redução 0,00 — o resultado tem de ser
    IDÊNTICO ao da referência em código (o motor de antes desta mudança)."""
    repo = AliquotaEmMemoria({("MG", "GERAL"): ("18", "0", "0")})
    item = _item(v_bc_st=Decimal("1400"), v_icms_st=Decimal("72"))

    referencia = _engine().auditar_item(item, OP_MG)      # AliquotasReferencia (MG 18%)
    com_matriz = _engine(repo).auditar_item(item, OP_MG)

    assert referencia.status == com_matriz.status == StatusAuditoria.OK
    assert referencia.memoria.alq_intra == com_matriz.memoria.alq_intra == Decimal("18")
    assert referencia.memoria.base_st_calculada == com_matriz.memoria.base_st_calculada
    assert referencia.memoria.icms_st_calculado == com_matriz.memoria.icms_st_calculado
    assert referencia.memoria.reducao_fonte == com_matriz.memoria.reducao_fonte == "xml"
