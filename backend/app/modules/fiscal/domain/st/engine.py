"""Motor de auditoria de ICMS ST — orquestra o pipeline do CALC_ICMS_ST.

Função central pura: recebe os fatos do item + os repositórios (ports) e
devolve um ResultadoAuditoria. Não levanta exceção por nota suja — input
podre vira diagnóstico, nunca crash do lote.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .aliquotas import AliquotaResolver
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
from .ports import EnquadramentoRepository, FcpRepository, MvaRepository, ProtocoloRepository
from .strategies import BaseMva, aplicar_reducao_base, base_strategy_for, calcular_deducao


class _AssumeProtocolo:
    """Default quando nenhuma matriz de protocolo é injetada: assume o acordo
    vigente — a interestadual é auditada como responsabilidade do REMETENTE
    (comportamento histórico, conservador)."""

    def tem_protocolo(self, uf_orig: str, uf_dest: str, data: date) -> bool:
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
    protocolo_repo: ProtocoloRepository = field(default_factory=_AssumeProtocolo)
    aliquotas: AliquotaResolver = AliquotaResolver()

    def auditar_item(self, item: ItemFiscal, operacao: Operacao) -> ResultadoAuditoria:
        # 1. Portão de enquadramento — só auditamos itens que SÃO ST.
        regime = self.enquadramento_repo.regime(
            item.ncm, item.cest, operacao.uf_emit, operacao.uf_dest, operacao.data
        )
        if regime != Regime.ST:
            return self._nao_auditavel(item, f"regime {regime.value} (fora do motor de ST)")

        # Bifurcação por tpNF. SAÍDA de revenda com ST já retido (CST 60 / CSOSN
        # 500): o ST foi recolhido na cadeia anterior, não se recolhe de novo —
        # auditoria própria (Cenário 1). Os demais casos (entrada, ou saída como
        # substituto CST 10/70/201…) seguem o mesmo cálculo de ST (Cenário 2).
        if operacao.saida and item.cst_csosn in ("60", "500"):
            return self._auditar_revenda_st_retido(item, operacao, regime)

        # 2. Estratégia de base — núcleo v1 cobre só MVA (4) e Valor da Operação (6).
        base_strategy = base_strategy_for(item.mod_bc_st)
        if base_strategy is None:
            return self._nao_auditavel(item, f"modBCST={item.mod_bc_st} fora do núcleo v1")

        # 3. Alíquotas.
        alq_inter = self.aliquotas.alq_inter(
            operacao.uf_emit, operacao.uf_dest, item.orig, operacao.data
        )
        alq_intra_modal = self.aliquotas.alq_intra_modal(operacao.uf_dest, operacao.data)
        alq_intra_efetiva = self.aliquotas.alq_intra_efetiva(operacao.uf_dest, operacao.data)
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

        # 9. Memória (independe das comparações — vale para os dois fluxos abaixo).
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
        )

        # 10. RESPONSABILIDADE na interestadual (matriz de protocolo). Sem acordo
        #     vigente origem→destino, o remetente NÃO é o substituto: a ST vira
        #     antecipação do destinatário (nosso cliente recolhe via guia local).
        if operacao.interestadual and not self.protocolo_repo.tem_protocolo(
            operacao.uf_emit, operacao.uf_dest, operacao.data
        ):
            return self._resultado_antecipacao(item, icms_st_calc, fcp_st_calc, memoria, erros)

        # 11. Com protocolo (ou operação interna): a ST é do REMETENTE — auditamos
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

    @staticmethod
    def _nao_auditavel(item: ItemFiscal, motivo: ErroST | str) -> ResultadoAuditoria:
        """NAO_AUDITAVEL com motivo. Se vier um ErroST, expõe o código no erro
        e a mensagem na observação (feedback claro, nunca silencioso)."""
        if isinstance(motivo, ErroST):
            return ResultadoAuditoria(
                numero_item=item.numero_item,
                status=StatusAuditoria.NAO_AUDITAVEL,
                erros=(motivo,),
                observacao=motivo.mensagem,
            )
        return ResultadoAuditoria(
            numero_item=item.numero_item,
            status=StatusAuditoria.NAO_AUDITAVEL,
            observacao=motivo,
        )
