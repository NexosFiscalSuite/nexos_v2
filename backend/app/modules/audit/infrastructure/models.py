"""Trilha de auditoria (audit_log). Tenant-scoped (RLS).

Registra ações relevantes: quem (user_id), o quê (acao), sobre o quê
(entidade/entidade_id) e detalhes (JSONB), com carimbo de tempo.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    acao: Mapped[str] = mapped_column(String(60))
    entidade: Mapped[str | None] = mapped_column(String(60), nullable=True)
    entidade_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    detalhe: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
