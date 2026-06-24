"""Regressão fiscal do Motor de Auditoria de ICMS ST (núcleo v1).

Cada teste é um caso fechado: fatos da nota -> resultado esperado (status +
código de erro + memória). É a malha de segurança contra regressão exigida pelo
GOVERNANCA_Testes_Regressao_Fiscal do Vault.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.modules.fiscal.domain.st import (
    Crt,
    EnquadramentoEmMemoria,
    FcpEmMemoria,
    ItemFiscal,
    MvaEmMemoria,
    Operacao,
    StatusAuditoria,
    StAuditEngine,
)
from app.modules.fiscal.domain.st.mva import calcular_mva

DATA = date(2026, 6, 1)


def _engine(**kw) -> StAuditEngine:
    return StAuditEngine(
        mva_repo=kw.get("mva", MvaEmMemoria()),
        enquadramento_repo=kw.get("enq", EnquadramentoEmMemoria()),
        fcp_repo=kw.get("fcp", FcpEmMemoria()),
    )


def _item(**kw) -> ItemFiscal:
    # Caso canônico SP→MG (interestadual Sudeste→Sudeste = 12%): ICMS próprio
    # da operação = 1000 × 12% = 120.
    base = dict(
        numero_item=1, ncm="85122011", cest="0100100", cfop="6404", orig="0",
        cst="10", mod_bc_st=4, v_prod=Decimal("1000"), q_com=Decimal("1"),
        v_icms=Decimal("120"), v_bc=Decimal("1000"), p_icms=Decimal("12"),
    )
    base.update(kw)
    return ItemFiscal(**base)


# --------------------------------------------------------------------------- #
def test_caso_feliz_cst10_normal_interestadual_ok():
    """SP→MG, CST 10, normal: MVA ajustada de 40% para ~50,24%, sem divergência."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(v_bc_st=Decimal("1502.44"), v_icms_st=Decimal("150.44"))

    r = _engine().auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    assert r.erros == ()
    assert r.memoria.mva_foi_ajustada is True
    assert round(r.memoria.mva_aplicada, 2) == Decimal("50.24")
    assert r.memoria.base_st_calculada == Decimal("1502.44")
    assert r.memoria.icms_st_calculado == Decimal("150.44")


def test_simples_nao_ajusta_mva_erro_101():
    """Emitente Simples (CRT 1): proibido ajustar MVA; XML ajustou -> ERRO_101."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.SIMPLES, data=DATA)
    # Base/valor coerentes com a MVA ORIGINAL (40%); só o pMVAST veio ajustado.
    item = _item(
        csosn="201", cst=None, p_mva_st=Decimal("58.78"),
        v_bc_st=Decimal("1400.00"), v_icms_st=Decimal("132.00"),
    )

    r = _engine().auditar_item(item, op)

    assert r.codigos_erro == ["ERRO_101_MVA_AJUSTADA_INDEVIDA"]
    assert r.memoria.mva_foi_ajustada is False


def test_operacao_interna_nao_ajusta():
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(v_bc_st=Decimal("1400.00"), v_icms_st=Decimal("182.00"))

    r = _engine().auditar_item(item, op)

    assert r.memoria.mva_foi_ajustada is False
    assert "interna" in r.memoria.motivo_nao_ajuste


def test_icms_proprio_zerado_dispara_erro_107():
    """CST 10 com vICMS=0 (erro do emissor): não deduz zero, marca ERRO_107."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(v_icms=Decimal("0"), v_bc=Decimal("0"),
                 v_bc_st=Decimal("1502.44"), v_icms_st=Decimal("150.44"))

    r = _engine().auditar_item(item, op)

    assert "ERRO_107_ICMS_PROPRIO_ZERADO_COM_ST" in r.codigos_erro
    assert r.memoria.deducao_tipo == "contaminada"
    # Dedução usa o próprio recalculado (1000 × 12% = 120), não o zero do XML.
    assert r.memoria.deducao_aplicada == Decimal("120.00")


def test_modbcst6_com_mva_dispara_erro_101():
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(mod_bc_st=6, p_mva_st=Decimal("10"),
                 v_bc_st=Decimal("1000.00"), v_icms_st=Decimal("60.00"))

    r = _engine().auditar_item(item, op)

    assert "ERRO_101_MVA_AJUSTADA_INDEVIDA" in r.codigos_erro


def test_fcp_st_omitido_dispara_erro_105():
    """RJ tem FCP GERAL 2%; XML veio com vFCPST zerado -> ERRO_105."""
    op = Operacao(uf_emit="SP", uf_dest="RJ", crt=Crt.NORMAL, data=DATA)
    item = _item(
        ncm="33049910", cest="2001600",
        v_bc_st=Decimal("1714.87"), v_icms_st=Decimal("222.97"), v_fcp_st=Decimal("0"),
    )

    r = _engine().auditar_item(item, op)

    assert r.codigos_erro == ["ERRO_105_FCP_ST_OMITIDO"]
    assert r.memoria.fcp_st_calculado > Decimal("0")


def test_enquadramento_tn_nao_auditavel():
    enq = EnquadramentoEmMemoria(tn={("85122011", "0100100", "MG")})
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = _engine(enq=enq).auditar_item(_item(), op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL


def test_modbcst_pauta_fora_do_nucleo_v1():
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = _engine().auditar_item(_item(mod_bc_st=5), op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert "modBCST=5" in r.observacao


def test_tolerancia_centavos_por_item():
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    # 2 centavos a mais no vICMSST: dentro da régua -> OK.
    ok = _engine().auditar_item(
        _item(v_bc_st=Decimal("1502.44"), v_icms_st=Decimal("150.46")), op
    )
    assert ok.status == StatusAuditoria.OK
    # 3 centavos: estoura a régua -> DIVERGENTE (ERRO_104).
    div = _engine().auditar_item(
        _item(v_bc_st=Decimal("1502.44"), v_icms_st=Decimal("150.47")), op
    )
    assert "ERRO_104_VALOR_ST_DIVERGENTE" in div.codigos_erro


@pytest.mark.parametrize(
    "inter, intra, espera_ajuste",
    [
        (Decimal("7"), Decimal("18"), True),    # inter < intra -> ajusta
        (Decimal("12"), Decimal("12"), False),  # inter == intra -> trava
        (Decimal("12"), Decimal("7"), False),   # inter > intra -> trava
    ],
)
def test_mva_trava_aliquota_inter_maior_igual(inter, intra, espera_ajuste):
    r = calcular_mva(
        mva_original=Decimal("40"), alq_inter=inter, alq_intra=intra,
        crt=Crt.NORMAL, interestadual=True,
    )
    assert r.ajustada is espera_ajuste
