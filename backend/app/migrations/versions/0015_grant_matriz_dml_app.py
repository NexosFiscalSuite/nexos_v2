"""Concede DML (INSERT/UPDATE/DELETE) nas matrizes ao role nexos_app — habilita
o CRUD de Matrizes Fiscais pela UI (antes só havia SELECT, da 0012).

Revision ID: 0015_grant_matriz_dml_app
Revises: 0014_cadastro_endereco_cnae
Create Date: 2026-06-25
"""
from collections.abc import Sequence

from alembic import op

revision: str = "0015_grant_matriz_dml_app"
down_revision: str | None = "0014_cadastro_endereco_cnae"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE t text;
        BEGIN
            IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'nexos_app') THEN
                FOREACH t IN ARRAY ARRAY['matriz_mva','matriz_enquadramento_st',
                                         'matriz_protocolo_st','matriz_fcp'] LOOP
                    EXECUTE format('GRANT INSERT, UPDATE, DELETE ON %I TO nexos_app', t);
                END LOOP;
                -- PK inteiro das matrizes usa sequence: nexos_app precisa usá-la no INSERT.
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO nexos_app;
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
                    EXECUTE format('REVOKE INSERT, UPDATE, DELETE ON %I FROM nexos_app', t);
                END LOOP;
            END IF;
        END
        $$;
        """
    )
