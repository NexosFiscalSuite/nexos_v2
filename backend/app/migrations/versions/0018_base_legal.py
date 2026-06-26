"""Padroniza a rastreabilidade legal: renomeia ato_legal → base_legal nas matrizes
MVA, Enquadramento e FCP; adiciona base_legal ao Protocolo (que só tinha o Acordo).

Revision ID: 0018_base_legal
Revises: 0017_cfop_global
Create Date: 2026-06-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018_base_legal"
down_revision: str | None = "0017_cfop_global"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column("matriz_mva", "ato_legal", new_column_name="base_legal")
    op.alter_column("matriz_enquadramento_st", "ato_legal", new_column_name="base_legal")
    op.alter_column("matriz_fcp", "ato_legal", new_column_name="base_legal")
    op.add_column("matriz_protocolo_st", sa.Column("base_legal", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("matriz_protocolo_st", "base_legal")
    op.alter_column("matriz_fcp", "base_legal", new_column_name="ato_legal")
    op.alter_column("matriz_enquadramento_st", "base_legal", new_column_name="ato_legal")
    op.alter_column("matriz_mva", "base_legal", new_column_name="ato_legal")
