"""Schemas de empresas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class EmpresaCreate(BaseModel):
    cnpj: str = Field(..., examples=["11.444.777/0001-61"])
    razao_social: str = Field(..., min_length=2, max_length=200)
    nome_fantasia: str | None = None
    regime: str | None = Field(default=None, examples=["Simples Nacional", "Lucro Presumido"])
    uf: str | None = Field(default=None, max_length=2)
    municipio: str | None = None
    inscricao_estadual: str | None = None


class EmpresaResponse(BaseModel):
    id: UUID
    cnpj: str
    razao_social: str
    nome_fantasia: str | None = None
    regime: str | None = None
    uf: str | None = None
    municipio: str | None = None
    inscricao_estadual: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
