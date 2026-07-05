"""Matrizes fiscais GLOBAIS (sem tenant_id / sem RLS) — fontes dos ports do ST.

A lei é universal: MVA, enquadramento, protocolos e FCP são iguais para todo
escritório, então vivem em tabelas globais (não tenant-scoped). Cada linha
carrega vigência temporal (ADR-0002): a busca filtra pela data de emissão.

NCM é guardado limpo e pode ter 8, 6 ou 4 dígitos (ou 'GERAL' no FCP) para
suportar o fallback por hierarquia na busca.
"""
from __future__ import annotations

from decimal import Decimal
from typing import ClassVar

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
    # Chave de identidade da regra: períodos de vigência não podem se sobrepor.
    CHAVE_VIGENCIA: ClassVar[tuple[str, ...]] = ("ncm", "cest", "uf_destino")

    id: Mapped[int] = mapped_column(primary_key=True)
    ncm: Mapped[str] = mapped_column(String(8))      # 8/6/4 dígitos (fallback)
    cest: Mapped[str] = mapped_column(String(7))
    uf_destino: Mapped[str] = mapped_column(String(2))
    mva_original: Mapped[Decimal] = mapped_column(_PCT)
    base_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MatrizEnquadramentoSt(Base, VigenciaTemporal):
    """Regime do item (ST | TN | ST_ENTRADA) por NCM+CEST+UF destino."""

    __tablename__ = "matriz_enquadramento_st"
    __table_args__ = (
        UniqueConstraint(
            "uf_destino", "ncm", "cest", "data_inicio_vigencia", name="uq_enq_vigencia"
        ),
        Index("ix_enq_busca", "uf_destino", "ncm", "cest"),
    )
    CHAVE_VIGENCIA: ClassVar[tuple[str, ...]] = ("uf_destino", "ncm", "cest")

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_destino: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str] = mapped_column(String(8))
    cest: Mapped[str] = mapped_column(String(7))
    regime: Mapped[str] = mapped_column(String(12))   # ST | TN | ST_ENTRADA
    segmento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    base_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MatrizProtocoloSt(Base, VigenciaTemporal):
    """Protocolos/Convênios que ativam a ST interestadual (par UF origem→destino)."""

    __tablename__ = "matriz_protocolo_st"
    __table_args__ = (Index("ix_protocolo_busca", "uf_origem", "uf_destino", "ncm"),)
    # Mesmo acordo não pode ter vigências sobrepostas; acordos distintos no
    # mesmo par UF→UF podem coexistir.
    CHAVE_VIGENCIA: ClassVar[tuple[str, ...]] = ("uf_origem", "uf_destino", "numero_acordo")

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_origem: Mapped[str] = mapped_column(String(2))
    uf_destino: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str | None] = mapped_column(String(8), nullable=True)  # opcional: escopo por par UF
    tipo_acordo: Mapped[str | None] = mapped_column(String(3), nullable=True)  # PRT | CVN
    numero_acordo: Mapped[str] = mapped_column(String(80))   # "Acordo" livre: ex. "Protocolo ICMS 41/2008"
    base_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)  # decreto/norma que ratifica
    situacao: Mapped[str] = mapped_column(String(10), default="ATIVO")


class MatrizAliquota(Base, VigenciaTemporal):
    """Alíquota modal do ICMS por UF de destino (alimenta o AliquotaRepository).

    `aliq_modal` é o débito do ST (sem FCP); `aliq_fcp_integrado` só compõe a
    carga efetiva no denominador do ajuste de MVA (R-07). Antes vivia fixa em
    código (aliquotas.py) e ignorava a data — dupla vigência como AL 19%→20,5%
    em 01/04/2026 (Lei 9.776/2025) exige a matriz temporal.
    """

    __tablename__ = "matriz_aliquota"
    __table_args__ = (
        UniqueConstraint("uf_destino", "data_inicio_vigencia", name="uq_aliquota_vigencia"),
        Index("ix_aliquota_busca", "uf_destino"),
    )
    CHAVE_VIGENCIA: ClassVar[tuple[str, ...]] = ("uf_destino",)

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_destino: Mapped[str] = mapped_column(String(2))
    aliq_modal: Mapped[Decimal] = mapped_column(_PCT)
    aliq_fcp_integrado: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    base_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MatrizFcp(Base, VigenciaTemporal):
    """Alíquota de FCP por UF+NCM (alimenta o FcpRepository). NCM pode ser 'GERAL'."""

    __tablename__ = "matriz_fcp"
    __table_args__ = (
        UniqueConstraint("uf_destino", "ncm", "data_inicio_vigencia", name="uq_fcp_vigencia"),
        Index("ix_fcp_busca", "uf_destino", "ncm"),
    )
    CHAVE_VIGENCIA: ClassVar[tuple[str, ...]] = ("uf_destino", "ncm")

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_destino: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str] = mapped_column(String(8))      # 8/4 dígitos ou 'GERAL'
    aliq_fcp_interno: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    aliq_fcp_st: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    base_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)
