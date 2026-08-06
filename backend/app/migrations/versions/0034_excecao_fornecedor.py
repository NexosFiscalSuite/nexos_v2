"""Exceção de item passa a ter fornecedor.

O cProd é do fornecedor: dois fornecedores usam o MESMO código para produtos
diferentes, e a exceção casava só pelo código — vazava de um para o outro. As
linhas já cadastradas viram "" (qualquer fornecedor), preservando o
comportamento atual até o curador apertar cada uma no fornecedor certo.

Revision ID: 0034_excecao_fornecedor
Revises: 0033_mva_uf_origem
Create Date: 2026-08-06
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0034_excecao_fornecedor"
down_revision: str | None = "0033_mva_uf_origem"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "excecao_enquadramento_st_produto"
_UQ = "uq_excecao_st_empresa_produto_inicio"


def upgrade() -> None:
    # server_default "" preenche o legado na própria criação da coluna.
    op.add_column(
        _TABELA,
        sa.Column("cnpj_fornecedor", sa.String(14), nullable=False, server_default=""),
    )
    op.drop_constraint(_UQ, _TABELA, type_="unique")
    op.create_unique_constraint(
        _UQ, _TABELA,
        ["tenant_id", "empresa_id", "cnpj_fornecedor", "codigo_produto",
         "data_inicio_vigencia"],
    )


def downgrade() -> None:
    op.drop_constraint(_UQ, _TABELA, type_="unique")
    # Regras por fornecedor específico colidiriam na chave antiga — só o
    # genérico sobrevive ao rollback.
    op.execute(f"DELETE FROM {_TABELA} WHERE cnpj_fornecedor <> ''")
    op.create_unique_constraint(
        _UQ, _TABELA,
        ["tenant_id", "empresa_id", "codigo_produto", "data_inicio_vigencia"],
    )
    op.drop_column(_TABELA, "cnpj_fornecedor")
