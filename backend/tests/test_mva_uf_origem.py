"""MVA por UF de ORIGEM + fim do 0% silencioso (caso relatado em 06/08/2026).

Duas causas de raiz cobertas aqui:

1. A matriz de MVA só tinha UF de DESTINO, então o motor aplicava a margem de
   outro acordo. A MVA varia com o estado REMETENTE e a interna (origem ==
   destino) difere da interestadual — a busca agora recebe origem e destino,
   preferindo a origem EXATA ao curinga `"*"` DENTRO de cada nível de NCM.

2. Sem linha na matriz o motor assumia MVA 0% e calculava assim mesmo. Agora
   "tem MVA" = EXISTE LINHA (um 0,00 cadastrado é DECISÃO curada, não ausência)
   e a falta de linha vira ERRO_MVA_NAO_ENCONTRADA — atrás do gate de rollout
   `mva_fail_closed` (env NEXOS_ST_MVA_FAIL_CLOSED, DESLIGADO por padrão), com
   a trava histórica do modBCST=4 sempre ativa.
"""
from datetime import date
from decimal import Decimal

from app.modules.fiscal.domain.st import (
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
from app.modules.fiscal.infrastructure.matrizes_loaders import _MvaSnapshot

D = Decimal
DATA = date(2026, 6, 1)
NCM, CEST = "85122011", "0100100"
# Par que o seed de exemplo do MvaEmMemoria NÃO cobre — usado nos cenários de
# "matriz sem linha" (o seed traz 85122011/MG, 8512/SP e 33049910/RJ).
NCM_SEM, CEST_SEM = "84248219", "0102900"


def _engine(mva, *, fail_closed: bool = False) -> StAuditEngine:
    return StAuditEngine(
        mva_repo=mva,
        enquadramento_repo=EnquadramentoEmMemoria(),
        fcp_repo=FcpEmMemoria(),
        protocolo_repo=ProtocoloEmMemoria(),      # default: acordo existe
        mva_fail_closed=fail_closed,
    )


def _item(**kw) -> ItemFiscal:
    base = dict(
        numero_item=1, ncm=NCM, cest=CEST, cfop="6404", orig="0",
        cst="10", mod_bc_st=4, v_prod=D("1000"), q_com=D("1"),
        v_icms=D("120"), v_bc=D("1000"), p_icms=D("12"),
    )
    base.update(kw)
    return ItemFiscal(**base)


# ── 1. Precedência origem exata × curinga ─────────────────────────────────── #
def test_origem_exata_vence_curinga():
    """Regra geral cadastrada para qualquer origem NÃO pode sequestrar o par
    curado SP→MG: com as duas linhas, ganha a específica."""
    repo = MvaEmMemoria({
        (NCM, CEST, "*", "MG"): "40.00",     # vale para qualquer remetente
        (NCM, CEST, "SP", "MG"): "58.00",    # acordo específico SP→MG
    })
    info = repo.buscar(NCM, CEST, "SP", "MG", DATA)
    assert info.mva_original == D("58.00")
    assert info.uf_origem_casada == "SP"


def test_curinga_usado_quando_nao_ha_linha_especifica():
    """Sem linha para a origem da nota, a regra curinga responde (e a memória
    registra que veio do '*', não de um par curado)."""
    repo = MvaEmMemoria({
        (NCM, CEST, "*", "MG"): "40.00",
        (NCM, CEST, "SP", "MG"): "58.00",
    })
    info = repo.buscar(NCM, CEST, "PR", "MG", DATA)   # PR não tem linha própria
    assert info.mva_original == D("40.00")
    assert info.uf_origem_casada == "*"


def test_ncm_e_o_laco_externo_origem_e_o_desempate_interno():
    """NCM de 8 dígitos com regra CURINGA ganha de NCM de 6 dígitos com origem
    EXATA: o produto é mais determinante que o remetente. A especificidade da
    origem só desempata DENTRO do mesmo nível de NCM."""
    repo = MvaEmMemoria({
        (NCM, CEST, "*", "MG"): "40.00",        # NCM 8 dígitos, curinga
        ("851220", CEST, "SP", "MG"): "58.00",  # NCM 6 dígitos, origem exata
    })
    info = repo.buscar(NCM, CEST, "SP", "MG", DATA)
    assert info.mva_original == D("40.00")
    assert info.ncm_casado == NCM
    assert info.uf_origem_casada == "*"


def test_snapshot_do_banco_segue_a_mesma_precedencia():
    """O repositório hidratado do banco (_MvaSnapshot) e o seed em memória têm
    de responder igual — é o mesmo contrato do port."""
    snap = _MvaSnapshot({
        (NCM, CEST, "*", "MG"): (D("40.00"), 1, "regra geral"),
        (NCM, CEST, "SP", "MG"): (D("58.00"), 2, "Protocolo ICMS 41/08"),
    })
    exata = snap.buscar(NCM, CEST, "SP", "MG", DATA)
    assert exata.mva_original == D("58.00") and exata.matriz_id == 2
    assert exata.uf_origem_casada == "SP"

    curinga = snap.buscar(NCM, CEST, "PR", "MG", DATA)
    assert curinga.mva_original == D("40.00") and curinga.matriz_id == 1
    assert curinga.uf_origem_casada == "*"


def test_snapshot_sem_cest_respeita_a_origem_e_a_ambiguidade():
    """XML sem tag CEST: casa por NCM, origem exata antes do curinga; MVAs
    distintas dentro da MESMA origem continuam ambíguas (fail-closed)."""
    snap = _MvaSnapshot({
        (NCM, "0100100", "SP", "MG"): (D("58.00"), 2, None),
        (NCM, "0100100", "*", "MG"): (D("40.00"), 1, None),
    })
    info = snap.buscar(NCM, "", "SP", "MG", DATA)
    assert info.mva_original == D("58.00") and info.uf_origem_casada == "SP"

    ambiguo = _MvaSnapshot({
        (NCM, "0100100", "SP", "MG"): (D("58.00"), 2, None),
        (NCM, "0100101", "SP", "MG"): (D("71.78"), 3, None),
        (NCM, "0100100", "*", "MG"): (D("40.00"), 1, None),
    })
    # Ambíguo na origem EXATA trava — não escorrega para o curinga.
    assert ambiguo.buscar(NCM, "", "SP", "MG", DATA) is None


# ── 2. MVA interna ≠ interestadual ────────────────────────────────────────── #
def test_mva_interna_difere_da_interestadual_no_resultado():
    """Mesma mercadoria, MVA própria para a interna (MG→MG) e para SP→MG: os
    dois cálculos precisam sair diferentes — era exatamente o que a matriz sem
    UF de origem impedia."""
    repo = MvaEmMemoria({
        (NCM, CEST, "MG", "MG"): "30.00",    # interna
        (NCM, CEST, "SP", "MG"): "40.00",    # interestadual (sofre ajuste R-07)
    })
    eng = _engine(repo)

    interna = eng.auditar_item(
        _item(v_icms=D("180"), p_icms=D("18")),
        Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA),
    )
    inter = eng.auditar_item(
        _item(), Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    )

    assert interna.memoria.mva_original == D("30.00")
    assert interna.memoria.mva_foi_ajustada is False       # interna não ajusta
    assert interna.memoria.base_st_calculada == D("1300.00")

    assert inter.memoria.mva_original == D("40.00")
    assert inter.memoria.mva_foi_ajustada is True
    assert inter.memoria.base_st_calculada == D("1502.44")
    assert interna.memoria.base_st_calculada != inter.memoria.base_st_calculada


def test_par_errado_nao_e_aproveitado():
    """Só há linha para SP→MG. Nota RS→MG não pode herdar a MVA de SP: sem
    curinga, não há regra — o motor fica sem MVA para o par."""
    repo = MvaEmMemoria({(NCM_SEM, CEST_SEM, "SP", "MG"): "58.00"})
    assert repo.buscar(NCM_SEM, CEST_SEM, "SP", "MG", DATA).mva_original == D("58.00")
    assert repo.buscar(NCM_SEM, CEST_SEM, "RS", "MG", DATA) is None


# ── 3. Fail-closed atrás do gate de rollout ───────────────────────────────── #
def _sem_linha() -> MvaEmMemoria:
    """Matriz padrão do seed — que NÃO cobre o par NCM_SEM/CEST_SEM→MG."""
    return MvaEmMemoria()


def _item_sem_matriz(**kw) -> ItemFiscal:
    return _item(ncm=NCM_SEM, cest=CEST_SEM, **kw)


def test_gate_desligado_preserva_o_comportamento_de_hoje_modbcst6():
    """Padrão (NEXOS_ST_MVA_FAIL_CLOSED=false): sem linha e modBCST=6 segue
    calculando pelo valor da operação, sem erro de MVA — nada regride."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item_sem_matriz(mod_bc_st=6, v_bc_st=D("1000.00"), v_icms_st=D("60.00"))

    r = _engine(_sem_linha()).auditar_item(item, op)

    assert r.status != StatusAuditoria.NAO_AUDITAVEL
    assert "ERRO_MVA_NAO_ENCONTRADA" not in r.codigos_erro
    assert r.memoria.mva_aplicada == D("0")
    assert r.memoria.base_st_calculada == D("1000.00")     # valor da operação


def test_gate_ligado_modbcst6_sem_linha_vira_mva_nao_encontrada():
    """Com o gate ligado, o 0% silencioso acaba: sem linha na matriz o item é
    NAO_AUDITAVEL com código reprocessável, mesmo com modBCST=6."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item_sem_matriz(mod_bc_st=6, v_bc_st=D("1000.00"), v_icms_st=D("60.00"))

    r = _engine(_sem_linha(), fail_closed=True).auditar_item(item, op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == ["ERRO_MVA_NAO_ENCONTRADA"]
    # A observação diz QUAL chave falta — a pendência vira tarefa de cadastro.
    assert "SP" in (r.observacao or "") and "MG" in (r.observacao or "")
    assert NCM_SEM in (r.observacao or "")


def test_gate_desligado_modbcst_ausente_sem_linha_segue_calculando():
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item_sem_matriz(mod_bc_st=None, v_icms=D("180"), p_icms=D("18"))

    r = _engine(_sem_linha()).auditar_item(item, op)

    assert r.status != StatusAuditoria.NAO_AUDITAVEL
    assert r.memoria.base_st_calculada == D("1000.00")     # valor da operação


def test_gate_ligado_modbcst_ausente_sem_linha_vira_mva_nao_encontrada():
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item_sem_matriz(mod_bc_st=None, v_icms=D("180"), p_icms=D("18"))

    r = _engine(_sem_linha(), fail_closed=True).auditar_item(item, op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == ["ERRO_MVA_NAO_ENCONTRADA"]


def test_trava_do_modbcst4_vale_com_o_gate_desligado():
    """A trava histórica (XML declarou base por MVA e a matriz não tem a linha)
    NÃO depende do gate — ela já existia e não pode regredir."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = _engine(_sem_linha()).auditar_item(_item_sem_matriz(mod_bc_st=4), op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == ["ERRO_MVA_NAO_ENCONTRADA"]


# ── 4. MVA 0,00 curada = decisão, não ausência ────────────────────────────── #
def test_linha_curada_com_mva_zero_calcula_por_valor_da_operacao_sem_erro():
    """0,00 cadastrado é DECISÃO (base = valor da operação por norma): calcula
    normalmente, sem ERRO_MVA_NAO_ENCONTRADA e sem ERRO_109, MESMO com o gate
    de fail-closed ligado."""
    repo = MvaEmMemoria({(NCM, CEST, "SP", "MG"): "0.00"})
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    # Base = 1000 (valor da operação); ST = 1000 × 18% − 120 = 60.
    item = _item(mod_bc_st=6, v_bc_st=D("1000.00"), v_icms_st=D("60.00"))

    r = _engine(repo, fail_closed=True).auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    assert r.erros == ()
    assert r.memoria.base_st_calculada == D("1000.00")
    assert r.memoria.icms_st_calculado == D("60.00")
    assert r.memoria.mva_original == D("0")


def test_mva_zero_curada_registra_na_memoria_que_veio_da_matriz():
    """A base por valor da operação precisa ser rastreável até a linha curada —
    nunca parecer omissão de cadastro."""
    repo = MvaEmMemoria({(NCM, CEST, "SP", "MG"): "0.00"})
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(mod_bc_st=6, v_bc_st=D("1000.00"), v_icms_st=D("60.00"))

    r = _engine(repo, fail_closed=True).auditar_item(item, op)

    motivo = r.memoria.motivo_nao_ajuste or ""
    assert "matriz" in motivo.lower()
    assert "VALOR DA OPERAÇÃO" in motivo


def test_mva_zero_curada_leva_matriz_id_e_base_legal_para_a_memoria():
    snap = _MvaSnapshot({(NCM, CEST, "SP", "MG"): (D("0.00"), 42, "RICMS/MG Anexo VII")})
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(mod_bc_st=6, v_bc_st=D("1000.00"), v_icms_st=D("60.00"))

    r = _engine(snap, fail_closed=True).auditar_item(item, op)

    assert r.memoria.mva_matriz_id == 42
    assert r.memoria.mva_base_legal == "RICMS/MG Anexo VII"


# ── Por que a margem saiu zerada (a pergunta que a tela não respondia) ───────
def test_margem_zerada_por_falta_de_regra_explica_se_na_memoria():
    """Com o gate DESLIGADO não há código de erro: a memória é a única pista.

    Sem isto a tela mostra "0,00%" com a frase genérica sobre o que é margem
    presumida, e não há como saber se falta cadastro ou se foi decisão curada.
    """
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item_sem_matriz(mod_bc_st=None, v_icms=D("120"), p_icms=D("12"))

    r = _engine(_sem_linha()).auditar_item(item, op)

    motivo = r.memoria.mva_zero_motivo or ""
    assert motivo, "margem zerada sem explicação é o bug que estamos matando"
    assert "sem MVA cadastrada" in motivo
    assert NCM_SEM in motivo and "SP" in motivo and "MG" in motivo   # a chave que falta
    assert "Cadastre a MVA do par" in motivo                          # e o que fazer


def test_margem_zerada_por_decisao_curada_diz_que_foi_decisao():
    """Linha 0,00 cadastrada é legítima — o texto não pode acusar falta."""
    mva = MvaEmMemoria({(NCM, CEST, "SP", "MG"): D("0")})
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = _engine(mva).auditar_item(_item(mod_bc_st=None), op)

    motivo = r.memoria.mva_zero_motivo or ""
    assert "decisão da matriz" in motivo
    assert "sem MVA cadastrada" not in motivo


def test_margem_normal_nao_inventa_explicacao():
    """Não-regressão: com MVA > 0 o campo fica vazio (nada a explicar)."""
    mva = MvaEmMemoria({(NCM, CEST, "SP", "MG"): D("42")})
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)

    r = _engine(mva).auditar_item(_item(mod_bc_st=4), op)

    assert r.memoria.mva_zero_motivo is None
