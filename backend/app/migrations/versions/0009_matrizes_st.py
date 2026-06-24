"""Matrizes fiscais globais (MVA, enquadramento, protocolo, FCP) com vigência.

Tabelas de REFERÊNCIA — globais, sem tenant_id e SEM RLS (a lei é universal).
Cada linha tem vigência temporal (ADR-0002).

Revision ID: 0009_matrizes_st
Revises: 0008_crt_emit
Create Date: 2026-06-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009_matrizes_st"
down_revision: str | None = "0008_crt_emit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PCT = sa.Numeric(5, 2)


def _vigencia() -> list[sa.Column]:
    return [
        sa.Column("data_inicio_vigencia", sa.Date(), nullable=False),
        sa.Column("data_fim_vigencia", sa.Date(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "matriz_mva",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("ncm", sa.String(8), nullable=False),
        sa.Column("cest", sa.String(7), nullable=False),
        sa.Column("uf_destino", sa.String(2), nullable=False),
        sa.Column("mva_original", _PCT, nullable=False),
        sa.Column("ato_legal", sa.String(120)),
        *_vigencia(),
        sa.UniqueConstraint(
            "ncm", "cest", "uf_destino", "data_inicio_vigencia", name="uq_mva_vigencia"
        ),
    )
    op.create_index("ix_mva_busca", "matriz_mva", ["uf_destino", "ncm", "cest"])

    op.create_table(
        "matriz_enquadramento_st",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uf_destino", sa.String(2), nullable=False),
        sa.Column("ncm", sa.String(8), nullable=False),
        sa.Column("cest", sa.String(7), nullable=False),
        sa.Column("regime", sa.String(12), nullable=False),
        sa.Column("segmento", sa.String(120)),
        sa.Column("ato_legal", sa.String(120)),
        *_vigencia(),
        sa.UniqueConstraint(
            "uf_destino", "ncm", "cest", "data_inicio_vigencia", name="uq_enq_vigencia"
        ),
        sa.CheckConstraint("regime IN ('ST','TN','ST_ENTRADA')", name="chk_enq_regime"),
    )
    op.create_index("ix_enq_busca", "matriz_enquadramento_st", ["uf_destino", "ncm", "cest"])

    op.create_table(
        "matriz_protocolo_st",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uf_origem", sa.String(2), nullable=False),
        sa.Column("uf_destino", sa.String(2), nullable=False),
        sa.Column("ncm", sa.String(8), nullable=False),
        sa.Column("tipo_acordo", sa.String(3), nullable=False),
        sa.Column("numero_acordo", sa.String(20), nullable=False),
        sa.Column("situacao", sa.String(10), nullable=False, server_default="ATIVO"),
        *_vigencia(),
    )
    op.create_index(
        "ix_protocolo_busca", "matriz_protocolo_st", ["uf_origem", "uf_destino", "ncm"]
    )

    op.create_table(
        "matriz_fcp",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uf_destino", sa.String(2), nullable=False),
        sa.Column("ncm", sa.String(8), nullable=False),
        sa.Column("aliq_fcp_interno", _PCT, nullable=False, server_default="0"),
        sa.Column("aliq_fcp_st", _PCT, nullable=False, server_default="0"),
        sa.Column("ato_legal", sa.String(120)),
        *_vigencia(),
        sa.UniqueConstraint("uf_destino", "ncm", "data_inicio_vigencia", name="uq_fcp_vigencia"),
    )
    op.create_index("ix_fcp_busca", "matriz_fcp", ["uf_destino", "ncm"])


def downgrade() -> None:
    op.drop_table("matriz_fcp")
    op.drop_table("matriz_protocolo_st")
    op.drop_table("matriz_enquadramento_st")
    op.drop_table("matriz_mva")
