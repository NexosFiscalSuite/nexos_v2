"""Schemas de contrapartes."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ContraparteBase(BaseModel):
    razao_social: str | None = None
    nome_fantasia: str | None = None
    situacao: str | None = None
    uf: str | None = None
    municipio: str | None = None
    atividade: str | None = None
    cnae: str | None = None
    porte: str | None = None
    regime: str | None = None
    inscricao_estadual: str | None = None
    logradouro: str | None = None
    numero: str | None = None
    complemento: str | None = None
    bairro: str | None = None
    cep: str | None = None
    pais: str | None = None


class ContraparteCreate(ContraparteBase):
    tipo: str = Field(..., examples=["cliente", "fornecedor"])
    cnpj: str
    pendente_revisao: bool = False
    origem: str = "manual"


class ContraparteUpdate(ContraparteBase):
    pendente_revisao: bool | None = None


class ContraparteResponse(ContraparteBase):
    id: UUID
    tipo: str
    cnpj: str
    origem: str
    pendente_revisao: bool
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class CnpjLookupResponse(BaseModel):
    ok: bool
    cnpj: str
    dados: dict
    error: str | None = None
