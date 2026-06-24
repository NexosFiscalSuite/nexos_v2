"""Schemas da trilha de auditoria."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AuditResponse(BaseModel):
    id: UUID
    acao: str
    entidade: str | None = None
    entidade_id: str | None = None
    detalhe: dict | None = None
    user_id: UUID | None = None
    user_nome: str | None = None
    created_at: datetime | None = None
