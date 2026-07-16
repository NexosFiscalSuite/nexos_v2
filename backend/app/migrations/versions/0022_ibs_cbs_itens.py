"""Campos de IBS/CBS por item (Reforma Tributária — destaque do ano-teste 2026).

A NF-e/NFC-e ganhou o grupo <IBSCBS> (NT 2025.002): em 2026 o destaque de
IBS 0,1% + CBS 0,9% é obrigatório para o regime normal (ADCT art. 125,
EC 132/2023), sem recolhimento. Guardamos o que veio no XML para o módulo de
verificação apontar quem está sem destaque ou com alíquota errada.

Revision ID: 0022_ibs_cbs_itens
Revises: 0021_matriz_aliquota
Create Date: 2026-07-09
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022_ibs_cbs_itens"
down_revision: str | None = "0021_matriz_aliquota"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PCT = sa.Numeric(5, 2)
_MONEY = sa.Numeric(15, 2)

_COLUNAS = (
    ("cst_ibs_cbs", sa.String(3), None),
    ("v_bc_ibs_cbs", _MONEY, "0"),
    ("p_ibs_uf", _PCT, "0"),
    ("v_ibs_uf", _MONEY, "0"),
    ("p_ibs_mun", _PCT, "0"),
    ("v_ibs_mun", _MONEY, "0"),
    ("p_cbs", _PCT, "0"),
    ("v_cbs", _MONEY, "0"),
)


def upgrade() -> None:
    for nome, tipo, default in _COLUNAS:
        op.add_column(
            "nota_itens",
            sa.Column(nome, tipo, nullable=True, server_default=default),
        )


def downgrade() -> None:
    for nome, _, _ in reversed(_COLUNAS):
        op.drop_column("nota_itens", nome)
