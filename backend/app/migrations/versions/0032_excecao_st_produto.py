"""Exceções de enquadramento ST por empresa e código de produto.

Revision ID: 0032_excecao_st_produto
Revises: 0031_divergencia_triagem
Create Date: 2026-08-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_excecao_st_produto"
down_revision: str | None = "0031_divergencia_triagem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "current_setting('app.current_tenant')::uuid"


def upgrade() -> None:
    op.create_table(
        "excecao_enquadramento_st_produto",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("codigo_produto", sa.String(60), nullable=False),
        sa.Column("descricao_produto", sa.String(500), nullable=True),
        sa.Column("ncm", sa.String(8), nullable=True),
        sa.Column("data_inicio_vigencia", sa.Date(), nullable=False),
        sa.Column("data_fim_vigencia", sa.Date(), nullable=True),
        sa.Column("tributado_icms", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("lei_icms", sa.String(2000), nullable=True),
        sa.Column("ativo", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("definido_por", sa.String(160), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "data_fim_vigencia IS NULL OR data_fim_vigencia >= data_inicio_vigencia",
            name="ck_excecao_st_periodo",
        ),
        sa.UniqueConstraint(
            "tenant_id", "empresa_id", "codigo_produto", "data_inicio_vigencia",
            name="uq_excecao_st_empresa_produto_inicio",
        ),
    )
    op.create_index("ix_excecao_enquadramento_st_produto_tenant_id", "excecao_enquadramento_st_produto", ["tenant_id"])
    op.create_index("ix_excecao_enquadramento_st_produto_empresa_id", "excecao_enquadramento_st_produto", ["empresa_id"])
    op.create_index("ix_excecao_st_busca", "excecao_enquadramento_st_produto", ["empresa_id", "codigo_produto"])

    op.execute("ALTER TABLE excecao_enquadramento_st_produto ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE excecao_enquadramento_st_produto FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON excecao_enquadramento_st_produto "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON excecao_enquadramento_st_produto TO nexos_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_table("excecao_enquadramento_st_produto")
