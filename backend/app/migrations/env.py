"""Ambiente Alembic (async). Roda com a role PRIVILEGIADA (owner/BYPASSRLS),
nunca com a role do app — migração não pode estar sujeita ao RLS.
"""
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings
from app.core.database import Base
from app.modules.audit.infrastructure import models as _m_audit  # noqa: F401
from app.modules.cfop_rules.infrastructure import models as _m_cfop_rules  # noqa: F401
from app.modules.companies.infrastructure import models as _m_companies  # noqa: F401
from app.modules.compliance.infrastructure import models as _m_compliance  # noqa: F401
from app.modules.contrapartes.infrastructure import models as _m_contrapartes  # noqa: F401
from app.modules.fiscal.infrastructure import matrizes_models as _m_matrizes  # noqa: F401
from app.modules.fiscal.infrastructure import models as _m_fiscal  # noqa: F401
from app.modules.grupos.infrastructure import models as _m_grupos  # noqa: F401

# Importa TODOS os modelos para popular Base.metadata (autogenerate enxergar tudo).
from app.modules.identity.infrastructure import models  # noqa: F401
from app.modules.jobs.infrastructure import models as _m_jobs  # noqa: F401
from app.modules.reporting.infrastructure import models as _m_reporting  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata
settings = get_settings()
DB_URL = settings.database_privileged_url


def run_migrations_offline() -> None:
    context.configure(
        url=DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    engine = create_async_engine(DB_URL, pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(_do_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
