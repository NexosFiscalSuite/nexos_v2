"""Proposta de matriz ganha campo de evidência.

Proposta vinda de fonte oficial se explica sozinha — a norma está no
`base_legal`. Já a proposta APRENDIDA das próprias notas não tem norma: sem
registrar quantos fornecedores e quantas notas sustentam o valor, o curador
aprovaria um número no escuro.

Revision ID: 0036_proposta_evidencia
Revises: 0035_aliquota_por_ncm
Create Date: 2026-08-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0036_proposta_evidencia"
down_revision: str | None = "0035_aliquota_por_ncm"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "matriz_proposta",
        sa.Column("evidencia", postgresql.JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("matriz_proposta", "evidencia")
