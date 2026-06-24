"""Modelos fiscais: Nota, NotaItem, NotaEvento. Todos tenant-scoped (RLS)."""
from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

_MONEY = Numeric(15, 2)
_QTY = Numeric(15, 4)
_PCT = Numeric(5, 2)


class Nota(Base):
    __tablename__ = "notas"
    __table_args__ = (
        UniqueConstraint("tenant_id", "empresa_id", "chave_acesso", name="uq_nota_chave"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    chave_acesso: Mapped[str] = mapped_column(String(60), index=True)
    tipo: Mapped[str] = mapped_column(String(10))          # NFe|NFCe|CTe|NFSe
    fluxo: Mapped[str] = mapped_column(String(10))         # entrada|saida|servico|cte
    modelo: Mapped[str] = mapped_column(String(10))        # 55|65|57|NFSe-A|NFSe-N
    serie: Mapped[str | None] = mapped_column(String(10), nullable=True)
    numero: Mapped[str | None] = mapped_column(String(20), nullable=True)

    cnpj_emit: Mapped[str | None] = mapped_column(String(14), nullable=True)
    nome_emit: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uf_emit: Mapped[str | None] = mapped_column(String(2), nullable=True)
    crt_emit: Mapped[str | None] = mapped_column(String(1), nullable=True)  # 1|2|3|4 (regime ST)
    cnpj_dest: Mapped[str | None] = mapped_column(String(14), nullable=True)
    nome_dest: Mapped[str | None] = mapped_column(String(200), nullable=True)
    uf_dest: Mapped[str | None] = mapped_column(String(2), nullable=True)
    transportadora_cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    transportadora_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo_nota: Mapped[str | None] = mapped_column(String(80), nullable=True)  # classificação da entrada

    valor_total: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    data_emissao: Mapped[str | None] = mapped_column(String(10), nullable=True)
    data_entrada: Mapped[str | None] = mapped_column(String(10), nullable=True)
    competencia: Mapped[str | None] = mapped_column(String(7), nullable=True)  # YYYY-MM
    iss_retido: Mapped[int | None] = mapped_column(Integer, nullable=True)     # 1|0|None
    ano: Mapped[str | None] = mapped_column(String(4), nullable=True)
    mes: Mapped[str | None] = mapped_column(String(2), nullable=True)

    storage_key: Mapped[str | None] = mapped_column(String(400), nullable=True)
    status: Mapped[str] = mapped_column(String(12), default="ativa")  # ativa|cancelada
    cancelada_em: Mapped[str | None] = mapped_column(String(40), nullable=True)
    protocolo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    tem_correcao: Mapped[bool] = mapped_column(Boolean, default=False)

    uploaded_by: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotaItem(Base):
    __tablename__ = "nota_itens"
    __table_args__ = (UniqueConstraint("nota_id", "numero_item", name="uq_item_nota"),)

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    nota_id: Mapped[UUID] = mapped_column(
        ForeignKey("notas.id", ondelete="CASCADE"), index=True
    )
    numero_item: Mapped[int] = mapped_column(Integer)
    codigo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ncm: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cfop: Mapped[str | None] = mapped_column(String(6), nullable=True)
    cfop_original: Mapped[str | None] = mapped_column(String(6), nullable=True)
    tipo_sped: Mapped[str | None] = mapped_column(String(40), nullable=True)
    unidade: Mapped[str | None] = mapped_column(String(10), nullable=True)
    quantidade: Mapped[Decimal] = mapped_column(_QTY, default=Decimal("0"))
    valor_unitario: Mapped[Decimal] = mapped_column(_QTY, default=Decimal("0"))
    valor_total: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_produto: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_desconto: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_frete: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_seguro: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_outro: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_ipi: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    base_calculo: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_icms: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    valor_icms_st: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))

    # --- tags de ST / FCP (insumos do motor de auditoria de Substituição Tributária) ---
    cest: Mapped[str | None] = mapped_column(String(7), nullable=True)
    orig: Mapped[str | None] = mapped_column(String(1), nullable=True)
    cst: Mapped[str | None] = mapped_column(String(2), nullable=True)
    csosn: Mapped[str | None] = mapped_column(String(3), nullable=True)
    mod_bc_st: Mapped[int | None] = mapped_column(Integer, nullable=True)
    p_icms: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    p_red_bc: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    p_mva_st: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    p_red_bc_st: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    p_icms_st: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    v_bc_st: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    # FCP (próprio e ST) — trilhas paralelas
    v_fcp: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    p_fcp: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    v_bc_fcp: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    v_fcp_st: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    p_fcp_st: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    v_bc_fcp_st: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))


class NfeCteVinculo(Base):
    """Vínculo N:N entre NF-e e CT-e (ADR-0001), por CHAVE — tolera órfão.

    Uma NF-e pode ter N CT-e e um CT-e pode transportar N NF-e. Chaveado por
    chave de acesso (não por FK de id) para suportar importação fora de ordem
    (o CT-e pode chegar antes da NF-e), espelhando o padrão de NotaEvento.
    """

    __tablename__ = "nfe_cte_vinculo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "empresa_id", "chave_nfe", "chave_cte", name="uq_nfe_cte"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    chave_nfe: Mapped[str] = mapped_column(String(44), index=True)
    chave_cte: Mapped[str] = mapped_column(String(44), index=True)
    vtprest: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    tp_cte: Mapped[str | None] = mapped_column(String(2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditoriaIcmsSt(Base):
    """Resultado da auditoria de ICMS-ST por item (Vault §9). Guarda o declarado
    no XML, o calculado pelo motor, a divergência e a memória de cálculo aberta."""

    __tablename__ = "auditoria_icms_st"
    __table_args__ = (
        UniqueConstraint("tenant_id", "nota_id", "numero_item", name="uq_auditoria_st_item"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    nota_id: Mapped[UUID] = mapped_column(ForeignKey("notas.id", ondelete="CASCADE"), index=True)
    chave_acesso: Mapped[str] = mapped_column(String(44), index=True)
    numero_item: Mapped[int] = mapped_column(Integer)
    cst_csosn: Mapped[str | None] = mapped_column(String(3), nullable=True)
    mod_bc_st: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # XML declarado × calculado pelo motor
    pmva_xml: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    pmva_calculada: Mapped[Decimal] = mapped_column(_PCT, default=Decimal("0"))
    vbc_st_xml: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    vbc_st_calculado: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    vicms_st_xml: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    vicms_st_calculado: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    vicms_st_divergencia: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    vfcp_st_xml: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))
    vfcp_st_calculado: Mapped[Decimal] = mapped_column(_MONEY, default=Decimal("0"))

    status: Mapped[str] = mapped_column(String(14))            # OK|DIVERGENTE|NAO_AUDITAVEL
    codigo_erro: Mapped[str | None] = mapped_column(String(120), nullable=True)
    observacao: Mapped[str | None] = mapped_column(String(255), nullable=True)  # motivo p/ NAO_AUDITAVEL
    memoria: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # cálculo aberto
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class NotaEvento(Base):
    """Eventos (cancelamento/CC-e). Pode existir órfão (nota ainda não importada)."""

    __tablename__ = "nota_eventos"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    empresa_id: Mapped[UUID] = mapped_column(
        ForeignKey("empresas.id", ondelete="CASCADE"), index=True
    )
    nota_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("notas.id", ondelete="CASCADE"), nullable=True
    )
    chave_acesso: Mapped[str] = mapped_column(String(60), index=True)
    tipo_evento: Mapped[str] = mapped_column(String(30))  # cancelamento
    protocolo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    data_evento: Mapped[str | None] = mapped_column(String(40), nullable=True)
    justificativa: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
