"""Alíquota por NCM e redução de base pela matriz.

Duas lacunas da mesma família da MVA: a alíquota interna era só da UF (produto
de cesta básica calculava a 18% em MG) e a redução de base vinha exclusivamente
do XML do fornecedor — o motor repetia a conta dele.

As linhas existentes viram `ncm = 'GERAL'` (a regra do estado, exatamente o que
elas já eram) com `p_red_bc_st = 0`, então nada muda até a curadoria cadastrar
a primeira exceção por produto.

Revision ID: 0035_aliquota_por_ncm
Revises: 0034_excecao_fornecedor
Create Date: 2026-08-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0035_aliquota_por_ncm"
down_revision: str | None = "0034_excecao_fornecedor"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "matriz_aliquota"
_UQ = "uq_aliquota_vigencia"


def upgrade() -> None:
    op.add_column(
        _TABELA,
        sa.Column("ncm", sa.String(8), nullable=False, server_default="GERAL"),
    )
    op.add_column(
        _TABELA,
        sa.Column("p_red_bc_st", sa.Numeric(5, 2), nullable=False, server_default="0"),
    )
    op.drop_constraint(_UQ, _TABELA, type_="unique")
    op.create_unique_constraint(
        _UQ, _TABELA, ["uf_destino", "ncm", "data_inicio_vigencia"]
    )
    op.drop_index("ix_aliquota_busca", table_name=_TABELA)
    op.create_index("ix_aliquota_busca", _TABELA, ["uf_destino", "ncm"])


def downgrade() -> None:
    op.drop_index("ix_aliquota_busca", table_name=_TABELA)
    op.create_index("ix_aliquota_busca", _TABELA, ["uf_destino"])
    op.drop_constraint(_UQ, _TABELA, type_="unique")
    # Linhas por NCM específico colidiriam na chave antiga — só a regra do
    # estado sobrevive ao rollback.
    op.execute(f"DELETE FROM {_TABELA} WHERE ncm <> 'GERAL'")
    op.create_unique_constraint(_UQ, _TABELA, ["uf_destino", "data_inicio_vigencia"])
    op.drop_column(_TABELA, "p_red_bc_st")
    op.drop_column(_TABELA, "ncm")
