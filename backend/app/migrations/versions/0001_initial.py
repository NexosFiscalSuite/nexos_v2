"""Initial: plans, tenants, users, refresh_tokens + RLS + seed de planos.

Revision ID: 0001_initial
Revises:
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Expressão do tenant corrente. `true` (missing_ok) => NULL se não setado =>
# nenhuma linha casa (fail-closed).
_TENANT = "current_setting('app.current_tenant', true)::uuid"


def _enable_rls(table: str, column: str = "tenant_id") -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY tenant_isolation ON {table}
            USING ({column} = {_TENANT})
            WITH CHECK ({column} = {_TENANT})
        """
    )


def upgrade() -> None:
    # ── plans (referência global, SEM RLS) ──────────────────────────────────
    op.create_table(
        "plans",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("rate_limit_per_min", sa.Integer(), nullable=False, server_default="120"),
        sa.Column("max_empresas", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("max_users", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("price_cents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    )

    # ── tenants (raiz do isolamento) ────────────────────────────────────────
    op.create_table(
        "tenants",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("cnpj", sa.String(14), nullable=False, unique=True),
        sa.Column("razao_social", sa.String(200), nullable=False),
        sa.Column("slug", sa.String(60), nullable=False, unique=True),
        sa.Column("plan_id", sa.Uuid(), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="trial"),
        sa.Column("trial_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # ── users ───────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="user"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "email", name="uq_user_tenant_email"),
    )
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])

    # ── refresh_tokens ──────────────────────────────────────────────────────
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("jti", sa.Uuid(), nullable=False, unique=True),
        sa.Column(
            "tenant_id",
            sa.Uuid(),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_refresh_tokens_tenant_id", "refresh_tokens", ["tenant_id"])

    # ── RLS ─────────────────────────────────────────────────────────────────
    # tenants: cada tenant só enxerga a própria linha (coluna alvo = id).
    _enable_rls("tenants", column="id")
    _enable_rls("users")
    _enable_rls("refresh_tokens")

    # ── Grants para a role do app (se existir) ──────────────────────────────
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nexos_app;
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nexos_app;
            END IF;
        END
        $$;
        """
    )

    # ── Seed de planos ──────────────────────────────────────────────────────
    op.execute(
        """
        INSERT INTO plans (id, code, name, rate_limit_per_min, max_empresas, max_users, price_cents, is_active)
        VALUES
          (gen_random_uuid(), 'trial',      'Trial (14 dias)', 120,  5,   3,      0, true),
          (gen_random_uuid(), 'free',       'Free',            120,  3,   2,      0, true),
          (gen_random_uuid(), 'pro',        'Pro',             600,  50,  15,  9900, true),
          (gen_random_uuid(), 'enterprise', 'Enterprise',     3000, 1000, 200, 49900, true)
        """
    )


def downgrade() -> None:
    for t in ("refresh_tokens", "users", "tenants"):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
    op.drop_table("refresh_tokens")
    op.drop_table("users")
    op.drop_table("tenants")
    op.drop_table("plans")
