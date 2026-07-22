"""ST retido anteriormente por item (CST 60 / CSOSN 500).

vBCSTRet, pST, vICMSSTRet, vICMSSubstituto e vFCPSTRet do XML — a entrada com
ST retido deixa de travar no motor (vira OK com o retido registrado) e esses
campos são o insumo de toda a trilha de ressarcimento/complemento (fundação
entrada→saída do roadmap do motor de ST).

Revision ID: 0026_st_retido
Revises: 0025_ibscbs_gred
Create Date: 2026-07-22
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_st_retido"
down_revision: str | None = "0025_ibscbs_gred"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COLUNAS = (
    ("v_bc_st_ret", sa.Numeric(15, 2)),
    ("p_st_ret", sa.Numeric(5, 2)),
    ("v_icms_st_ret", sa.Numeric(15, 2)),
    ("v_icms_substituto", sa.Numeric(15, 2)),
    ("v_fcp_st_ret", sa.Numeric(15, 2)),
)


def upgrade() -> None:
    for nome, tipo in _COLUNAS:
        op.add_column(
            "nota_itens",
            sa.Column(nome, tipo, nullable=False, server_default="0"),
        )


def downgrade() -> None:
    for nome, _tipo in reversed(_COLUNAS):
        op.drop_column("nota_itens", nome)
