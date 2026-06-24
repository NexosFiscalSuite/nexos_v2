"""Itens: colunas de ICMS (base de cálculo, valor ICMS, ICMS-ST, valor produto).

Revision ID: 0004_item_icms
Revises: 0003_contrapartes
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_item_icms"
down_revision: str | None = "0003_contrapartes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(15, 2)


def upgrade() -> None:
    for col in ("valor_produto", "base_calculo", "valor_icms", "valor_icms_st"):
        op.add_column("nota_itens", sa.Column(col, _MONEY, nullable=False, server_default="0"))


def downgrade() -> None:
    for col in ("valor_icms_st", "valor_icms", "base_calculo", "valor_produto"):
        op.drop_column("nota_itens", col)
