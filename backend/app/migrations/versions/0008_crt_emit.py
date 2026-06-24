"""Nota: CRT do emitente (regime tributário) — insumo do motor de auditoria de ST.

Revision ID: 0008_crt_emit
Revises: 0007_grupos_audit
Create Date: 2026-06-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_crt_emit"
down_revision: str | None = "0007_grupos_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notas", sa.Column("crt_emit", sa.String(1), nullable=True))


def downgrade() -> None:
    op.drop_column("notas", "crt_emit")
