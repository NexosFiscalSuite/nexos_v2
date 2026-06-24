"""Engines e sessions async.

Duas conexões distintas, por desenho de segurança:

* ``engine`` / ``SessionLocal``      -> role do app (nexos_app), SUJEITA a RLS.
    Tudo no runtime normal da API passa por aqui, sempre com o tenant injetado
    na transação (ver app/core/rls.py).

* ``privileged_engine`` / ``PrivilegedSessionLocal`` -> role com BYPASSRLS.
    Usado SÓ por operações inerentemente cross-tenant: signup (criar tenant) e
    login (achar usuário por e-mail antes de existir contexto). Mantém o
    "blast radius" do bypass minúsculo e auditável.
"""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    """Base declarativa de todos os modelos ORM."""


# ensure_ascii=False: sem isto, gravar dict->JSONB via asyncpg corrompe acentos
# (UTF-8 lido como latin-1: "ã" vira "Ã£"). Serializador compartilhado por todas
# as engines (ver também app/core/worker_db.py).
def json_serializer(obj):
    import json
    return json.dumps(obj, ensure_ascii=False)


engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_pre_ping=True,
    json_serializer=json_serializer,
)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

privileged_engine = create_async_engine(
    settings.database_privileged_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    json_serializer=json_serializer,
)
PrivilegedSessionLocal = async_sessionmaker(
    privileged_engine, class_=AsyncSession, expire_on_commit=False
)


async def privileged_session() -> AsyncIterator[AsyncSession]:
    """Session com BYPASSRLS. Use apenas em auth/signup."""
    async with PrivilegedSessionLocal() as session:
        yield session
