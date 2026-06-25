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


def test_modbcst6_com_mva_cadastrada_recalcula_e_marca_109():
    """XML usou modBCST=6 (valor da operação) num produto que TEM MVA na matriz:
    o motor recalcula com a MVA correta e marca ERRO_109 (base do emitente errada)."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(mod_bc_st=6, v_bc_st=Decimal("1000.00"), v_icms_st=Decimal("60.00"))

    r = _engine().auditar_item(item, op)

    assert r.status == StatusAuditoria.DIVERGENTE
    assert "ERRO_109_MODBCST_INCOMPATIVEL" in r.codigos_erro
    assert r.memoria.mva_aplicada > Decimal("0")   # usou a MVA da matriz, não 0


def test_mva_exigida_e_ausente_trava_em_nao_auditavel():
    """modBCST=4 mas a matriz não tem MVA p/ o NCM → NÃO calcula a seco:
    classifica NAO_AUDITAVEL com ERRO_MVA_NAO_ENCONTRADA (trava de segurança)."""
    engine = StAuditEngine(MvaEmMemoria(), EnquadramentoEmMemoria(), FcpEmMemoria())
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(ncm="99999999", cest="9999999", mod_bc_st=4)   # NCM fora da matriz

    r = engine.auditar_item(item, op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert "ERRO_MVA_NAO_ENCONTRADA" in r.codigos_erro
    assert "MVA" in (r.observacao or "")


def test_modbcst6_sem_mva_e_legitimo():
    """modBCST=6 e SEM MVA cadastrada = base 'valor da operação' (NT 2020.005),
    legítimo: calcula sem MVA e sem ERRO_109."""
    engine = StAuditEngine(MvaEmMemoria(), EnquadramentoEmMemoria(), FcpEmMemoria())
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(ncm="99999999", cest="9999999", mod_bc_st=6,
                 v_bc_st=Decimal("1000.00"), v_icms_st=Decimal("60.00"))

    r = engine.auditar_item(item, op)

    assert r.status != StatusAuditoria.NAO_AUDITAVEL
    assert "ERRO_109_MODBCST_INCOMPATIVEL" not in r.codigos_erro
    assert r.memoria.mva_aplicada == Decimal("0")


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


def test_gabarito_pneuagro_mg_mg_interna():
    """GABARITO REAL (Pneuagro, saída MG->MG interna) — NÃO REGRIDIR.

    vProd 3300, alíq interna 18%, NCM 40111000 (pneu), MVA original 42%.
    Operação interna => MVA não ajusta. ICMS-ST esperado = 249,48.
    """
    engine = StAuditEngine(
        MvaEmMemoria({("40111000", "0100500", "MG"): "42.00"}),
        EnquadramentoEmMemoria(),
        FcpEmMemoria(),
    )
    item = ItemFiscal(
        numero_item=1, ncm="40111000", cest="0100500", cfop="5405", orig="0",
        cst="10", mod_bc_st=4, v_prod=Decimal("3300"),
        v_bc=Decimal("3300"), v_icms=Decimal("594.00"), p_icms=Decimal("18"),
        p_mva_st=Decimal("42.00"), v_bc_st=Decimal("4686.00"), v_icms_st=Decimal("249.48"),
    )
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = engine.auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    assert r.memoria.mva_foi_ajustada is False
    assert r.memoria.base_st_calculada == Decimal("4686.00")  # 3300 × 1,42
    assert r.memoria.deducao_aplicada == Decimal("594.00")    # ICMS próprio real
    assert r.memoria.icms_st_calculado == Decimal("249.48")   # 843,48 − 594,00


def test_antecipacao_interestadual_com_frete_rateado():
    """GABARITO REAL (autopeça SP->MG, antecipação) — NÃO REGRIDIR.

    Remetente Regime Normal não destacou ST -> antecipação do destinatário (MG).
    vProd 731,35 + frete rateado de CT-e 68,05 (entra na base do ST, não no
    próprio). NCM 87082919, CEST 01.075.00, MVA original 71,78%.
    Interestadual 12%->18% => MVA ajusta para 84,35%. ICMS-ST devido = 177,50.
    """
    engine = StAuditEngine(
        MvaEmMemoria({("87082919", "0107500", "MG"): "71.78"}),
        EnquadramentoEmMemoria(),
        FcpEmMemoria(),
    )
    item = ItemFiscal(
        numero_item=1, ncm="87082919", cest="0107500", cfop="6102", orig="0",
        cst="00", mod_bc_st=4,
        v_prod=Decimal("731.35"), v_frete=Decimal("68.05"),   # 731,35 + 68,05 = 799,40
        v_bc=Decimal("731.35"), v_icms=Decimal("87.76"), p_icms=Decimal("12"),
        v_bc_st=Decimal("0"), v_icms_st=Decimal("0"),         # ST omitido pelo remetente
    )
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = engine.auditar_item(item, op)

    assert r.memoria.mva_foi_ajustada is True
    assert round(r.memoria.mva_aplicada, 2) == Decimal("84.35")
    assert r.memoria.base_st_calculada == Decimal("1473.69")   # 799,40 × 1,843493
    assert r.memoria.deducao_aplicada == Decimal("87.76")      # 731,35 × 12% (sem frete)
    assert r.memoria.icms_st_calculado == Decimal("177.50")
    # Remetente omitiu o ST: motor aponta a antecipação devida como divergência.
    assert r.status == StatusAuditoria.DIVERGENTE
    assert "ERRO_104_VALOR_ST_DIVERGENTE" in r.codigos_erro


def test_cst70_reducao_base_interna():
    """GABARITO (CST 70, redução de base, interna MG->MG) — NÃO REGRIDIR.

    pRedBC e pRedBCST = 33,33%. Redução aplicada na base ANTES do débito
    (Método A). A dedução usa o ICMS próprio REAL já reduzido (120,01) — a
    "Armadilha da Dedução" do §6.1: própria reduzida => dedução menor => ST sobe.
    ICMS-ST esperado = 48,00.
    """
    engine = StAuditEngine(
        MvaEmMemoria({("84099900", "0102200", "MG"): "40.00"}),
        EnquadramentoEmMemoria(),
        FcpEmMemoria(),
    )
    item = ItemFiscal(
        numero_item=1, ncm="84099900", cest="0102200", cfop="5405", orig="0",
        cst="70", mod_bc_st=4, v_prod=Decimal("1000"),
        v_bc=Decimal("666.70"), v_icms=Decimal("120.01"), p_icms=Decimal("18"),
        p_red_bc=Decimal("33.33"), p_red_bc_st=Decimal("33.33"), p_mva_st=Decimal("40.00"),
        v_bc_st=Decimal("933.38"), v_icms_st=Decimal("48.00"),
    )
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = engine.auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    assert r.memoria.mva_foi_ajustada is False
    assert r.memoria.base_st_calculada == Decimal("933.38")   # 1400 × (1 − 33,33%)
    assert r.memoria.icms_st_debito == Decimal("168.01")
    assert r.memoria.deducao_aplicada == Decimal("120.01")    # próprio real reduzido
    assert r.memoria.icms_st_calculado == Decimal("48.00")


def test_simples_interestadual_sem_ajuste_deducao_teorica():
    """GABARITO (Simples CSOSN 201, SP->MG) — NÃO REGRIDIR.

    Duas regras de ouro: (1) CRT=1 => MVA NÃO ajusta (Conv. 142/2018); (2)
    dedução TEÓRICA = base × alíq. interestadual (12%), não a guia do DAS.
    ICMS-ST esperado = 150,00.
    """
    engine = StAuditEngine(
        MvaEmMemoria({("39173900", "1001100", "MG"): "50.00"}),
        EnquadramentoEmMemoria(),
        FcpEmMemoria(),
    )
    item = ItemFiscal(
        numero_item=1, ncm="39173900", cest="1001100", cfop="6102", orig="0",
        csosn="201", mod_bc_st=4, v_prod=Decimal("1000"), p_mva_st=Decimal("50.00"),
        v_bc_st=Decimal("1500.00"), v_icms_st=Decimal("150.00"),
    )
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.SIMPLES, data=DATA)

    r = engine.auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    assert r.memoria.mva_foi_ajustada is False                # trava do Simples
    assert round(r.memoria.mva_aplicada, 2) == Decimal("50.00")
    assert r.memoria.deducao_tipo == "teorica"
    assert r.memoria.deducao_aplicada == Decimal("120.00")    # 1000 × 12% (interestadual)
    assert r.memoria.base_st_calculada == Decimal("1500.00")
    assert r.memoria.icms_st_calculado == Decimal("150.00")


def test_fcp_st_trilhas_paralelas_com_deducao():
    """GABARITO (FCP-ST, interna MG->MG) — NÃO REGRIDIR.

    Bebida alcoólica, FCP 2%, MVA 50%. ICMS-ST e FCP-ST correm em trilhas
    SEPARADAS (nunca somadas). FCP-ST deduz o FCP próprio (não-cumulatividade,
    NT 2016.002): FCP-ST = (1500 × 2%) − 20 = 10,00. ICMS-ST = 90,00.
    """
    engine = StAuditEngine(
        MvaEmMemoria({("22084000", "0202200", "MG"): "50.00"}),
        EnquadramentoEmMemoria(),
        FcpEmMemoria({("MG", "22084000"): "2.00"}),
    )
    item = ItemFiscal(
        numero_item=1, ncm="22084000", cest="0202200", cfop="5405", orig="0",
        cst="10", mod_bc_st=4, v_prod=Decimal("1000"),
        v_bc=Decimal("1000"), v_icms=Decimal("180.00"), p_icms=Decimal("18"),
        v_fcp=Decimal("20.00"), p_mva_st=Decimal("50.00"),
        v_bc_st=Decimal("1500.00"), v_icms_st=Decimal("90.00"),
        p_fcp_st=Decimal("2.00"), v_bc_fcp_st=Decimal("1500.00"), v_fcp_st=Decimal("10.00"),
    )
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = engine.auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    # Trilha 1 — ICMS-ST (deduz ICMS próprio).
    assert r.memoria.icms_st_debito == Decimal("270.00")
    assert r.memoria.icms_st_calculado == Decimal("90.00")
    # Trilha 2 — FCP-ST (paralela; deduz FCP próprio).
    assert r.memoria.fcp_st_debito == Decimal("30.00")
    assert r.memoria.fcp_st_deducao == Decimal("20.00")
    assert r.memoria.fcp_st_calculado == Decimal("10.00")
    # As trilhas são independentes: o FCP-ST jamais entra no ICMS-ST.
    assert r.memoria.icms_st_calculado != r.memoria.fcp_st_calculado


def test_saida_revenda_cst60_cobrando_st_indevido():
    """SAÍDA, revenda interna de produto ST com CST 60: vICMSST DEVE ser 0.
    Emitente destacou R$ 50 → bitributação (ERRO_110), diferença a FAVOR do cliente."""
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA, saida=True)
    item = _item(cst="60", csosn=None, mod_bc_st=None, v_icms_st=Decimal("50.00"))

    r = _engine().auditar_item(item, op)

    assert r.status == StatusAuditoria.DIVERGENTE
    assert "ERRO_110_ST_INDEVIDO_REVENDA" in r.codigos_erro
    assert r.divergencia_icms_st == Decimal("50.00")     # positivo = pago a maior
    assert r.memoria.icms_st_calculado == Decimal("0.00")


def test_saida_revenda_cst60_sem_st_ok():
    """SAÍDA CST 60 com vICMSST = 0 (correto): sem novo ST devido → OK."""
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA, saida=True)
    item = _item(cst="60", csosn=None, mod_bc_st=None, v_icms_st=Decimal("0"))

    r = _engine().auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    assert r.codigos_erro == []


def test_saida_substituto_cst10_calcula_igual_a_entrada():
    """SAÍDA como substituto (CST 10): mesmo cálculo de ST do motor de entradas.
    SP->MG, MVA 71,78% ajustada, ICMS-ST esperado = 177,50."""
    engine = StAuditEngine(
        MvaEmMemoria({("87082919", "0107500", "MG"): "71.78"}),
        EnquadramentoEmMemoria(), FcpEmMemoria(),
    )
    item = ItemFiscal(
        numero_item=1, ncm="87082919", cest="0107500", cfop="6404", orig="0",
        cst="10", mod_bc_st=4, v_prod=Decimal("799.40"),
        v_bc=Decimal("799.40"), v_icms=Decimal("87.76"), p_icms=Decimal("12"),
        v_bc_st=Decimal("1473.69"), v_icms_st=Decimal("177.50"),
    )
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA, saida=True)

    r = engine.auditar_item(item, op)

    assert r.status == StatusAuditoria.OK            # destaque correto
    assert r.memoria.icms_st_calculado == Decimal("177.50")


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
