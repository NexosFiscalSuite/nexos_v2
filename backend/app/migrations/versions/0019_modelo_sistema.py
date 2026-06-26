"""Templates de fábrica: flag `sistema` no relatorio_modelos (modelos oficiais,
não editáveis/excluíveis — só visualizar ou duplicar).

Revision ID: 0019_modelo_sistema
Revises: 0018_base_legal
Create Date: 2026-06-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0019_modelo_sistema"
down_revision: str | None = "0018_base_legal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "relatorio_modelos",
        sa.Column("sistema", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("relatorio_modelos", "sistema")
