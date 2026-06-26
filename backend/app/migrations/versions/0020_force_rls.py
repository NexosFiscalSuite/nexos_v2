"""Defense-in-depth: FORCE ROW LEVEL SECURITY em todas as tabelas tenant-scoped.

Sem FORCE, a RLS é ignorada para o OWNER da tabela. Hoje estamos protegidos só
porque a role do app (nexos_app) não é owner — mas isso é uma garantia frágil:
basta apontar o DATABASE_URL para a role privilegiada por engano, ou a role do
app virar owner, para a RLS parar de aplicar SILENCIOSAMENTE. FORCE remove essa
dependência: a policy passa a valer até para o owner (exceto superuser, que é
intencional para migração/auth).

Tabelas GLOBAIS (matrizes fiscais e cfop_regras) ficam de fora de propósito —
não têm tenant_id nem RLS (dado de referência, ver 0009 e 0017).

Revision ID: 0020_force_rls
Revises: 0019_modelo_sistema
Create Date: 2026-06-26
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0020_force_rls"
down_revision: str | None = "0019_modelo_sistema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS = (
    "tenants",
    "users",
    "refresh_tokens",
    "empresas",
    "processing_jobs",
    "notas",
    "nota_itens",
    "nota_eventos",
    "quebra_ciencia",
    "relatorio_modelos",
    "grupos",
    "grupo_membros",
    "empresa_grupo",
    "audit_log",
    "contrapartes",
    "nfe_cte_vinculo",
    "auditoria_icms_st",
)


def upgrade() -> None:
    for t in _TABELAS:
        op.execute(f"ALTER TABLE {t} FORCE ROW LEVEL SECURITY")


def downgrade() -> None:
    for t in _TABELAS:
        op.execute(f"ALTER TABLE {t} NO FORCE ROW LEVEL SECURITY")
