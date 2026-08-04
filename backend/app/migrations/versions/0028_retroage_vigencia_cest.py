"""Retroage a vigência do enquadramento auto-alimentado (CONFAZ) p/ 01/06/2026.

O primeiro sync do crawler gravou a vigência no 1º do mês corrente
(01/08/2026), mas as notas auditadas são de competências desde jun/2026 —
fail-closed, tudo anterior a agosto travaria "sem enquadramento". Retroage
APENAS as linhas do crawler (base_legal 'auto/CONFAZ'), preservando a
curadoria manual. Guardas: o MIN() move só a linha mais antiga de cada chave
(se o job tiver rodado em mais de um mês) e o NOT EXISTS respeita a unique
(uf, ncm, cest, data_inicio_vigencia) quando já houver linha em 01/06.

Revision ID: 0028_retroage_vigencia_cest
Revises: 0027_frete_cte_gate
Create Date: 2026-08-04
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0028_retroage_vigencia_cest"
down_revision: str | None = "0027_frete_cte_gate"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_BASE_LEGAL_AUTO = "Convênio ICMS 142/2018 (auto/CONFAZ)"


def upgrade() -> None:
    op.execute(f"""
        UPDATE matriz_enquadramento_st m
           SET data_inicio_vigencia = DATE '2026-06-01'
         WHERE m.base_legal = '{_BASE_LEGAL_AUTO}'
           AND m.data_inicio_vigencia > DATE '2026-06-01'
           AND m.data_inicio_vigencia = (
               SELECT MIN(x.data_inicio_vigencia)
                 FROM matriz_enquadramento_st x
                WHERE x.uf_destino = m.uf_destino
                  AND x.ncm = m.ncm AND x.cest = m.cest
                  AND x.base_legal = m.base_legal
                  AND x.data_inicio_vigencia > DATE '2026-06-01'
           )
           AND NOT EXISTS (
               SELECT 1 FROM matriz_enquadramento_st e
                WHERE e.uf_destino = m.uf_destino
                  AND e.ncm = m.ncm AND e.cest = m.cest
                  AND e.data_inicio_vigencia = DATE '2026-06-01'
           )
    """)


def downgrade() -> None:
    # Sem volta: o mês original de cada linha não é rastreado (e o crawler
    # regrava a família 01/06 na próxima rodada de qualquer forma).
    pass
