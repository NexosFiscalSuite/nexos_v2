"""Schemas do relatório de divergências de ICMS-ST."""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel


class DivergenciaStItem(BaseModel):
    chave_acesso: str
    numero_item: int
    numero_nota: str | None = None
    fornecedor: str | None = None
    cnpj_emit: str | None = None
    uf_origem: str | None = None
    uf_destino: str | None = None
    data_emissao: str | None = None
    cst_csosn: str | None = None
    mod_bc_st: int | None = None
    # MVA: declarada × calculada
    pmva_xml: Decimal
    pmva_calculada: Decimal
    # Base do ST
    vbc_st_xml: Decimal
    vbc_st_calculado: Decimal
    # ICMS-ST: declarado × calculado × rombo
    vicms_st_xml: Decimal
    vicms_st_calculado: Decimal
    divergencia: Decimal
    # FCP-ST
    vfcp_st_xml: Decimal
    vfcp_st_calculado: Decimal
    # Diagnóstico + memória de cálculo aberta (modal de explicação no front)
    codigo_erro: str | None = None
    memoria: dict | None = None


class DivergenciasStResponse(BaseModel):
    total: int
    page: int
    page_size: int
    itens: list[DivergenciaStItem]
