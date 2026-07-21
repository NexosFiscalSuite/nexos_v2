"""cClassTrib por item (IBS/CBS): a classificação tributária da operação.

Com o CST + cClassTrib dá para saber se o item está DESOBRIGADO das alíquotas
de teste de 2026 (isenção, imunidade, diferimento, monofásica...) — sem isso o
verificador apontava alíquota zerada legítima como problema.

Revision ID: 0024_cclasstrib_item
Revises: 0023_matriz_created_at
Create Date: 2026-07-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_cclasstrib_item"
down_revision: str | None = "0023_matriz_created_at"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("nota_itens", sa.Column("c_class_trib", sa.String(6), nullable=True))


def downgrade() -> None:
    op.drop_column("nota_itens", "c_class_trib")
