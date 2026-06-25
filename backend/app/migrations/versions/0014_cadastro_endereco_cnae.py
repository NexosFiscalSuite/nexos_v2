"""Enriquece cadastros: endereço (CEP/logradouro/número/bairro) + CNAE em
empresas; CNAE em contrapartes (que já têm endereço).

Revision ID: 0014_cadastro_endereco_cnae
Revises: 0013_auditoria_observacao
Create Date: 2026-06-25
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_cadastro_endereco_cnae"
down_revision: str | None = "0013_auditoria_observacao"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("empresas", sa.Column("cep", sa.String(9)))
    op.add_column("empresas", sa.Column("logradouro", sa.String(200)))
    op.add_column("empresas", sa.Column("numero", sa.String(20)))
    op.add_column("empresas", sa.Column("bairro", sa.String(120)))
    op.add_column("empresas", sa.Column("cnae", sa.String(20)))
    # Contrapartes já têm endereço; falta só o CNAE principal.
    op.add_column("contrapartes", sa.Column("cnae", sa.String(20)))


def downgrade() -> None:
    op.drop_column("contrapartes", "cnae")
    for col in ("cnae", "bairro", "numero", "logradouro", "cep"):
        op.drop_column("empresas", col)
