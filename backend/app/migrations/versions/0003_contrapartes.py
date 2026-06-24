"""Item 3: tabela contrapartes (clientes/fornecedores) + RLS.

Revision ID: 0003_contrapartes
Revises: 0002_fiscal
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_contrapartes"
down_revision: str | None = "0002_fiscal"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "current_setting('app.current_tenant', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "contrapartes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(11), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("razao_social", sa.String(200)),
        sa.Column("nome_fantasia", sa.String(200)),
        sa.Column("situacao", sa.String(40)),
        sa.Column("uf", sa.String(2)),
        sa.Column("municipio", sa.String(120)),
        sa.Column("atividade", sa.String(255)),
        sa.Column("porte", sa.String(40)),
        sa.Column("regime", sa.String(40)),
        sa.Column("inscricao_estadual", sa.String(30)),
        sa.Column("logradouro", sa.String(200)),
        sa.Column("numero", sa.String(20)),
        sa.Column("complemento", sa.String(120)),
        sa.Column("bairro", sa.String(120)),
        sa.Column("cep", sa.String(9)),
        sa.Column("pais", sa.String(60)),
        sa.Column("origem", sa.String(20), nullable=False, server_default="manual"),
        sa.Column("pendente_revisao", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_lookup_at", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "empresa_id", "tipo", "cnpj", name="uq_contraparte"),
    )
    op.create_index("ix_contrapartes_tenant_id", "contrapartes", ["tenant_id"])
    op.create_index("ix_contrapartes_empresa_id", "contrapartes", ["empresa_id"])
    op.create_index("ix_contrapartes_cnpj", "contrapartes", ["cnpj"])

    op.execute("ALTER TABLE contrapartes ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON contrapartes "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON contrapartes TO nexos_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON contrapartes")
    op.drop_table("contrapartes")
