"""Sessão tenant-aware: injeta o tenant na transação para o RLS atuar.

Fluxo por request:
  1. `get_current_claims` valida o JWT e devolve tenant_id.
  2. Abrimos UMA transação e executamos `set_config('app.current_tenant', tid, true)`.
     - `set_config(..., is_local => true)` == `SET LOCAL`: vale só nesta transação,
       então é seguro com pooling (pgbouncer transaction mode).
     - é parametrizado -> imune a SQL injection (diferente de `SET ... = '...'`).
  3. A partir daí TODA query roda já filtrada pelo Postgres. Esquecer um
     `WHERE tenant_id` deixa de ser vazamento: o banco recusa as linhas.

As policies usam `current_setting('app.current_tenant', true)` (missing_ok=true):
se o contexto não foi setado, retorna NULL -> nenhuma linha casa -> fail-closed.
"""
from collections.abc import AsyncIterator

from fastapi import Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import SessionLocal
from app.core.security import TokenClaims, get_current_claims

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tid, true)")


async def tenant_session(
    claims: TokenClaims = Depends(get_current_claims),
) -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        async with session.begin():
            await session.execute(_SET_TENANT, {"tid": str(claims.tid)})
            yield session
