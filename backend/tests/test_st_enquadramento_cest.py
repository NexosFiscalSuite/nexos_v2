"""Enquadramento × CEST ausente no XML (caso Irrigacer, jul/2026).

O emitente que NEM tratou o item como ST geralmente não manda a tag CEST — e é
justamente essa nota que mais precisa de auditoria. Regras cobertas:
  - snapshot casa por NCM quando o XML vem sem CEST (enquadramento e MVA);
  - TN SEM cadastro vira NAO_AUDITAVEL acionável (código de erro, entra no
    reprocesso retroativo), distinto do TN por decisão de cadastro (sem código);
  - CEST do XML divergente do cadastro é apontado com a lista cadastrada.
"""
from datetime import date
from decimal import Decimal

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
    _EnquadramentoSnapshot,
    _MvaSnapshot,
)

DATA = date(2026, 6, 15)
D = Decimal
NCM, CEST, UF = "84248219", "0102900", "MG"


def _snap_enq(dados) -> _EnquadramentoSnapshot:
    return _EnquadramentoSnapshot(dados)


# ── Snapshot de enquadramento ────────────────────────────────────────────── #
def test_regime_casa_por_ncm_quando_xml_sem_cest():
    snap = _snap_enq({(NCM, CEST, UF): Regime.ST})
    assert snap.regime(NCM, "", "MG", UF, DATA) == Regime.ST          # sem tag CEST
    assert snap.regime(NCM, CEST, "MG", UF, DATA) == Regime.ST        # com CEST exato
    assert snap.regime("99999999", "", "MG", UF, DATA) == Regime.TN   # não cadastrado


def test_regime_conflito_entre_cests_abre_o_portao():
    """CESTs do mesmo NCM com regimes distintos e XML sem CEST: abre o portão
    (ST) — a checagem de MVA a jusante trava com transparência se for ambígua."""
    snap = _snap_enq({(NCM, CEST, UF): Regime.ST, (NCM, "0102901", UF): Regime.TN})
    assert snap.regime(NCM, "", "MG", UF, DATA) == Regime.ST


def test_explicar_tn_distingue_os_tres_casos():
    # 1) TN explícito por cadastro → None (fora do motor POR DECISÃO)
    snap = _snap_enq({(NCM, CEST, UF): Regime.TN})
    assert snap.explicar_tn(NCM, CEST, UF) is None
    assert snap.explicar_tn(NCM, "", UF) is None       # fallback por NCM achou o TN

    # 2) Sem cadastro nenhum → mensagem manda cadastrar
    vazio = _snap_enq({})
    msg = vazio.explicar_tn(NCM, "", UF)
    assert msg and "sem enquadramento cadastrado" in msg and NCM in msg and UF in msg

    # 3) CEST do XML não casa com o cadastrado → aponta a diferença
    snap_st = _snap_enq({(NCM, CEST, UF): Regime.ST})
    msg = snap_st.explicar_tn(NCM, "9999999", UF)
    assert msg and "não casa" in msg and CEST in msg


# ── Snapshot de MVA ──────────────────────────────────────────────────────── #
def test_mva_fallback_por_ncm_sem_cest():
    uma = _MvaSnapshot({(NCM, CEST, UF): (D("40"), 7)})
    info = uma.buscar(NCM, "", UF, DATA)
    assert info and info.mva_original == D("40") and info.matriz_id == 7

    iguais = _MvaSnapshot({(NCM, CEST, UF): (D("40"), 7), (NCM, "0102901", UF): (D("40"), 8)})
    assert iguais.buscar(NCM, "", UF, DATA).mva_original == D("40")

    distintas = _MvaSnapshot({(NCM, CEST, UF): (D("40"), 7), (NCM, "0102901", UF): (D("55"), 8)})
    assert distintas.buscar(NCM, "", UF, DATA) is None   # ambíguo: fail-closed

    # Com CEST no XML, o exato continua mandando.
    assert distintas.buscar(NCM, "0102901", UF, DATA).mva_original == D("55")


# ── Motor de ponta a ponta com os snapshots reais ────────────────────────── #
def _item_sem_cest(**kw) -> ItemFiscal:
    base = dict(
        numero_item=1, ncm=NCM, cest="", cfop="5405", orig="0",
        cst="10", mod_bc_st=4, v_prod=D("1000"), q_com=D("1"),
        v_icms=D("180"), v_bc=D("1000"), p_icms=D("18"),
    )
    base.update(kw)
    return ItemFiscal(**base)


def _engine_snapshots(enq: _EnquadramentoSnapshot, mva: _MvaSnapshot) -> StAuditEngine:
    return StAuditEngine(mva_repo=mva, enquadramento_repo=enq, fcp_repo=FcpEmMemoria())


def test_item_sem_cest_e_auditado_quando_enquadrado():
    """MG→MG interna, XML sem CEST, NCM cadastrado (ST + MVA 40): o motor audita
    — base 1000 × 1,40 = 1400; ST = 1400 × 18% − 180 = 72."""
    eng = _engine_snapshots(
        _snap_enq({(NCM, CEST, UF): Regime.ST}),
        _MvaSnapshot({(NCM, CEST, UF): (D("40"), 7)}),
    )
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = eng.auditar_item(_item_sem_cest(v_bc_st=D("1400.00"), v_icms_st=D("72.00")), op)

    assert r.status == StatusAuditoria.OK
    assert r.memoria.mva_original == D("40")
    assert r.memoria.base_st_calculada == D("1400.00")


def test_item_sem_cadastro_vira_pendencia_acionavel():
    """Sem enquadramento cadastrado: NAO_AUDITAVEL COM código (entra no
    reprocesso retroativo) e observação dizendo o que cadastrar."""
    eng = _engine_snapshots(_snap_enq({}), _MvaSnapshot({}))
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = eng.auditar_item(_item_sem_cest(cst="20"), op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == ["ERRO_ENQUADRAMENTO_NAO_CADASTRADO"]
    assert "cadastre" in (r.observacao or "").lower()


def test_tn_por_cadastro_segue_sem_codigo():
    """TN explícito nas matrizes: legítimo, sem código de erro (não entra no
    reprocesso) e com a mensagem clássica de fora do motor."""
    eng = _engine_snapshots(_snap_enq({(NCM, CEST, UF): Regime.TN}), _MvaSnapshot({}))
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = eng.auditar_item(_item_sem_cest(cest=CEST, cst="20"), op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == []
    assert "TN por cadastro" in (r.observacao or "")   # texto novo ≠ legado mudo
    assert "fora do motor de ST" in (r.observacao or "")
