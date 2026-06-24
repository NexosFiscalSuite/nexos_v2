"""Schemas de grupos."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class GrupoBody(BaseModel):
    nome: str = Field(..., min_length=1, max_length=120)
    descricao: str | None = None
    empresa_ids: list[UUID] = []
    user_ids: list[UUID] = []
    supervisor_id: UUID | None = None


class GrupoListItem(BaseModel):
    id: UUID
    nome: str
    descricao: str | None = None
    qtd_membros: int
    qtd_empresas: int
    supervisor_id: UUID | None = None
    supervisor_nome: str | None = None
    created_at: datetime | None = None


class GrupoDetail(BaseModel):
    id: UUID
    nome: str
    descricao: str | None = None
    empresa_ids: list[UUID] = []
    user_ids: list[UUID] = []
    supervisor_id: UUID | None = None
    created_at: datetime | None = None
