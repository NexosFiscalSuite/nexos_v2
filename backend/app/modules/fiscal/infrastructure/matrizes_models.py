"""Matrizes fiscais GLOBAIS (sem tenant_id / sem RLS) — fontes dos ports do ST.

A lei é universal: MVA, enquadramento, protocolos e FCP são iguais para todo
escritório, então vivem em tabelas globais (não tenant-scoped). Cada linha
carrega vigência temporal (ADR-0002): a busca filtra pela data de emissão.

NCM é guardado limpo e pode ter 8, 6 ou 4 dígitos (ou 'GERAL' no FCP) para
suportar o fallback por hierarquia na busca.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import ClassVar

from sqlalchemy import DateTime, Index, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.fiscal.infrastructure.vigencia import VigenciaTemporal
from app.shared.domain.uf import CURINGA_UF

_PCT = Numeric(5, 2)


class CriadoEm:
    """Carimbo de quando a linha foi CADASTRADA no sistema (difere da vigência,
    que é quando a regra vale no mundo real — ADR-0002)."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UltimaVerificacao:
    """Quando um humano confirmou a linha pela última vez (cadastro, edição ou
    aprovação de proposta) — o 'frescor' que o aviso de legislação e o radar
    de saúde das matrizes leem. Difere do created_at: reconferir uma regra
    antiga renova este carimbo sem criar vigência nova."""

    ultima_verificacao_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MatrizMva(Base, VigenciaTemporal, CriadoEm, UltimaVerificacao):
    """MVA Original por NCM+CEST+UF origem→destino (alimenta o MvaRepository).

    A MVA NÃO depende só do destino: o mesmo produto entrando em MG tem MVA
    diferente conforme o acordo do estado remetente, e a MVA interna (origem ==
    destino) costuma diferir da interestadual. Sem `uf_origem` o motor aplicava
    uma MVA de outro par e o valor saía errado — por isso a coluna é parte da
    CHAVE_VIGENCIA.

    `uf_origem = "*"` (CURINGA_UF) é a regra que vale para qualquer origem. A
    busca prefere a origem EXATA e só cai no curinga se não houver linha
    específica — assim uma regra geral não sequestra o par curado.
    """

    __tablename__ = "matriz_mva"
    __table_args__ = (
        UniqueConstraint(
            "ncm", "cest", "uf_origem", "uf_destino", "data_inicio_vigencia",
            name="uq_mva_vigencia",
        ),
        Index("ix_mva_busca", "uf_destino", "uf_origem", "ncm", "cest"),
    )
    # Chave de identidade da regra: períodos de vigência não podem se sobrepor.
    CHAVE_VIGENCIA: ClassVar[tuple[str, ...]] = ("ncm", "cest", "uf_origem", "uf_destino")

    id: Mapped[int] = mapped_column(primary_key=True)
    ncm: Mapped[str] = mapped_column(String(8))      # 8/6/4 dígitos (fallback)
    cest: Mapped[str] = mapped_column(String(7))
    uf_origem: Mapped[str] = mapped_column(String(2), default=CURINGA_UF,
                                           server_default=CURINGA_UF)
    uf_destino: Mapped[str] = mapped_column(String(2))
    mva_original: Mapped[Decimal] = mapped_column(_PCT)
    base_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)


class MatrizEnquadramentoSt(Base, VigenciaTemporal, CriadoEm, UltimaVerificacao):
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


class MatrizProtocoloSt(Base, VigenciaTemporal, CriadoEm, UltimaVerificacao):
    """Protocolos/Convênios que ativam a ST interestadual (par UF origem→destino)."""

    __tablename__ = "matriz_protocolo_st"
    __table_args__ = (Index("ix_protocolo_busca", "uf_origem", "uf_destino", "ncm"),)
    # Mesmo acordo NO MESMO ESCOPO de NCM não pode ter vigências sobrepostas;
    # acordos distintos (ou escopos de NCM distintos do mesmo acordo) podem
    # coexistir no par — é como o Anexo VII de MG publica: um acordo cobre
    # vários NCM, uma linha por escopo.
    CHAVE_VIGENCIA: ClassVar[tuple[str, ...]] = ("uf_origem", "uf_destino", "numero_acordo", "ncm")

    id: Mapped[int] = mapped_column(primary_key=True)
    uf_origem: Mapped[str] = mapped_column(String(2))
    uf_destino: Mapped[str] = mapped_column(String(2))
    ncm: Mapped[str | None] = mapped_column(String(8), nullable=True)  # opcional: escopo por par UF
    tipo_acordo: Mapped[str | None] = mapped_column(String(3), nullable=True)  # PRT | CVN
    numero_acordo: Mapped[str] = mapped_column(String(80))   # "Acordo" livre: ex. "Protocolo ICMS 41/2008"
    base_legal: Mapped[str | None] = mapped_column(String(120), nullable=True)  # decreto/norma que ratifica
    situacao: Mapped[str] = mapped_column(String(10), default="ATIVO")


class MatrizAliquota(Base, VigenciaTemporal, CriadoEm, UltimaVerificacao):
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


class MatrizFcp(Base, VigenciaTemporal, CriadoEm, UltimaVerificacao):
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
