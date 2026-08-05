"""Triagem de divergências de ST (roadmap do motor, item 1).

A auditoria diz O QUE está errado; a triagem registra o que o escritório FEZ:
COBRADA (carta), JUSTIFICADA (base normativa — baixa) ou ACEITA (cliente
assume). Tabela própria, tenant-scoped (RLS FORCE), ancorada em
(nota_id, numero_item) — sobrevive ao reprocessamento da auditoria.

Revision ID: 0031_divergencia_triagem
Revises: 0030_ultima_verificacao_matrizes
Create Date: 2026-08-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0031_divergencia_triagem"
down_revision: str | None = "0030_ultima_verificacao_matrizes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "current_setting('app.current_tenant')::uuid"


def upgrade() -> None:
    op.create_table(
        "divergencia_triagem",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(),
                  sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(),
                  sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nota_id", sa.Uuid(),
                  sa.ForeignKey("notas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("observacao", sa.String(300), nullable=True),
        sa.Column("definido_por", sa.String(160), nullable=True),
        sa.Column("definido_em", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "nota_id", "numero_item", name="uq_triagem_item"),
    )
    op.create_index("ix_divergencia_triagem_tenant_id", "divergencia_triagem", ["tenant_id"])
    op.create_index("ix_divergencia_triagem_empresa_id", "divergencia_triagem", ["empresa_id"])
    op.create_index("ix_divergencia_triagem_nota_id", "divergencia_triagem", ["nota_id"])

    op.execute("ALTER TABLE divergencia_triagem ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE divergencia_triagem FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON divergencia_triagem "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON divergencia_triagem TO nexos_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_table("divergencia_triagem")
