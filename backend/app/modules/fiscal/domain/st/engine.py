"""Motor de auditoria de ICMS ST — orquestra o pipeline do CALC_ICMS_ST.

Função central pura: recebe os fatos do item + os repositórios (ports) e
devolve um ResultadoAuditoria. Não levanta exceção por nota suja — input
podre vira diagnóstico, nunca crash do lote.
"""
from __future__ import annotations

from dataclasses import dataclass
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
from .ports import EnquadramentoRepository, FcpRepository, MvaRepository
from .strategies import aplicar_reducao_base, base_strategy_for, calcular_deducao

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
    aliquotas: AliquotaResolver = AliquotaResolver()

    def auditar_item(self, item: ItemFiscal, operacao: Operacao) -> ResultadoAuditoria:
        # 1. Portão de enquadramento — só auditamos itens que SÃO ST.
        regime = self.enquadramento_repo.regime(
            item.ncm, item.cest, operacao.uf_emit, operacao.uf_dest, operacao.data
        )
        if regime != Regime.ST:
            return self._nao_auditavel(item, f"regime {regime.value} (fora do motor de ST)")

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

        # 4. MVA (só quando a base é por MVA).
        if base_strategy.espera_mva:
            mva_info = self.mva_repo.buscar(
                item.ncm, item.cest, operacao.uf_dest, operacao.data
            )
            if mva_info is None:
                return self._nao_auditavel(item, "MVA não cadastrada para NCM/CEST/UF")
            mva = calcular_mva(
                mva_original=mva_info.mva_original,
                alq_inter=alq_inter,
                alq_intra=alq_intra_efetiva,   # R-07: carga efetiva no denominador
                crt=operacao.crt,
                interestadual=operacao.interestadual,
            )
            mva_original = mva_info.mva_original
            mva_aplicada = mva.mva_aplicada
            # ERRO_101: não devíamos ajustar, mas o XML aplicou MVA maior que a original.
            if not mva.ajustada and item.p_mva_st > mva_original + TOLERANCIA_MVA_PCT:
                erros.append(ErroST.MVA_AJUSTADA_INDEVIDA)
        else:
            mva_original = mva_aplicada = ZERO
            mva = None
            # ERRO_101: modBCST=6 não admite MVA.
            if item.p_mva_st > ZERO:
                erros.append(ErroST.MVA_AJUSTADA_INDEVIDA)

        # 5. Base do ST (integral → com redução, Método A).
        base_integral = base_strategy.base_integral(item, mva_aplicada)
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

        # 9. Comparações com a régua de centavos.
        div_bc = centavos(item.v_bc_st) - centavos(base_st_calc)
        if abs(div_bc) > TOLERANCIA_ITEM:
            erros.append(ErroST.BC_ST_DIVERGENTE)

        div_icms_st = centavos(item.v_icms_st) - centavos(icms_st_calc)
        if abs(div_icms_st) > TOLERANCIA_ITEM:
            erros.append(ErroST.VALOR_ST_DIVERGENTE)

        div_fcp = centavos(item.v_fcp_st) - centavos(fcp_st_calc)
        if abs(div_fcp) > TOLERANCIA_ITEM:
            erros.append(ErroST.FCP_ST_DIVERGENTE)

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
        status = StatusAuditoria.DIVERGENTE if erros else StatusAuditoria.OK
        return ResultadoAuditoria(
            numero_item=item.numero_item,
            status=status,
            erros=tuple(erros),
            divergencia_icms_st=div_icms_st,
            divergencia_fcp_st=div_fcp,
            memoria=memoria,
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

    @staticmethod
    def _nao_auditavel(item: ItemFiscal, motivo: str) -> ResultadoAuditoria:
        return ResultadoAuditoria(
            numero_item=item.numero_item,
            status=StatusAuditoria.NAO_AUDITAVEL,
            observacao=motivo,
        )
