"""Tabela de auditoria de ICMS-ST por item (Vault §9).

Revision ID: 0011_auditoria_icms_st
Revises: 0010_st_tags_e_vinculo_cte
Create Date: 2026-06-24
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_auditoria_icms_st"
down_revision: str | None = "0010_st_tags_e_vinculo_cte"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MONEY = sa.Numeric(15, 2)
_PCT = sa.Numeric(5, 2)
_TENANT = "current_setting('app.current_tenant', true)::uuid"


def upgrade() -> None:
    op.create_table(
        "auditoria_icms_st",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("nota_id", sa.Uuid(), sa.ForeignKey("notas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=False),
        sa.Column("cst_csosn", sa.String(3)),
        sa.Column("mod_bc_st", sa.Integer()),
        sa.Column("pmva_xml", _PCT, nullable=False, server_default="0"),
        sa.Column("pmva_calculada", _PCT, nullable=False, server_default="0"),
        sa.Column("vbc_st_xml", _MONEY, nullable=False, server_default="0"),
        sa.Column("vbc_st_calculado", _MONEY, nullable=False, server_default="0"),
        sa.Column("vicms_st_xml", _MONEY, nullable=False, server_default="0"),
        sa.Column("vicms_st_calculado", _MONEY, nullable=False, server_default="0"),
        sa.Column("vicms_st_divergencia", _MONEY, nullable=False, server_default="0"),
        sa.Column("vfcp_st_xml", _MONEY, nullable=False, server_default="0"),
        sa.Column("vfcp_st_calculado", _MONEY, nullable=False, server_default="0"),
        sa.Column("status", sa.String(14), nullable=False),
        sa.Column("codigo_erro", sa.String(120)),
        sa.Column("memoria", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "nota_id", "numero_item", name="uq_auditoria_st_item"),
    )
    op.create_index("ix_auditoria_st_tenant_id", "auditoria_icms_st", ["tenant_id"])
    op.create_index("ix_auditoria_st_empresa_id", "auditoria_icms_st", ["empresa_id"])
    op.create_index("ix_auditoria_st_nota_id", "auditoria_icms_st", ["nota_id"])
    op.create_index("ix_auditoria_st_chave", "auditoria_icms_st", ["chave_acesso"])
    # Índice parcial: relatório de divergências varre só os DIVERGENTE.
    op.create_index(
        "ix_auditoria_st_divergente",
        "auditoria_icms_st",
        ["status"],
        postgresql_where=sa.text("status = 'DIVERGENTE'"),
    )

    op.execute("ALTER TABLE auditoria_icms_st ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON auditoria_icms_st "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON auditoria_icms_st TO nexos_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS tenant_isolation ON auditoria_icms_st")
    op.drop_table("auditoria_icms_st")
