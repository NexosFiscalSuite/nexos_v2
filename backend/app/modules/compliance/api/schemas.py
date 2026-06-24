"""Schemas de compliance (quebra de sequência)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class QuebraResponse(BaseModel):
    modelo: str
    serie: str
    num_inicio: int
    num_fim: int
    qtd: int


class CienciaCreate(BaseModel):
    modelo: str
    serie: str
    num_inicio: int = Field(..., ge=0)
    num_fim: int = Field(..., ge=0)
    classificacao: str = Field(..., examples=["cancelada", "inutilizada", "outra"])
    justificativa: str | None = None
    ciente_nome: str | None = Field(default=None, description="Nome do responsável/auditor.")


class FaixaItem(BaseModel):
    modelo: str
    serie: str
    num_inicio: int = Field(..., ge=0)
    num_fim: int = Field(..., ge=0)


class CienciaLoteCreate(BaseModel):
    faixas: list[FaixaItem]
    classificacao: str = Field(..., examples=["cancelada", "inutilizada", "outra"])
    justificativa: str | None = None
    auditor_email: str
    auditor_password: str


class CienciaResponse(BaseModel):
    id: UUID
    modelo: str
    serie: str
    num_inicio: int
    num_fim: int
    classificacao: str
    justificativa: str | None = None
    ciente_nome: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
