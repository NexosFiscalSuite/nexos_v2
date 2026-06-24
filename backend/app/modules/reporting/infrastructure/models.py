"""Modelo de relatório personalizável (config das colunas em JSONB)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class RelatorioModelo(Base):
    __tablename__ = "relatorio_modelos"
    __table_args__ = (
        UniqueConstraint("tenant_id", "empresa_id", "nome", "fluxo", name="uq_modelo_nome_fluxo"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    nome: Mapped[str] = mapped_column(String(120))
    fluxo: Mapped[str] = mapped_column(String(10))
    config_json: Mapped[dict] = mapped_column(JSONB)  # {"colunas": [...]}
    created_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
