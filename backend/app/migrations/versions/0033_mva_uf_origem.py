"""MVA passa a ter UF de origem (par origem→destino).

A MVA varia com o estado remetente (acordo aplicável) e a interna difere da
interestadual. As linhas já cadastradas viram curinga "*" (valem para qualquer
origem), preservando exatamente o comportamento atual até a curadoria abrir os
pares específicos.

Revision ID: 0033_mva_uf_origem
Revises: 0032_excecao_st_produto
Create Date: 2026-08-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0033_mva_uf_origem"
down_revision: str | None = "0032_excecao_st_produto"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default "*" preenche o legado na própria criação da coluna.
    op.add_column(
        "matriz_mva",
        sa.Column("uf_origem", sa.String(2), nullable=False, server_default="*"),
    )
    op.drop_constraint("uq_mva_vigencia", "matriz_mva", type_="unique")
    op.create_unique_constraint(
        "uq_mva_vigencia",
        "matriz_mva",
        ["ncm", "cest", "uf_origem", "uf_destino", "data_inicio_vigencia"],
    )
    op.drop_index("ix_mva_busca", table_name="matriz_mva")
    op.create_index(
        "ix_mva_busca", "matriz_mva", ["uf_destino", "uf_origem", "ncm", "cest"]
    )


def downgrade() -> None:
    op.drop_index("ix_mva_busca", table_name="matriz_mva")
    op.create_index("ix_mva_busca", "matriz_mva", ["uf_destino", "ncm", "cest"])
    op.drop_constraint("uq_mva_vigencia", "matriz_mva", type_="unique")
    # Linhas por origem específica colidiriam na chave antiga — só o curinga volta.
    op.execute("DELETE FROM matriz_mva WHERE uf_origem <> '*'")
    op.create_unique_constraint(
        "uq_mva_vigencia",
        "matriz_mva",
        ["ncm", "cest", "uf_destino", "data_inicio_vigencia"],
    )
    op.drop_column("matriz_mva", "uf_origem")
