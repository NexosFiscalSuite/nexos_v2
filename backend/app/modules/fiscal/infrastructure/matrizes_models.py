"""Matrizes fiscais GLOBAIS (sem tenant_id / sem RLS) — fontes dos ports do ST.

A lei é universal: MVA, enquadramento, protocolos e FCP são iguais para todo
escritório, então vivem em tabelas globais (não tenant-scoped). Cada linha
carrega vigência temporal (ADR-0002): a busca filtra pela data de emissão.

NCM é guardado limpo e pode ter 8, 6 ou 4 dígitos (ou 'GERAL' no FCP) para
suportar o fallback por hierarquia na busca.
"""
from __future__ import annotations

from decimal import Decimal

from sqlalchemy import Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.fiscal.infrastructure.vigencia import VigenciaTemporal

_PCT = Numeric(5, 2)


class MatrizMva(Base, VigenciaTemporal):
    """MVA Original por NCM+CEST+UF destino (alimenta o MvaRepository)."""

    __tablename__ = "matriz_mva"
    __table_args__ = (
        UniqueConstraint(
            "ncm", "cest", "uf_destino", "data_inicio_vigencia", name="uq_mva_vigencia"
        ),
        Index("ix_mva_busca", "uf_destino", "ncm", "cest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ncm: Mapped[str] = mapped_column(String(8))      # 8/6/4 dígitos (fallback)
    cest: Mapped[str] = mapped_column(String(7))
    uf_destino: Mapped[str] = mapped_column(String(2))
    mva_original: Mapped[Decimal] = mapped_column(_PCT)
    ato_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MatrizEnquadramentoSt(Base, VigenciaTemporal):
    """Regime do item (ST | TN | ST_ENTRADA) por NCM+CEST+UF destino."""

    __tablename__ = "matriz_enquadramento_st"
    __table_args__ = (
        UniqueConstraint(
            "uf_destino", "ncm", "cest", "data_inicio_vigencia", name="uq_enq_vigencia"
        ),
        Index("ix_enq_busca", "uf_destino", "ncm", "cest"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_destino: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str] = mapped_column(String(8))
    cest: Mapped[str] = mapped_column(String(7))
    regime: Mapped[str] = mapped_column(String(12))   # ST | TN | ST_ENTRADA
    segmento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    ato_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MatrizProtocoloSt(Base, VigenciaTemporal):
    """Protocolos/Convênios que ativam a ST interestadual (par UF origem→destino)."""

    __tablename__ = "matriz_protocolo_st"
    __table_args__ = (Index("ix_protocolo_busca", "uf_origem", "uf_destino", "ncm"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_origem: Mapped[str] = mapped_column(String(2))
    uf_destino: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str] = mapped_column(String(8))
    tipo_acordo: Mapped[str] = mapped_column(String(3))      # PRT | CVN
    numero_acordo: Mapped[str] = mapped_column(String(20))
    situacao: Mapped[str] = mapped_column(String(10), default="ATIVO")


class MatrizFcp(Base, VigenciaTemporal):
    """Alíquota de FCP por UF+NCM (alimenta o FcpRepository). NCM pode ser 'GERAL'."""

    __tablename__ = "matriz_fcp"
    __table_args__ = (
        UniqueConstraint("uf_destino", "ncm", "data_inicio_vigencia", name="uq_fcp_vigencia"),
        Index("ix_fcp_busca", "uf_destino", "ncm"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_destino: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str] = mapped_column(String(8))      # 8/4 dígitos ou 'GERAL'
    aliq_fcp_interno: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    aliq_fcp_st: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    ato_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)
