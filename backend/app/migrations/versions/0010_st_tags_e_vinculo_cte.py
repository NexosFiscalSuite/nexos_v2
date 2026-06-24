"""Tags de ST/FCP no nota_itens + tabela nfe_cte_vinculo (N:N, ADR-0001).

Revision ID: 0010_st_tags_e_vinculo_cte
Revises: 0009_matrizes_st
Create Date: 2026-06-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010_st_tags_e_vinculo_cte"
down_revision: str | None = "0009_matrizes_st"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(15, 2)
_PCT = sa.Numeric(5, 2)
_TENANT = "current_setting('app.current_tenant', true)::uuid"

_COLUNAS_MONEY = ("valor_outro", "valor_ipi", "v_bc_st", "v_fcp", "v_bc_fcp", "v_fcp_st", "v_bc_fcp_st")
_COLUNAS_PCT = ("p_icms", "p_red_bc", "p_mva_st", "p_red_bc_st", "p_icms_st", "p_fcp", "p_fcp_st")


def upgrade() -> None:
    # --- Tags de ST/FCP por item ---
    for col in _COLUNAS_MONEY:
        op.add_column("nota_itens", sa.Column(col, _MONEY, nullable=False, server_default="0"))
    for col in _COLUNAS_PCT:
        op.add_column("nota_itens", sa.Column(col, _PCT, nullable=False, server_default="0"))
    op.add_column("nota_itens", sa.Column("cest", sa.String(7)))
    op.add_column("nota_itens", sa.Column("orig", sa.String(1)))
    op.add_column("nota_itens", sa.Column("cst", sa.String(2)))
    op.add_column("nota_itens", sa.Column("csosn", sa.String(3)))
    op.add_column("nota_itens", sa.Column("mod_bc_st", sa.Integer()))

    # --- Vínculo N:N NF-e <-> CT-e (ADR-0001), tenant-scoped + RLS ---
    op.create_table(
        "nfe_cte_vinculo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("chave_nfe", sa.String(44), nullable=False),
        sa.Column("chave_cte", sa.String(44), nullable=False),
        sa.Column("vtprest", _MONEY, nullable=False, server_default="0"),
        sa.Column("tp_cte", sa.String(2)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "empresa_id", "chave_nfe", "chave_cte", name="uq_nfe_cte"),
    )
    op.create_index("ix_nfe_cte_tenant_id", "nfe_cte_vinculo", ["tenant_id"])
    op.create_index("ix_nfe_cte_empresa_id", "nfe_cte_vinculo", ["empresa_id"])
    op.create_index("ix_nfe_cte_chave_nfe", "nfe_cte_vinculo", ["chave_nfe"])
    op.create_index("ix_nfe_cte_chave_cte", "nfe_cte_vinculo", ["chave_cte"])

    op.execute("ALTER TABLE nfe_cte_vinculo ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON nfe_cte_vinculo "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON nfe_cte_vinculo TO nexos_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON nfe_cte_vinculo")
    op.drop_table("nfe_cte_vinculo")
    for col in ("mod_bc_st", "csosn", "cst", "orig", "cest", *_COLUNAS_PCT, *_COLUNAS_MONEY):
        op.drop_column("nota_itens", col)
