"""Fase 3: empresas, processing_jobs, notas/itens/eventos, quebra_ciencia,
relatorio_modelos. Todas tenant-scoped com RLS.

Revision ID: 0002_fiscal
Revises: 0001_initial
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0002_fiscal"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TENANT = "current_setting('app.current_tenant', true)::uuid"
_MONEY = sa.Numeric(15, 2)
_QTY = sa.Numeric(15, 4)


def _rls(table: str) -> None:
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY tenant_isolation ON {table} "
        f"USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})"
    )


def upgrade() -> None:
    # ── empresas ────────────────────────────────────────────────────────────
    op.create_table(
        "empresas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=False),
        sa.Column("razao_social", sa.String(200), nullable=False),
        sa.Column("nome_fantasia", sa.String(200)),
        sa.Column("regime", sa.String(40)),
        sa.Column("uf", sa.String(2)),
        sa.Column("municipio", sa.String(120)),
        sa.Column("inscricao_estadual", sa.String(30)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "cnpj", name="uq_empresa_tenant_cnpj"),
    )
    op.create_index("ix_empresas_tenant_id", "empresas", ["tenant_id"])
    op.create_index("ix_empresas_cnpj", "empresas", ["cnpj"])

    # ── processing_jobs ─────────────────────────────────────────────────────
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result", JSONB()),
        sa.Column("error", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_jobs_tenant_id", "processing_jobs", ["tenant_id"])

    # ── notas ───────────────────────────────────────────────────────────────
    op.create_table(
        "notas",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chave_acesso", sa.String(60), nullable=False),
        sa.Column("tipo", sa.String(10), nullable=False),
        sa.Column("fluxo", sa.String(10), nullable=False),
        sa.Column("modelo", sa.String(10), nullable=False),
        sa.Column("serie", sa.String(10)),
        sa.Column("numero", sa.String(20)),
        sa.Column("cnpj_emit", sa.String(14)),
        sa.Column("nome_emit", sa.String(200)),
        sa.Column("cnpj_dest", sa.String(14)),
        sa.Column("nome_dest", sa.String(200)),
        sa.Column("transportadora_cnpj", sa.String(14)),
        sa.Column("transportadora_nome", sa.String(200)),
        sa.Column("valor_total", _MONEY, server_default="0"),
        sa.Column("data_emissao", sa.String(10)),
        sa.Column("data_entrada", sa.String(10)),
        sa.Column("competencia", sa.String(7)),
        sa.Column("iss_retido", sa.Integer()),
        sa.Column("ano", sa.String(4)),
        sa.Column("mes", sa.String(2)),
        sa.Column("storage_key", sa.String(400)),
        sa.Column("status", sa.String(12), nullable=False, server_default="ativa"),
        sa.Column("cancelada_em", sa.String(40)),
        sa.Column("protocolo", sa.String(60)),
        sa.Column("tem_correcao", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("uploaded_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("tenant_id", "empresa_id", "chave_acesso", name="uq_nota_chave"),
    )
    op.create_index("ix_notas_tenant_id", "notas", ["tenant_id"])
    op.create_index("ix_notas_empresa_id", "notas", ["empresa_id"])
    op.create_index("ix_notas_chave", "notas", ["chave_acesso"])
    op.create_index("ix_notas_emp_fluxo_periodo", "notas", ["empresa_id", "fluxo", "ano", "mes"])

    # ── nota_itens ──────────────────────────────────────────────────────────
    op.create_table(
        "nota_itens",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nota_id", sa.Uuid(), sa.ForeignKey("notas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero_item", sa.Integer(), nullable=False),
        sa.Column("codigo", sa.String(60)),
        sa.Column("descricao", sa.String(500)),
        sa.Column("ncm", sa.String(10)),
        sa.Column("cfop", sa.String(6)),
        sa.Column("cfop_original", sa.String(6)),
        sa.Column("tipo_sped", sa.String(40)),
        sa.Column("unidade", sa.String(10)),
        sa.Column("quantidade", _QTY, server_default="0"),
        sa.Column("valor_unitario", _QTY, server_default="0"),
        sa.Column("valor_total", _MONEY, server_default="0"),
        sa.Column("valor_desconto", _MONEY, server_default="0"),
        sa.Column("valor_frete", _MONEY, server_default="0"),
        sa.Column("valor_seguro", _MONEY, server_default="0"),
        sa.UniqueConstraint("nota_id", "numero_item", name="uq_item_nota"),
    )
    op.create_index("ix_itens_tenant_id", "nota_itens", ["tenant_id"])
    op.create_index("ix_itens_nota_id", "nota_itens", ["nota_id"])

    # ── nota_eventos ────────────────────────────────────────────────────────
    op.create_table(
        "nota_eventos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nota_id", sa.Uuid(), sa.ForeignKey("notas.id", ondelete="CASCADE")),
        sa.Column("chave_acesso", sa.String(60), nullable=False),
        sa.Column("tipo_evento", sa.String(30), nullable=False),
        sa.Column("protocolo", sa.String(60)),
        sa.Column("data_evento", sa.String(40)),
        sa.Column("justificativa", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("ix_eventos_tenant_id", "nota_eventos", ["tenant_id"])
    op.create_index("ix_eventos_empresa_id", "nota_eventos", ["empresa_id"])
    op.create_index("ix_eventos_chave", "nota_eventos", ["chave_acesso"])

    # ── quebra_ciencia ──────────────────────────────────────────────────────
    op.create_table(
        "quebra_ciencia",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("modelo", sa.String(10), nullable=False),
        sa.Column("serie", sa.String(10), nullable=False),
        sa.Column("num_inicio", sa.Integer(), nullable=False),
        sa.Column("num_fim", sa.Integer(), nullable=False),
        sa.Column("classificacao", sa.String(30), nullable=False),
        sa.Column("justificativa", sa.String(500)),
        sa.Column("ciente_nome", sa.String(200)),
        sa.Column("registrado_por", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "tenant_id", "empresa_id", "modelo", "serie", "num_inicio", "num_fim",
            name="uq_quebra_faixa",
        ),
    )
    op.create_index("ix_quebra_tenant_id", "quebra_ciencia", ["tenant_id"])
    op.create_index("ix_quebra_empresa_id", "quebra_ciencia", ["empresa_id"])

    # ── relatorio_modelos ───────────────────────────────────────────────────
    op.create_table(
        "relatorio_modelos",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("empresa_id", sa.Uuid(), sa.ForeignKey("empresas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(120), nullable=False),
        sa.Column("fluxo", sa.String(10), nullable=False),
        sa.Column("config_json", JSONB(), nullable=False),
        sa.Column("created_by", sa.Uuid()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "empresa_id", "nome", "fluxo", name="uq_modelo_nome_fluxo"),
    )
    op.create_index("ix_modelos_tenant_id", "relatorio_modelos", ["tenant_id"])
    op.create_index("ix_modelos_empresa_id", "relatorio_modelos", ["empresa_id"])

    # ── RLS em todas ────────────────────────────────────────────────────────
    for t in (
        "empresas",
        "processing_jobs",
        "notas",
        "nota_itens",
        "nota_eventos",
        "quebra_ciencia",
        "relatorio_modelos",
    ):
        _rls(t)

    # ── Grants p/ a role do app (redundante c/ default privileges; explícito) ─
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO nexos_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    for t in (
        "relatorio_modelos",
        "quebra_ciencia",
        "nota_eventos",
        "nota_itens",
        "notas",
        "processing_jobs",
        "empresas",
    ):
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation ON {t}")
        op.drop_table(t)
