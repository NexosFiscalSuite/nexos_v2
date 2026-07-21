"""gRed do IBS/CBS por item: pRedAliq e pAliqEfet de cada perna (UF/Mun/CBS).

Pela NT 2025.002, item com redução (ex.: cClassTrib 200003, alimentos −100%)
traz a alíquota NOMINAL de teste em pIBSUF/pCBS (obrigatória — Rejeição 1026)
e a carga real em pAliqEfet. Sem estes campos o verificador comparava a nominal
com a régua efetiva e apontava "alíquota errada" em nota correta (caso Alto
Cafezal, jul/2026). NULL = grupo ausente no XML (≠ de zerado).

Revision ID: 0025_ibscbs_gred
Revises: 0024_cclasstrib_item
Create Date: 2026-07-21
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025_ibscbs_gred"
down_revision: str | None = "0024_cclasstrib_item"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUNAS = (
    "p_red_aliq_ibs_uf",
    "p_aliq_efet_ibs_uf",
    "p_red_aliq_ibs_mun",
    "p_aliq_efet_ibs_mun",
    "p_red_aliq_cbs",
    "p_aliq_efet_cbs",
)


def upgrade() -> None:
    for col in _COLUNAS:
        op.add_column("nota_itens", sa.Column(col, sa.Numeric(5, 2), nullable=True))


def downgrade() -> None:
    for col in reversed(_COLUNAS):
        op.drop_column("nota_itens", col)
