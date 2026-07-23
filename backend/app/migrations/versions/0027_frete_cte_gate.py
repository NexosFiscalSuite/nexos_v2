"""Gate do frete/CT-e no motor de ST.

modFrete do XML (quem paga o frete) + confirmação explícita de que NÃO há
CT-e para a nota (com autor e data — trilha de auditoria). Nota FOB de
entrada (ou CIF de saída) sem CT-e vinculado e sem frete nos itens deixa de
calcular base a menor em silêncio: vira pendência reprocessável até importar
o CT-e ou confirmar a ausência.

Revision ID: 0027_frete_cte_gate
Revises: 0026_st_retido
Create Date: 2026-07-23
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0027_frete_cte_gate"
down_revision: str | None = "0026_st_retido"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("notas", sa.Column("mod_frete", sa.String(1), nullable=True))
    op.add_column("notas", sa.Column(
        "frete_sem_cte_confirmado", sa.Boolean(), nullable=False, server_default=sa.false()
    ))
    op.add_column("notas", sa.Column("frete_confirmado_por", sa.String(160), nullable=True))
    op.add_column("notas", sa.Column(
        "frete_confirmado_em", sa.DateTime(timezone=True), nullable=True
    ))


def downgrade() -> None:
    op.drop_column("notas", "frete_confirmado_em")
    op.drop_column("notas", "frete_confirmado_por")
    op.drop_column("notas", "frete_sem_cte_confirmado")
    op.drop_column("notas", "mod_frete")
