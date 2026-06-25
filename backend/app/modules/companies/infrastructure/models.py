"""Empresa = empresa-cliente do escritório (tenant). Tenant-scoped (RLS)."""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Empresa(Base):
    __tablename__ = "empresas"
    __table_args__ = (UniqueConstraint("tenant_id", "cnpj", name="uq_empresa_tenant_cnpj"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    cnpj: Mapped[str] = mapped_column(String(14), index=True)
    razao_social: Mapped[str] = mapped_column(String(200))
    nome_fantasia: Mapped[str | None] = mapped_column(String(200), nullable=True)
    regime: Mapped[str | None] = mapped_column(String(40), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(30), nullable=True)
    cnae: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    logradouro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
