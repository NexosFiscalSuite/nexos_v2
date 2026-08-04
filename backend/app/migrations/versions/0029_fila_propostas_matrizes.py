"""Fila de propostas da auto-alimentação (Fase 1 da automação das matrizes).

O crawler deixa de escrever direto na matriz: o diff da fonte vira proposta
em `matriz_proposta`, revisada na aba Revisão (aprovar aplica pela mesma
validação do CRUD; rejeitar suprime a re-proposta). `fonte_snapshot` guarda
hash + conteúdo do que foi baixado (trilha de origem e detecção de mudança).

Revision ID: 0029_fila_propostas_matrizes
Revises: 0028_retroage_vigencia_cest
Create Date: 2026-08-04
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_fila_propostas_matrizes"
down_revision: str | None = "0028_retroage_vigencia_cest"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fonte_snapshot",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fonte", sa.String(120), nullable=False),
        sa.Column("url", sa.String(500), nullable=False),
        sa.Column("hash_conteudo", sa.String(64), nullable=False),
        sa.Column("resumo", sa.String(200), nullable=True),
        sa.Column("conteudo", sa.LargeBinary(), nullable=True),
        sa.Column(
            "baixado_em", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_fonte_snapshot_fonte", "fonte_snapshot", ["fonte"])

    op.create_table(
        "matriz_proposta",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tipo_matriz", sa.String(20), nullable=False),
        sa.Column("acao", sa.String(20), nullable=False, server_default="INSERIR"),
        sa.Column("chave_resumo", sa.String(200), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("linha_atual_id", sa.Integer(), nullable=True),
        sa.Column("linha_atual", postgresql.JSONB(), nullable=True),
        sa.Column("fonte", sa.String(120), nullable=False),
        sa.Column(
            "fonte_snapshot_id", sa.Integer(),
            sa.ForeignKey("fonte_snapshot.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("hash_proposta", sa.String(64), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDENTE"),
        sa.Column("motivo_rejeicao", sa.String(300), nullable=True),
        sa.Column("revisado_por", sa.String(160), nullable=True),
        sa.Column("revisado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ),
    )
    op.create_index("ix_matriz_proposta_hash_proposta", "matriz_proposta", ["hash_proposta"])
    op.create_index("ix_proposta_fila", "matriz_proposta", ["status", "tipo_matriz"])


def downgrade() -> None:
    op.drop_table("matriz_proposta")
    op.drop_table("fonte_snapshot")
