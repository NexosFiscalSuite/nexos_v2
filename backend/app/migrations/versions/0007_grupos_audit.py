"""Grupos (controle de acesso) + trilha de auditoria (audit_log) + RLS.

Revision ID: 0007_grupos_audit
Revises: 0006_cfop_regras
Create Date: 2026-06-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_grupos_audit"
down_revision: str | None = "0006_cfop_regras"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "current_setting('app.current_tenant', true)::uuid"
_TABELAS = ["grupos", "grupo_membros", "empresa_grupo", "audit_log"]


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )
    op.execute(
        f"""
        DO $$ BEGIN
          IF EXISTS (SELECT FROM pg_roles WHERE rolname='nexos_app') THEN
            GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO nexos_app;
          END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.create_table(
        "grupos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("descricao", sa.String(400)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "nome", name="uq_grupo_tenant_nome"),
    )
    op.create_index("ix_grupos_tenant_id", "grupos", ["tenant_id"])

    op.create_table(
        "grupo_membros",
        sa.Column("grupo_id", sa.Uuid(), sa.ForeignKey("grupos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("papel", sa.String(20), nullable=False, server_default="membro"),
    )
    op.create_index("ix_grupo_membros_tenant_id", "grupo_membros", ["tenant_id"])
    op.create_index("ix_grupo_membros_user", "grupo_membros", ["user_id"])

    op.create_table(
        "empresa_grupo",
        sa.Column("grupo_id", sa.Uuid(), sa.ForeignKey("grupos.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_empresa_grupo_tenant_id", "empresa_grupo", ["tenant_id"])
    op.create_index("ix_empresa_grupo_empresa", "empresa_grupo", ["empresa_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("acao", sa.String(60), nullable=False),
        sa.Column("entidade", sa.String(60)),
        sa.Column("entidade_id", sa.String(60)),
        sa.Column("detalhe", postgresql.JSONB()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_audit_log_tenant_id", "audit_log", ["tenant_id"])
    op.create_index("ix_audit_log_created", "audit_log", ["created_at"])
    op.create_index("ix_audit_log_user", "audit_log", ["user_id"])

    for t in _TABELAS:
        _rls(t)


def downgrade() -> None:
    for t in reversed(_TABELAS):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
    op.drop_table("audit_log")
    op.drop_table("empresa_grupo")
    op.drop_table("grupo_membros")
    op.drop_table("grupos")
