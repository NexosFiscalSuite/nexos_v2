"""Regras De/Para CFOP -> Tipo de Item + RLS.

Revision ID: 0006_cfop_regras
Revises: 0005_tipo_nota_uf
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_cfop_regras"
down_revision: str | None = "0005_tipo_nota_uf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "current_setting('app.current_tenant', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "cfop_regras",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo_item", sa.String(40), nullable=False),
        sa.Column("cfop_origem", sa.String(10), nullable=False),
        sa.Column("cfop_destino", sa.String(10), nullable=False),
        sa.Column("usa_extensao", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("extensao", sa.String(20)),
        sa.Column("descricao", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "cfop_origem", name="uq_cfop_regra"),
    )
    op.create_index("ix_cfop_regras_tenant_id", "cfop_regras", ["tenant_id"])
    op.create_index("ix_cfop_regras_origem", "cfop_regras", ["cfop_origem"])
    op.execute("ALTER TABLE cfop_regras ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON cfop_regras "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )
    op.execute(
        """
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname='nexos_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON cfop_regras TO nexos_app;
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON cfop_regras")
    op.drop_table("cfop_regras")
