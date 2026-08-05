"""Carimbo de última verificação nas 5 matrizes fiscais (Fase 2 da automação).

`ultima_verificacao_em` diz quando um humano confirmou a linha pela última
vez (cadastro, edição, import ou aprovação de proposta). Alimenta o aviso de
legislação vigente da carta ("base atualizada em DD/MM/AAAA") e o futuro
radar de saúde das matrizes. Backfill honesto: linhas existentes valem como
verificadas quando foram cadastradas (created_at).

Revision ID: 0030_ultima_verificacao_matrizes
Revises: 0029_fila_propostas_matrizes
Create Date: 2026-08-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030_ultima_verificacao_matrizes"
down_revision: str | None = "0029_fila_propostas_matrizes"
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
        op.add_column(tabela, sa.Column(
            "ultima_verificacao_em", sa.DateTime(timezone=True),
            server_default=sa.func.now(), nullable=False,
        ))
        op.execute(f"UPDATE {tabela} SET ultima_verificacao_em = created_at")


def downgrade() -> None:
    for tabela in _TABELAS:
        op.drop_column(tabela, "ultima_verificacao_em")
