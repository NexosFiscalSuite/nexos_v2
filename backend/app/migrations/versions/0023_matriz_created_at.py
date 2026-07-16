"""Data de cadastro (created_at) em todas as matrizes fiscais.

Difere da vigência (quando a regra vale no mundo real — ADR-0002): created_at
diz QUANDO a linha entrou no sistema. Linhas pré-existentes recebem o timestamp
da migração (a data real de cadastro delas não é recuperável).

Revision ID: 0023_matriz_created_at
Revises: 0022_ibs_cbs_itens
Create Date: 2026-07-10
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023_matriz_created_at"
down_revision: str | None = "0022_ibs_cbs_itens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS = (
    "matriz_mva",
    "matriz_enquadramento_st",
    "matriz_protocolo_st",
    "matriz_aliquota",
    "matriz_fcp",
)


def upgrade() -> None:
    for tabela in _TABELAS:
        op.add_column(
            tabela,
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
        )


def downgrade() -> None:
    for tabela in reversed(_TABELAS):
        op.drop_column(tabela, "created_at")
