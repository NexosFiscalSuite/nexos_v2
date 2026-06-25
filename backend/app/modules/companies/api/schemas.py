"""Schemas de empresas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class _EmpresaCampos(BaseModel):
    nome_fantasia: str | None = None
    regime: str | None = Field(default=None, examples=["Lucro Real", "Simples Nacional"])
    uf: str | None = Field(default=None, max_length=2)
    municipio: str | None = None
    inscricao_estadual: str | None = None
    cnae: str | None = None
    cep: str | None = Field(default=None, max_length=9)
    logradouro: str | None = None
    numero: str | None = None
    bairro: str | None = None


class EmpresaCreate(_EmpresaCampos):
    cnpj: str = Field(..., examples=["11.444.777/0001-61"])
    razao_social: str = Field(..., min_length=2, max_length=200)


class EmpresaUpdate(_EmpresaCampos):
    """Edição: todos os campos opcionais (CNPJ é imutável)."""
    razao_social: str | None = Field(default=None, min_length=2, max_length=200)


class EmpresaResponse(_EmpresaCampos):
    id: UUID
    cnpj: str
    razao_social: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
