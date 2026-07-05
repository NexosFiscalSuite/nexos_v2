"""Matriz de alíquotas modais do ICMS por UF (com FCP integrado), com vigência.

Tira do código (aliquotas.py) a tabela que muda por lei estadual: auditar exige
a alíquota VIGENTE NA EMISSÃO (ADR-0002), e a tabela fixa aplicava a taxa atual
a qualquer data (ex.: AL 20,5% em notas anteriores a 01/04/2026 — Lei 9.776/2025).

Tabela GLOBAL (sem tenant_id / sem RLS), como as demais matrizes (0009).
Grants de SELECT+DML ao nexos_app seguem 0012/0015.

Revision ID: 0021_matriz_aliquota
Revises: 0020_force_rls
Create Date: 2026-07-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0021_matriz_aliquota"
down_revision: str | None = "0020_force_rls"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PCT = sa.Numeric(5, 2)


def upgrade() -> None:
    op.create_table(
        "matriz_aliquota",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uf_destino", sa.String(2), nullable=False),
        sa.Column("aliq_modal", _PCT, nullable=False),
        sa.Column("aliq_fcp_integrado", _PCT, nullable=False, server_default="0"),
        sa.Column("base_legal", sa.String(120)),
        sa.Column("data_inicio_vigencia", sa.Date(), nullable=False),
        sa.Column("data_fim_vigencia", sa.Date(), nullable=True),
        sa.UniqueConstraint("uf_destino", "data_inicio_vigencia", name="uq_aliquota_vigencia"),
    )
    op.create_index("ix_aliquota_busca", "matriz_aliquota", ["uf_destino"])

    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON matriz_aliquota TO nexos_app;
                -- Sequence do PK criada depois do grant genérico da 0015.
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nexos_app;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_table("matriz_aliquota")
