"""GRANT SELECT nas matrizes globais para a role do app (nexos_app).

As matrizes (0009) são globais (sem RLS), mas o worker lê-as sob a role
nexos_app durante a auditoria de ST. Sem este GRANT, a leitura falha em
produção (a demo não pega isso porque o seed roda sob a role privilegiada).

Revision ID: 0012_grant_matrizes_app
Revises: 0011_auditoria_icms_st
Create Date: 2026-06-24
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0012_grant_matrizes_app"
down_revision: str | None = "0011_auditoria_icms_st"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELAS = ("matriz_mva", "matriz_enquadramento_st", "matriz_protocolo_st", "matriz_fcp")


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                FOREACH t IN ARRAY ARRAY['matriz_mva','matriz_enquadramento_st',
                                         'matriz_protocolo_st','matriz_fcp'] LOOP
                    EXECUTE format('GRANT SELECT ON %I TO nexos_app', t);
                END LOOP;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                FOREACH t IN ARRAY ARRAY['matriz_mva','matriz_enquadramento_st',
                                         'matriz_protocolo_st','matriz_fcp'] LOOP
                    EXECUTE format('REVOKE SELECT ON %I FROM nexos_app', t);
                END LOOP;
            END IF;
        END
        $$;
        """
    )
