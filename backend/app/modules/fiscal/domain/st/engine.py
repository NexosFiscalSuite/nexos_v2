"""Motor de auditoria de ICMS ST — orquestra o pipeline do CALC_ICMS_ST.

Função central pura: recebe os fatos do item + os repositórios (ports) e
devolve um ResultadoAuditoria. Não levanta exceção por nota suja — input
podre vira diagnóstico, nunca crash do lote.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .aliquotas import AliquotaResolver, AliquotasReferencia
from .enums import Regime
from .errors import ErroST
from .model import (
    ItemFiscal,
    MemoriaCalculo,
    Operacao,
    ResultadoAuditoria,
    StatusAuditoria,
)
from .money import ZERO, aplicar_percentual, centavos
from .mva import calcular_mva
from .ports import (
    AliquotaRepository,
    EnquadramentoRepository,
    FcpRepository,
    MvaRepository,
    ProtocoloRepository,
)
from .strategies import (
    BaseMva,
    BaseValorOperacao,
    aplicar_reducao_base,
    base_strategy_for,
    calcular_deducao,
)

# Gravada em cada memória de cálculo: permite responder "qual regra o sistema
# aplicou na época" (defensibilidade). Bump a cada mudança de regra de cálculo.
ENGINE_VERSION = "2.1.0"


class _AssumeProtocolo:
    """Default quando nenhuma matriz de protocolo é injetada: assume o acordo
    vigente — a interestadual é auditada como responsabilidade do REMETENTE
    (comportamento histórico, conservador). A memória registra fonte="assumido"."""

    fonte = "assumido"

    def tem_protocolo(self, uf_orig: str, uf_dest: str, data: date, ncm: str = "") -> bool:
        return True

# Régua de centavos por item (Seção 6 do CALC_ICMS_Proprio).
TOLERANCIA_ITEM = Decimal("0.02")
# Régua do somatório da nota.
TOLERANCIA_NOTA = Decimal("0.05")
# Tolerância de percentual para acusar ajuste indevido de MVA (pontos).
TOLERANCIA_MVA_PCT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class StAuditEngine:
    """Auditor de ST. Injete os repositórios; o resolver de alíquota é concreto."""

    mva_repo: MvaRepository
    enquadramento_repo: EnquadramentoRepository
    fcp_repo: FcpRepository
    # Intra (modal/FCP) vem de matriz com vigência; a referência em código serve
    # a testes/dev — em produção o orquestrador injeta o snapshot do banco.
    aliquota_repo: AliquotaRepository = field(default_factory=AliquotasReferencia)
    protocolo_repo: ProtocoloRepository = field(default_factory=_AssumeProtocolo)
    aliquotas: AliquotaResolver = AliquotaResolver()

    def auditar_item(self, item: ItemFiscal, operacao: Operacao) -> ResultadoAuditoria:
        # 1. Portão de enquadramento — só auditamos itens que SÃO ST.
        regime = self.enquadramento_repo.regime(
            item.ncm, item.cest, operacao.uf_emit, operacao.uf_dest, operacao.data
        )
        if regime != Regime.ST:
            # TN sem cadastro (ou CEST que não casa) não é "fora do motor por
            # decisão": vira pendência COM código — a tela diz o que cadastrar e
            # o reprocesso destrava a nota quando o cadastro chegar. TN por
            # cadastro explícito ganha texto próprio (≠ do legado pré-fallback,
            # que o reprocesso re-rotula uma única vez).
            if regime == Regime.TN:
                explicar = getattr(self.enquadramento_repo, "explicar_tn", None)
                if explicar is not None:
                    detalhe = explicar(item.ncm, item.cest, operacao.uf_dest)
                    if detalhe:
                        return self._nao_auditavel(
                            item, ErroST.ENQUADRAMENTO_NAO_CADASTRADO, observacao=detalhe
                        )
                    return self._nao_auditavel(
                        item, "regime TN por cadastro nas matrizes (fora do motor de ST)"
                    )
            return self._nao_auditavel(item, f"regime {regime.value} (fora do motor de ST)")

        # Bifurcação por tpNF e CST 60/500 (ST já retido na cadeia). SAÍDA de
        # revenda: não se recolhe de novo — auditoria própria (Cenário 1).
        # ENTRADA com ST retido: nada a calcular nesta compra — OK registrando o
        # retido (insumo do ressarcimento). Demais casos: cálculo de ST normal.
        if item.cst_csosn in ("60", "500"):
            if operacao.saida:
                return self._auditar_revenda_st_retido(item, operacao, regime)
            return self._auditar_entrada_st_retido(item, regime)

        # 2. Estratégia de base — núcleo v1 cobre MVA (4) e Valor da Operação (6).
        #    modBCST AUSENTE (fornecedor nem tratou o item como ST — o caso
        #    típico da antecipação/sem retenção): a matriz decide, mesma regra
        #    de ouro do passo 4 — MVA cadastrada → base MVA; senão → valor da
        #    operação. Modalidades 0/1/2/3/5 (pauta/listas) seguem sem suporte,
        #    agora com código reprocessável.
        base_strategy = base_strategy_for(item.mod_bc_st)
        if base_strategy is None and item.mod_bc_st is None:
            mva_previa = self.mva_repo.buscar(
                item.ncm, item.cest, operacao.uf_dest, operacao.data
            )
            tem_mva_previa = mva_previa is not None and mva_previa.mva_original > ZERO
            base_strategy = BaseMva() if tem_mva_previa else BaseValorOperacao()
        if base_strategy is None:
            return self._nao_auditavel(
                item, ErroST.MODBCST_NAO_SUPORTADO,
                observacao=f"modBCST={item.mod_bc_st} (pauta/preço tabelado/listas) "
                           "ainda sem suporte no motor — pendência reprocessável.",
            )

        # 3. Alíquotas. A interestadual é lei em fórmula (código); a interna vem
        #    da matriz VIGENTE NA DATA — sem alíquota cadastrada, o motor não
        #    assume a taxa atual (fail-closed, ADR-0002).
        aliq_uf = self.aliquota_repo.buscar(operacao.uf_dest, operacao.data)
        if aliq_uf is None:
            return self._nao_auditavel(item, ErroST.ALIQUOTA_NAO_ENCONTRADA)
        alq_inter = self.aliquotas.alq_inter(
            operacao.uf_emit, operacao.uf_dest, item.orig, operacao.data
        )
        alq_intra_modal = aliq_uf.modal
        alq_intra_efetiva = aliq_uf.efetiva   # R-07: carga efetiva no ajuste de MVA
        alq_operacao = alq_inter if operacao.interestadual else alq_intra_modal

        erros: list[ErroST] = []

        # 4. MVA. Regra de ouro: a MVA CADASTRADA define a modalidade da base —
        #    não o modBCST do XML (que o emitente pode ter errado). Sem isso, uma
        #    nota com modBCST=6 (valor da operação) num produto base-MVA seria
        #    calculada a menor SILENCIOSAMENTE.
        mva_info = self.mva_repo.buscar(item.ncm, item.cest, operacao.uf_dest, operacao.data)
        tem_mva = mva_info is not None and mva_info.mva_original > ZERO
        exige_mva = base_strategy.espera_mva   # XML declarou modBCST=4

        if exige_mva and not tem_mva:
            # TRAVA DE SEGURANÇA: base por MVA mas a matriz não tem MVA → não
            # inventa um cálculo com MVA 0; classifica como não auditável.
            return self._nao_auditavel(item, ErroST.MVA_NAO_ENCONTRADA)

        if tem_mva:
            mva = calcular_mva(
                mva_original=mva_info.mva_original,
                alq_inter=alq_inter,
                alq_intra=alq_intra_efetiva,   # R-07: carga efetiva no denominador
                crt=operacao.crt,
                interestadual=operacao.interestadual,
            )
            mva_original, mva_aplicada = mva_info.mva_original, mva.mva_aplicada
            base_integral = BaseMva().base_integral(item, mva_aplicada)
            if not exige_mva:
                # Produto é base-MVA, mas o XML não usou modBCST=4: emitente errou
                # a base. Recalculamos com a MVA correta e marcamos o erro.
                erros.append(ErroST.MODBCST_INCOMPATIVEL)
            elif not mva.ajustada and item.p_mva_st > mva_original + TOLERANCIA_MVA_PCT:
                erros.append(ErroST.MVA_AJUSTADA_INDEVIDA)
        else:
            # Sem MVA na matriz e modBCST≠4 → base = valor da operação (modBCST 6
            # legítimo, NT 2020.005).
            mva = None
            mva_original = mva_aplicada = ZERO
            base_integral = base_strategy.base_integral(item, mva_aplicada)
            if item.p_mva_st > ZERO:
                erros.append(ErroST.MVA_AJUSTADA_INDEVIDA)

        # 5. Base do ST (com redução, Método A).
        base_st_calc = aplicar_reducao_base(base_integral, item.p_red_bc_st)

        # 6. Débito do ST pela carga interna modal do destino.
        icms_st_debito = aplicar_percentual(base_st_calc, alq_intra_modal)

        # 7. Dedução do ICMS próprio (real / teórica / trava do zero).
        deducao = calcular_deducao(item, operacao, alq_operacao)
        if deducao.erro is not None:
            erros.append(deducao.erro)
        icms_st_calc = icms_st_debito - deducao.valor
        if icms_st_calc < ZERO:
            icms_st_calc = ZERO

        # 8. FCP-ST em trilha paralela. Não-cumulatividade (NT 2016.002): o FCP
        #    da operação própria é creditado, então vFCPST = débito − FCP próprio.
        #    Sem isso, a carga final ultrapassaria o teto do fundo (bitributação).
        p_fcp_esperado = self.fcp_repo.aliquota_st(item.ncm, operacao.uf_dest, operacao.data)
        fcp_st_debito = aplicar_percentual(base_st_calc, p_fcp_esperado)
        fcp_st_calc = fcp_st_debito - item.v_fcp
        if fcp_st_calc < ZERO:
            fcp_st_calc = ZERO

        # 9. RESPONSABILIDADE na interestadual (matriz de protocolo), resolvida
        #    ANTES da memória: fica registrado o que o motor decidiu E de onde
        #    veio a resposta ("assumido" = default sem matriz, nunca silencioso).
        #    Tri-state: True = acordo vigente (remetente é o substituto);
        #    False = par CURADO sem acordo aplicável (antecipação do destinatário);
        #    None = par nunca avaliado na matriz → fail-closed, não decide.
        tem_protocolo: bool | None = None
        protocolo_fonte: str | None = None
        if operacao.interestadual:
            tem_protocolo = self.protocolo_repo.tem_protocolo(
                operacao.uf_emit, operacao.uf_dest, operacao.data, item.ncm
            )
            protocolo_fonte = getattr(self.protocolo_repo, "fonte", "matriz")
            if tem_protocolo is None:
                return self._nao_auditavel(item, ErroST.PROTOCOLO_NAO_AVALIADO)

        # 10. Memória (independe das comparações — vale para os dois fluxos abaixo).
        memoria = MemoriaCalculo(
            regime=regime.value,
            mva_original=mva_original,
            mva_aplicada=mva_aplicada,
            mva_foi_ajustada=bool(mva and mva.ajustada),
            motivo_nao_ajuste=mva.motivo_nao_ajuste if mva else None,
            alq_inter=alq_inter,
            alq_intra=alq_intra_modal,
            base_st_calculada=centavos(base_st_calc),
            icms_st_debito=centavos(icms_st_debito),
            deducao_aplicada=centavos(deducao.valor),
            deducao_tipo=deducao.tipo,
            icms_st_calculado=centavos(icms_st_calc),
            fcp_st_debito=centavos(fcp_st_debito),
            fcp_st_deducao=centavos(item.v_fcp),
            fcp_st_calculado=centavos(fcp_st_calc),
            engine_version=ENGINE_VERSION,
            mva_matriz_id=(mva_info.matriz_id if tem_mva else None),
            aliquota_matriz_id=aliq_uf.matriz_id,
            tem_protocolo=tem_protocolo,
            protocolo_fonte=protocolo_fonte,
            mva_base_legal=(getattr(mva_info, "base_legal", None) if tem_mva else None),
            aliquota_base_legal=getattr(aliq_uf, "base_legal", None),
            custo_produto=centavos(item.v_prod),
            custo_frete=centavos(item.v_frete),
            custo_frete_cte=centavos(item.v_frete_cte),
            custo_seguro=centavos(item.v_seg),
            custo_outras=centavos(item.v_outro),
            custo_desconto=centavos(item.v_desc),
            custo_ipi=centavos(item.v_ipi),
        )

        # 11. Sem acordo vigente origem→destino, o remetente NÃO é o substituto:
        #     a ST vira antecipação do destinatário (recolhe via guia local).
        if tem_protocolo is False:
            return self._resultado_antecipacao(item, icms_st_calc, fcp_st_calc, memoria, erros)

        # 12. Com protocolo (ou operação interna): a ST é do REMETENTE — auditamos
        #     o que veio destacado no XML contra o cálculo.
        div_bc = centavos(item.v_bc_st) - centavos(base_st_calc)
        if abs(div_bc) > TOLERANCIA_ITEM:
            erros.append(ErroST.BC_ST_DIVERGENTE)

        div_icms_st = centavos(item.v_icms_st) - centavos(icms_st_calc)
        if abs(div_icms_st) > TOLERANCIA_ITEM:
            erros.append(ErroST.VALOR_ST_DIVERGENTE)

        div_fcp = centavos(item.v_fcp_st) - centavos(fcp_st_calc)
        if abs(div_fcp) > TOLERANCIA_ITEM:
            erros.append(ErroST.FCP_ST_DIVERGENTE)

        status = StatusAuditoria.DIVERGENTE if erros else StatusAuditoria.OK
        return ResultadoAuditoria(
            numero_item=item.numero_item,
            status=status,
            erros=tuple(erros),
            divergencia_icms_st=div_icms_st,
            divergencia_fcp_st=div_fcp,
            memoria=memoria,
        )

    def _resultado_antecipacao(
        self,
        item: ItemFiscal,
        icms_st_calc: Decimal,
        fcp_st_calc: Decimal,
        memoria: MemoriaCalculo,
        erros_calc: list[ErroST],
    ) -> ResultadoAuditoria:
        """Interestadual SEM protocolo: o remetente corretamente NÃO retém a ST.
        A obrigação é do destinatário (nosso cliente) por antecipação, recolhida
        em guia local. O valor devido = ST calculado, líquido do que por acaso já
        tenha vindo retido no XML (diferença negativa = falta antecipar)."""
        devido = centavos(icms_st_calc)
        diferenca = centavos(item.v_icms_st) - devido          # XML(0) − devido = falta
        diferenca_fcp = centavos(item.v_fcp_st) - centavos(fcp_st_calc)
        tem_obrigacao = abs(diferenca) > TOLERANCIA_ITEM
        erros = (
            (ErroST.ST_ANTECIPACAO_DESTINATARIO, *erros_calc)
            if tem_obrigacao else tuple(erros_calc)
        )
        obs = (
            f"Interestadual SEM protocolo de ST: o remetente não é o substituto. "
            f"Antecipação de R$ {devido} devida pelo destinatário (recolher via guia local)."
            if tem_obrigacao else
            "Interestadual sem protocolo e sem ST a recolher — nada a antecipar."
        )
        status = StatusAuditoria.DIVERGENTE if erros else StatusAuditoria.OK
        return ResultadoAuditoria(
            numero_item=item.numero_item,
            status=status,
            erros=erros,
            divergencia_icms_st=diferenca,
            divergencia_fcp_st=diferenca_fcp,
            memoria=memoria,
            observacao=obs,
        )

    def auditar_nota(
        self, itens: list[ItemFiscal], operacao: Operacao
    ) -> list[ResultadoAuditoria]:
        """Audita todos os itens e aplica a régua do somatório (R$ 0,05/nota).

        Mesmo que cada item passe na régua de 0,02, um desvio sistemático que
        só aparece no agregado é sinalizado no último item auditável.
        """
        resultados = [self.auditar_item(i, operacao) for i in itens]
        soma_div = sum(
            (r.divergencia_icms_st for r in resultados if r.memoria), ZERO
        )
        if abs(soma_div) > TOLERANCIA_NOTA:
            for idx in range(len(resultados) - 1, -1, -1):
                r = resultados[idx]
                if r.memoria and not r.divergente:
                    resultados[idx] = ResultadoAuditoria(
                        numero_item=r.numero_item,
                        status=StatusAuditoria.DIVERGENTE,
                        erros=(ErroST.VALOR_ST_DIVERGENTE,),
                        divergencia_icms_st=r.divergencia_icms_st,
                        divergencia_fcp_st=r.divergencia_fcp_st,
                        memoria=r.memoria,
                        observacao="Somatório da nota excede R$ 0,05 (desvio sistemático).",
                    )
                    break
        return resultados

    def _auditar_revenda_st_retido(
        self, item: ItemFiscal, operacao: Operacao, regime: Regime
    ) -> ResultadoAuditoria:
        """Cenário 1 (saída): revenda de produto com ST já retido (CST 60/CSOSN 500).

        Nesta operação NÃO se recolhe ST de novo — o vICMSST destacado deve ser
        ZERO. Se houver valor, é pagamento indevido (bitributação): a diferença
        é positiva (a FAVOR do cliente, imposto pago a maior, passível de estorno).
        """
        diferenca = centavos(item.v_icms_st) - ZERO          # esperado = 0
        indevido = item.v_icms_st > TOLERANCIA_ITEM
        erros = (ErroST.ST_INDEVIDO_REVENDA,) if indevido else ()
        memoria = MemoriaCalculo(
            regime=regime.value, mva_original=ZERO, mva_aplicada=ZERO,
            mva_foi_ajustada=False,
            motivo_nao_ajuste="ST retido anteriormente (CST 60/500) — sem novo recolhimento",
            alq_inter=ZERO, alq_intra=ZERO, base_st_calculada=ZERO, icms_st_debito=ZERO,
            deducao_aplicada=ZERO, deducao_tipo="zero", icms_st_calculado=ZERO,
            fcp_st_debito=ZERO, fcp_st_deducao=ZERO, fcp_st_calculado=ZERO,
            engine_version=ENGINE_VERSION,
        )
        obs = (
            "ST destacado numa revenda com ST já retido (CST 60/500): pagamento a "
            "maior, passível de estorno." if indevido else
            "Revenda com ST retido anteriormente — sem novo ST devido (correto)."
        )
        return ResultadoAuditoria(
            numero_item=item.numero_item,
            status=StatusAuditoria.DIVERGENTE if erros else StatusAuditoria.OK,
            erros=erros, divergencia_icms_st=diferenca, memoria=memoria, observacao=obs,
        )

    def _auditar_entrada_st_retido(self, item: ItemFiscal, regime: Regime) -> ResultadoAuditoria:
        """COMPRA com ST já retido na cadeia (CST 60 / CSOSN 500): não há ST a
        calcular nesta entrada — o imposto veio retido pelo substituto. O item
        sai OK e os valores retidos do XML (vICMSSTRet/vBCSTRet/vICMSSubstituto)
        ficam registrados como insumo do fluxo de ressarcimento/complemento."""
        memoria = MemoriaCalculo(
            regime=regime.value, mva_original=ZERO, mva_aplicada=ZERO,
            mva_foi_ajustada=False,
            motivo_nao_ajuste="ST retido na cadeia (CST 60/500) — entrada sem novo ST",
            alq_inter=ZERO, alq_intra=ZERO, base_st_calculada=ZERO, icms_st_debito=ZERO,
            deducao_aplicada=ZERO, deducao_tipo="zero", icms_st_calculado=ZERO,
            fcp_st_debito=ZERO, fcp_st_deducao=ZERO, fcp_st_calculado=ZERO,
            engine_version=ENGINE_VERSION,
        )
        obs = (
            f"Compra com ST retido na cadeia (CST 60/500). Retido informado no XML: "
            f"R$ {centavos(item.v_icms_st_ret)} (base R$ {centavos(item.v_bc_st_ret)})."
            if item.v_icms_st_ret > ZERO else
            "Compra com ST retido na cadeia (CST 60/500) — sem ST a auditar nesta entrada."
        )
        return ResultadoAuditoria(
            numero_item=item.numero_item, status=StatusAuditoria.OK,
            memoria=memoria, observacao=obs,
        )

    @staticmethod
    def _nao_auditavel(
        item: ItemFiscal, motivo: ErroST | str, observacao: str | None = None
    ) -> ResultadoAuditoria:
        """NAO_AUDITAVEL com motivo. Se vier um ErroST, expõe o código no erro
        e a mensagem na observação (feedback claro, nunca silencioso); uma
        `observacao` explícita, mais específica que a genérica do enum, vence."""
        if isinstance(motivo, ErroST):
            return ResultadoAuditoria(
                numero_item=item.numero_item,
                status=StatusAuditoria.NAO_AUDITAVEL,
                erros=(motivo,),
                observacao=observacao or motivo.mensagem,
            )
        return ResultadoAuditoria(
            numero_item=item.numero_item,
            status=StatusAuditoria.NAO_AUDITAVEL,
            observacao=observacao or motivo,
        )
