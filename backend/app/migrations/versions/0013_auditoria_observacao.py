"""Coluna observacao na auditoria_icms_st (motivo do NAO_AUDITAVEL).

Revision ID: 0013_auditoria_observacao
Revises: 0012_grant_matrizes_app
Create Date: 2026-06-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_auditoria_observacao"
down_revision: str | None = "0012_grant_matrizes_app"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("auditoria_icms_st", sa.Column("observacao", sa.String(255)))


def downgrade() -> None:
    op.drop_column("auditoria_icms_st", "observacao")
