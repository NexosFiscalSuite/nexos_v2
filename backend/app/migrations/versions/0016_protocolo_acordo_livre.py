"""Adapta matriz_protocolo_st ao CRUD simples (par UF + acordo livre):
- numero_acordo de 20 → 80 chars (cabe "Convênio ICMS 142/2018" etc.);
- ncm e tipo_acordo passam a NULL (escopo é o par UF origem→destino, sem NCM).

Revision ID: 0016_protocolo_acordo_livre
Revises: 0015_grant_matriz_dml_app
Create Date: 2026-06-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_protocolo_acordo_livre"
down_revision: str | None = "0015_grant_matriz_dml_app"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "matriz_protocolo_st", "numero_acordo",
        existing_type=sa.String(20), type_=sa.String(80),
    )
    op.alter_column("matriz_protocolo_st", "ncm", existing_type=sa.String(8), nullable=True)
    op.alter_column("matriz_protocolo_st", "tipo_acordo", existing_type=sa.String(3), nullable=True)


def downgrade() -> None:
    op.alter_column("matriz_protocolo_st", "tipo_acordo", existing_type=sa.String(3), nullable=False)
    op.alter_column("matriz_protocolo_st", "ncm", existing_type=sa.String(8), nullable=False)
    op.alter_column(
        "matriz_protocolo_st", "numero_acordo",
        existing_type=sa.String(80), type_=sa.String(20),
    )
