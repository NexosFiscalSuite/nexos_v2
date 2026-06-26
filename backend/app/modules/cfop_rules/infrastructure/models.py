"""Regra De/Para: CFOP -> Tipo de Item (SPED). GLOBAL (regra do escritório, sem
tenant/RLS — a classificação por CFOP é a mesma para todos os clientes).

Na importação de ENTRADAS, o CFOP do XML (origem) casa com a regra e o sistema
preenche o Tipo de Item e reclassifica o CFOP para o destino (cfop_original é
preservado no item).
"""
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CfopRegra(Base):
    __tablename__ = "cfop_regras"
    __table_args__ = (UniqueConstraint("cfop_origem", name="uq_cfop_origem"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tipo_item: Mapped[str] = mapped_column(String(40))
    cfop_origem: Mapped[str] = mapped_column(String(10), index=True)
    cfop_destino: Mapped[str] = mapped_column(String(10))
    usa_extensao: Mapped[bool] = mapped_column(Boolean, default=False)
    extensao: Mapped[str | None] = mapped_column(String(20), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now())
