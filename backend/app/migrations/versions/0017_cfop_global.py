"""Torna o De/Para CFOP GLOBAL (regra do escritório, não por tenant), igual às
matrizes fiscais: remove o tenant_id + a RLS, deduplica por cfop_origem e cria
unique global. Os grants ao nexos_app já existem (da 0006).

Revision ID: 0017_cfop_global
Revises: 0016_protocolo_acordo_livre
Create Date: 2026-06-26
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0017_cfop_global"
down_revision: str | None = "0016_protocolo_acordo_livre"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON cfop_regras")
    op.execute("ALTER TABLE cfop_regras DISABLE ROW LEVEL SECURITY")
    # Deduplica por cfop_origem (mantém 1 linha) antes do unique global.
    op.execute(
        "DELETE FROM cfop_regras a USING cfop_regras b "
        "WHERE a.ctid < b.ctid AND a.cfop_origem = b.cfop_origem"
    )
    op.drop_constraint("uq_cfop_regra", "cfop_regras", type_="unique")
    op.drop_index("ix_cfop_regras_tenant_id", table_name="cfop_regras")
    op.drop_column("cfop_regras", "tenant_id")
    op.create_unique_constraint("uq_cfop_origem", "cfop_regras", ["cfop_origem"])


def downgrade() -> None:
    op.drop_constraint("uq_cfop_origem", "cfop_regras", type_="unique")
    op.add_column(
        "cfop_regras",
        sa.Column("tenant_id", sa.Uuid(), nullable=True),   # lossy: tenant não é recuperável
    )
    op.create_index("ix_cfop_regras_tenant_id", "cfop_regras", ["tenant_id"])
    op.create_unique_constraint("uq_cfop_regra", "cfop_regras", ["tenant_id", "cfop_origem"])
