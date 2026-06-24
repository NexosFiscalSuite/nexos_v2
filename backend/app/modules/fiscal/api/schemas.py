"""Schemas fiscais."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class UploadResponse(BaseModel):
    job_id: UUID
    status: str
    arquivos: int
    detail: str = "Importação enfileirada. Acompanhe em GET /jobs/{job_id}."


class NotaItemResponse(BaseModel):
    numero_item: int
    codigo: str | None = None
    descricao: str | None = None
    ncm: str | None = None
    cfop: str | None = None
    tipo_sped: str | None = None
    unidade: str | None = None
    quantidade: float = 0
    valor_unitario: float = 0
    valor_total: float = 0
    valor_produto: float = 0
    valor_desconto: float = 0
    valor_frete: float = 0
    valor_seguro: float = 0
    base_calculo: float = 0
    valor_icms: float = 0
    valor_icms_st: float = 0

    model_config = {"from_attributes": True}


class NotaResponse(BaseModel):
    id: UUID
    empresa_id: UUID
    chave_acesso: str
    tipo: str
    fluxo: str
    modelo: str
    serie: str | None = None
    numero: str | None = None
    cnpj_emit: str | None = None
    nome_emit: str | None = None
    uf_emit: str | None = None
    cnpj_dest: str | None = None
    nome_dest: str | None = None
    uf_dest: str | None = None
    valor_total: float = 0
    data_emissao: str | None = None
    data_entrada: str | None = None
    competencia: str | None = None
    iss_retido: int | None = None
    tem_correcao: bool = False
    tipo_nota: str | None = None
    status: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class NotaDetailResponse(NotaResponse):
    itens: list[NotaItemResponse] = []


class NotaListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    notas: list[NotaResponse]


class BulkIds(BaseModel):
    ids: list[UUID]


class BulkCfop(BaseModel):
    ids: list[UUID]
    cfop: str


class BulkTipoNota(BaseModel):
    ids: list[UUID]
    tipo_nota: str


class BulkResult(BaseModel):
    afetadas: int


class NotaUpdate(BaseModel):
    """Campos editáveis do cabeçalho (PATCH; só os enviados são alterados)."""
    data_entrada: str | None = None
    competencia: str | None = None
    iss_retido: int | None = None
    tem_correcao: bool | None = None
    tipo_nota: str | None = None


class ItemUpdate(BaseModel):
    """Edição de item: CFOP e Tipo SPED (cfop_original é preservado no servidor)."""
    cfop: str | None = None
    tipo_sped: str | None = None
