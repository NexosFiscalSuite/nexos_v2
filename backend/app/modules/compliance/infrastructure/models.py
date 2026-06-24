"""Ciência de quebra de sequência (faixas de numeração canceladas/inutilizadas)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class QuebraCiencia(Base):
    __tablename__ = "quebra_ciencia"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "empresa_id", "modelo", "serie", "num_inicio", "num_fim",
            name="uq_quebra_faixa",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    modelo: Mapped[str] = mapped_column(String(10))
    serie: Mapped[str] = mapped_column(String(10))
    num_inicio: Mapped[int] = mapped_column(Integer)
    num_fim: Mapped[int] = mapped_column(Integer)
    classificacao: Mapped[str] = mapped_column(String(30))  # cancelada|inutilizada|outra
    justificativa: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ciente_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    registrado_por: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
