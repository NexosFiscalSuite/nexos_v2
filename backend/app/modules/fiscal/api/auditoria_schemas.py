"""Schemas do relatório de divergências de ICMS-ST."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class DivergenciaStItem(BaseModel):
    chave_acesso: str
    nota_id: str | None = None    # habilita ações por nota na tela (ex.: sem CT-e)
    numero_item: int
    # Identificação do produto (join com nota_itens — a auditoria só guarda o nº)
    descricao: str | None = None
    codigo: str | None = None
    ncm: str | None = None
    cest: str | None = None
    numero_nota: str | None = None
    fornecedor: str | None = None
    cnpj_emit: str | None = None
    uf_origem: str | None = None
    uf_destino: str | None = None
    data_emissao: str | None = None
    fluxo: str | None = None
    cst_csosn: str | None = None
    mod_bc_st: int | None = None
    # MVA: declarada × calculada
    pmva_xml: Decimal
    pmva_calculada: Decimal
    # Base do ST
    vbc_st_xml: Decimal
    vbc_st_calculado: Decimal
    # ICMS-ST: declarado × calculado × diferença
    vicms_st_xml: Decimal
    vicms_st_calculado: Decimal
    diferenca: Decimal
    # FCP-ST
    vfcp_st_xml: Decimal
    vfcp_st_calculado: Decimal
    # Status + diagnóstico + memória de cálculo aberta (modal de explicação)
    status: str
    codigo_erro: str | None = None
    observacao: str | None = None
    memoria: dict | None = None
    ctes_vinculados: list[str] = []
    # Triagem do item (o que o escritório decidiu): sem declarar aqui, o
    # response_model tipado REMOVIA o campo da resposta e a tela ficava cega.
    triagem: dict | None = None


class ResumoSt(BaseModel):
    """Dinheiro em jogo no período (independente da paginação)."""

    a_recolher: float    # divergências negativas (sem ERRO_111): fornecedor reteve a menor
    a_favor: float       # divergências positivas: pago a maior (ressarcimento)
    antecipacao: float   # ERRO_111: guia própria do cliente (não é cobrança de fornecedor)
    divergentes: int
    nao_auditaveis: int
    triagem: dict[str, int] = {}   # contagem dos DIVERGENTES por status de triagem


class FornecedorRanking(BaseModel):
    cnpj: str | None = None
    nome: str | None = None
    itens: int
    valor: float         # |diferença| acumulada cobrável (sem ERRO_111)


class DivergenciasStResponse(BaseModel):
    total: int
    page: int
    page_size: int
    itens: list[DivergenciaStItem]
    resumo: ResumoSt | None = None
    ranking_fornecedores: list[FornecedorRanking] = []
