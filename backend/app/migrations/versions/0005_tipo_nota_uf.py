"""Notas: tipo_nota (classificação da entrada) + uf_emit/uf_dest (cabeçalho).

Revision ID: 0005_tipo_nota_uf
Revises: 0004_item_icms
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_tipo_nota_uf"
down_revision: str | None = "0004_item_icms"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notas", sa.Column("uf_emit", sa.String(2), nullable=True))
    op.add_column("notas", sa.Column("uf_dest", sa.String(2), nullable=True))
    op.add_column("notas", sa.Column("tipo_nota", sa.String(80), nullable=True))


def downgrade() -> None:
    op.drop_column("notas", "tipo_nota")
    op.drop_column("notas", "uf_dest")
    op.drop_column("notas", "uf_emit")
