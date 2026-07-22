"""Estruturas de entrada (fatos da nota) e saída (resultado da auditoria).

Princípio do motor: o XML é FONTE DE FATO, não FONTE DE VERDADE. Os campos
"físicos" (vProd, frete, NCM, orig, CRT...) alimentam o recálculo; os campos
fiscais declarados (vBCST, vICMSST, pMVAST...) servem apenas para COMPARAR.
Assim uma nota com imposto errado é auditada, nunca propagada.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .enums import Crt
from .errors import ErroST
from .money import ZERO


@dataclass(frozen=True, slots=True)
class Operacao:
    """Contexto da nota, comum a todos os itens (nível <ide>/<emit>/<dest>)."""

    uf_emit: str
    uf_dest: str
    crt: Crt
    data: date
    # tpNF: 0=entrada (compra) / 1=saída (venda). Bifurca a auditoria — na saída
    # o cliente é o vendedor (substituto ou revendedor com ST já retido).
    saida: bool = False
    # indIEDest: 1=contribuinte, 2=isento de IE, 9=não contribuinte. Usado a
    # montante (enquadramento); mantido aqui para roteamento futuro.
    ind_ie_dest: str | None = None

    @property
    def interestadual(self) -> bool:
        return self.uf_emit.upper() != self.uf_dest.upper()


@dataclass(frozen=True, slots=True)
class ItemFiscal:
    """Fatos de um item (<det nItem>). Valores de despesa já rateados por item.

    O rateio de frete/seguro/outras/desconto que vêm só no totalizador é
    responsabilidade de quem monta este objeto (helper `ratear` à parte) —
    o motor assume os valores já no nível do item.
    """

    numero_item: int
    ncm: str
    cest: str
    cfop: str
    orig: str                      # 0-8 (tag <orig>)
    cst: str | None = None         # regime normal
    csosn: str | None = None       # simples nacional
    mod_bc_st: int | None = None

    # --- valores físicos da operação (base do recálculo) ---
    v_prod: Decimal = ZERO
    q_com: Decimal = ZERO
    v_frete: Decimal = ZERO
    v_seg: Decimal = ZERO
    v_outro: Decimal = ZERO
    v_desc: Decimal = ZERO
    v_ipi: Decimal = ZERO

    # --- operação própria declarada (dedução real + trava ERRO_107) ---
    v_bc: Decimal = ZERO
    v_icms: Decimal = ZERO
    p_icms: Decimal = ZERO
    p_red_bc: Decimal = ZERO
    v_fcp: Decimal = ZERO          # FCP da operação própria (deduz do FCP-ST)

    # --- ST declarado no XML (apenas para comparação) ---
    p_mva_st: Decimal = ZERO
    p_red_bc_st: Decimal = ZERO
    p_icms_st: Decimal = ZERO
    v_bc_st: Decimal = ZERO
    v_icms_st: Decimal = ZERO
    p_fcp_st: Decimal = ZERO
    v_bc_fcp_st: Decimal = ZERO
    v_fcp_st: Decimal = ZERO

    # --- ST retido anteriormente (CST 60 / CSOSN 500) — insumo do ressarcimento ---
    v_bc_st_ret: Decimal = ZERO
    p_st_ret: Decimal = ZERO
    v_icms_st_ret: Decimal = ZERO
    v_icms_substituto: Decimal = ZERO
    v_fcp_st_ret: Decimal = ZERO

    @property
    def cst_csosn(self) -> str:
        return self.cst or self.csosn or ""


@dataclass(frozen=True, slots=True)
class MemoriaCalculo:
    """Memória de cálculo aberta — sustenta a defesa fiscal (REL_Divergencia_ST)."""

    regime: str
    mva_original: Decimal
    mva_aplicada: Decimal
    mva_foi_ajustada: bool
    motivo_nao_ajuste: str | None
    alq_inter: Decimal
    alq_intra: Decimal
    base_st_calculada: Decimal
    icms_st_debito: Decimal
    deducao_aplicada: Decimal
    deducao_tipo: str               # "real" | "teorica" | "zero" | "contaminada"
    icms_st_calculado: Decimal
    fcp_st_debito: Decimal          # vBCFCPST × pFCPST (antes da dedução)
    fcp_st_deducao: Decimal         # FCP próprio abatido (não-cumulatividade)
    fcp_st_calculado: Decimal       # FCP-ST líquido devido

    # --- rastreabilidade (defensibilidade fiscal) ---
    engine_version: str | None = None       # versão do motor que produziu o cálculo
    mva_matriz_id: int | None = None        # linha da matriz_mva usada (None = seed/teste)
    aliquota_matriz_id: int | None = None   # linha da matriz_aliquota usada
    tem_protocolo: bool | None = None       # None = operação interna (não se aplica)
    protocolo_fonte: str | None = None      # "matriz" (consultada) | "assumido" (default)


class StatusAuditoria(str):
    OK = "OK"
    DIVERGENTE = "DIVERGENTE"
    NAO_AUDITAVEL = "NAO_AUDITAVEL"  # fora do escopo v1 (ex.: modBCST pauta)


@dataclass(frozen=True, slots=True)
class ResultadoAuditoria:
    """Saída por item: status, erros, divergências e a memória de cálculo."""

    numero_item: int
    status: str
    erros: tuple[ErroST, ...] = ()
    divergencia_icms_st: Decimal = ZERO
    divergencia_fcp_st: Decimal = ZERO
    memoria: MemoriaCalculo | None = None
    observacao: str | None = None

    @property
    def divergente(self) -> bool:
        return self.status == StatusAuditoria.DIVERGENTE

    @property
    def codigos_erro(self) -> list[str]:
        return [e.codigo for e in self.erros]
