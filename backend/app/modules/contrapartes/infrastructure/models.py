"""Contraparte = cliente OU fornecedor de uma empresa (unificado por `tipo`).

Substitui as duas tabelas idênticas do V1 (clientes/fornecedores). Tenant-scoped.
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

TIPO_CLIENTE = "cliente"
TIPO_FORNECEDOR = "fornecedor"


class Contraparte(Base):
    __tablename__ = "contrapartes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "empresa_id", "tipo", "cnpj", name="uq_contraparte"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    empresa_id: Mapped[UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), index=True)
    tipo: Mapped[str] = mapped_column(String(11))  # cliente | fornecedor
    cnpj: Mapped[str] = mapped_column(String(14), index=True)

    razao_social: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nome_fantasia: Mapped[str | None] = mapped_column(String(200), nullable=True)
    situacao: Mapped[str | None] = mapped_column(String(40), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    atividade: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cnae: Mapped[str | None] = mapped_column(String(20), nullable=True)
    porte: Mapped[str | None] = mapped_column(String(40), nullable=True)
    regime: Mapped[str | None] = mapped_column(String(40), nullable=True)
    inscricao_estadual: Mapped[str | None] = mapped_column(String(30), nullable=True)

    logradouro: Mapped[str | None] = mapped_column(String(200), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(120), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    pais: Mapped[str | None] = mapped_column(String(60), nullable=True)

    origem: Mapped[str] = mapped_column(String(20), default="manual")  # manual|xml|opencnpj
    pendente_revisao: Mapped[bool] = mapped_column(Boolean, default=False)
    last_lookup_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
