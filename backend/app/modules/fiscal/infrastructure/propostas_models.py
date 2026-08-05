"""Fila de propostas da auto-alimentação das matrizes (Fase 1 da automação).

O robô NUNCA escreve direto nas matrizes: cada mudança detectada na fonte
vira uma PROPOSTA que o curador aprova (vendo o diff) ou rejeita — e rejeição
suprime a re-proposta idêntica para sempre. `FonteSnapshot` guarda o que foi
baixado (hash + conteúdo bruto) para trilha de origem e detecção de mudança.
Tabelas GLOBAIS (sem tenant), como as matrizes que alimentam.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, LargeBinary, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

STATUS_PENDENTE = "PENDENTE"
STATUS_APROVADA = "APROVADA"
STATUS_REJEITADA = "REJEITADA"

ACAO_INSERIR = "INSERIR"
ACAO_ATUALIZAR = "ATUALIZAR"
ACAO_NOVA_VIGENCIA = "NOVA_VIGENCIA"
ACAO_ENCERRAR_VIGENCIA = "ENCERRAR_VIGENCIA"
# Reconferência (Fase 4): aprovar = "continua valendo" — só renova o carimbo
# de verificação da linha; mudou? rejeita e ajusta pelo CRUD (vigência nova).
ACAO_REVALIDAR = "REVALIDAR"

# with_variant: permite aos testes (sqlite) criar a tabela; Postgres segue JSONB.
_JSON = JSONB().with_variant(JSON(), "sqlite")


class FonteSnapshot(Base):
    """Uma captura da fonte oficial: o que foi baixado, quando e com que hash.
    Serve de trilha ('de onde veio esse dado?') e de detector de mudança."""

    __tablename__ = "fonte_snapshot"

    id: Mapped[int] = mapped_column(primary_key=True)
    fonte: Mapped[str] = mapped_column(String(120), index=True)
    url: Mapped[str] = mapped_column(String(500))
    hash_conteudo: Mapped[str] = mapped_column(String(64))     # SHA-256 do bruto
    resumo: Mapped[str | None] = mapped_column(String(200), nullable=True)
    conteudo: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    baixado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class MatrizProposta(Base):
    """Uma mudança proposta em uma matriz fiscal, aguardando curadoria.

    `payload` está no formato do schema Create da matriz (o mesmo do CRUD),
    então a aplicação valida e grava pelo caminho já testado. `linha_atual`
    congela a linha vigente no momento da proposta — é o lado 'de' do diff.
    """

    __tablename__ = "matriz_proposta"
    __table_args__ = (Index("ix_proposta_fila", "status", "tipo_matriz"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo_matriz: Mapped[str] = mapped_column(String(20))   # chaves do registry MATRIZES
    acao: Mapped[str] = mapped_column(String(20), default=ACAO_INSERIR)
    chave_resumo: Mapped[str] = mapped_column(String(200))  # "MG · NCM … · CEST …"
    payload: Mapped[dict] = mapped_column(_JSON)
    linha_atual_id: Mapped[int | None] = mapped_column(nullable=True)
    linha_atual: Mapped[dict | None] = mapped_column(_JSON, nullable=True)
    fonte: Mapped[str] = mapped_column(String(120))
    fonte_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("fonte_snapshot.id", ondelete="SET NULL"), nullable=True
    )
    hash_proposta: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(10), default=STATUS_PENDENTE)
    motivo_rejeicao: Mapped[str | None] = mapped_column(String(300), nullable=True)
    revisado_por: Mapped[str | None] = mapped_column(String(160), nullable=True)
    revisado_em: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
