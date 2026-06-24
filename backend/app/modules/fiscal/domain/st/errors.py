"""Catálogo técnico de erros do motor de auditoria de ST (Seção 8 do CALC_ICMS_ST).

Cada erro carrega o código estável (contrato com o REL_Divergencia_ST), a
mensagem e a ação sugerida que alimenta a coluna de automação do relatório.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


@dataclass(frozen=True, slots=True)
class _Erro:
    codigo: str
    mensagem: str
    acao_sugerida: str


class ErroST(_Erro, Enum):
    """Erros auditáveis no núcleo v1. CST 60/500 (106/108) entram no v2."""

    MVA_AJUSTADA_INDEVIDA = (
        "ERRO_101_MVA_AJUSTADA_INDEVIDA",
        "Ajuste de MVA aplicado em operação interna, com emitente do Simples, "
        "ou MVA informada em modBCST=6 (valor da operação).",
        "Solicitar NF-e complementar/corrigida ao fornecedor (retenção a maior = custo indevido).",
    )
    BC_ST_DIVERGENTE = (
        "ERRO_102_BC_ST_DIVERGENTE",
        "vBCST diverge do cálculo matemático baseado no modBCST.",
        "Verificar rateio de frete/IPI e regra de pauta antes de contestar.",
    )
    DEDUCAO_ST_INCORRETA = (
        "ERRO_103_DEDUCAO_ST_INCORRETA",
        "Abatimento do ICMS próprio incorreto (dedução teórica do Simples ou "
        "base própria com redução).",
        "Checar CRT do emitente e CST da operação própria.",
    )
    VALOR_ST_DIVERGENTE = (
        "ERRO_104_VALOR_ST_DIVERGENTE",
        "vICMSST final difere do cálculo esperado fora da margem de centavos.",
        "Recolher complemento (se a menor) ou pleitear ressarcimento (se a maior).",
    )
    FCP_ST_DIVERGENTE = (
        "ERRO_105_FCP_ST_OMITIDO",
        "Erro matemático ou omissão das tags de FCP ST para NCM sujeito ao fundo.",
        "Conferir vigência na MATRIZ_FCP_Por_UF antes de qualquer cobrança.",
    )
    ICMS_PROPRIO_ZERADO_COM_ST = (
        "ERRO_107_ICMS_PROPRIO_ZERADO_COM_ST",
        "CST 10/70 (própria tributada) com vICMS ou vBC zerados — erro do "
        "emissor que contamina a dedução do ST.",
        "Corrigir a operação própria na origem; dedução usa o ICMS próprio calculado.",
    )
    MODBCST_INCOMPATIVEL = (
        "ERRO_109_MODBCST_INCOMPATIVEL",
        "O XML usou base sem MVA (ex.: modBCST=6, valor da operação), mas o "
        "produto tem MVA cadastrada na matriz — base do ST subdimensionada.",
        "Exigir NF-e com modBCST=4 (MVA) ou recolher o complemento do ST.",
    )
    MVA_NAO_ENCONTRADA = (
        "ERRO_MVA_NAO_ENCONTRADA",
        "Base por MVA (modBCST=4) mas não há MVA cadastrada na matriz para "
        "NCM/CEST/UF na data — auditoria não confiável, não calculada.",
        "Cadastrar a MVA (com vigência) na matriz e reauditar.",
    )
