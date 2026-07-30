"""Grupos = controle de acesso. Grupo tem empresas + membros (1 supervisor).

Supervisor e `user` só enxergam as empresas dos grupos a que pertencem (o
supervisor entra como membro com papel próprio); apenas o admin vê todas.
Todas as tabelas são tenant-scoped (RLS).
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

PAPEL_MEMBRO = "membro"
PAPEL_SUPERVISOR = "supervisor"


class Grupo(Base):
    __tablename__ = "grupos"
    __table_args__ = (UniqueConstraint("tenant_id", "nome", name="uq_grupo_tenant_nome"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(String(400), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GrupoMembro(Base):
    __tablename__ = "grupo_membros"

    grupo_id: Mapped[UUID] = mapped_column(ForeignKey("grupos.id", ondelete="CASCADE"), primary_key=True)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
    papel: Mapped[str] = mapped_column(String(20), default=PAPEL_MEMBRO)


class EmpresaGrupo(Base):
    __tablename__ = "empresa_grupo"

    grupo_id: Mapped[UUID] = mapped_column(ForeignKey("grupos.id", ondelete="CASCADE"), primary_key=True)
    empresa_id: Mapped[UUID] = mapped_column(ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True)
    tenant_id: Mapped[UUID] = mapped_column(ForeignKey("tenants.id", ondelete="CASCADE"), index=True)
