"""Prova de isolamento RLS contra um Postgres REAL (a garantia central do produto).

Usa a MESMA role do app (`nexos_app`, sujeita a RLS + FORCE) e o mesmo
`set_config('app.current_tenant', ..., true)` do runtime. Pula automaticamente
se o Postgres do dev não estiver de pé (`docker compose up -d postgres`) ou
sem migrações — nesses ambientes o restante da suíte segue normal.

O que fica provado:
  1. Tenant A não lê dados do tenant B (USING).
  2. Sem contexto de tenant, NENHUMA linha aparece (fail-closed).
  3. INSERT com tenant_id alheio é recusado pelo banco (WITH CHECK).
  4. UPDATE cross-tenant não afeta linha alguma.
"""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

_SET_TENANT = text("SELECT set_config('app.current_tenant', :tid, true)")


@pytest_asyncio.fixture
async def rls_env():
    settings = get_settings()
    priv = create_async_engine(settings.database_privileged_url, poolclass=NullPool)
    try:
        async with priv.connect() as c:
            rls_on = await c.scalar(
                text("SELECT relrowsecurity FROM pg_class WHERE relname = 'empresas'")
            )
    except Exception:
        await priv.dispose()
        pytest.skip("Postgres indisponível — suba com: docker compose up -d postgres")
    if not rls_on:
        await priv.dispose()
        pytest.skip("Banco sem RLS em `empresas` — rode: alembic upgrade head")

    app_eng = create_async_engine(settings.database_url, poolclass=NullPool)
    ids = {
        "plan": uuid4(), "tenant_a": uuid4(), "tenant_b": uuid4(),
        "empresa_a": uuid4(), "empresa_b": uuid4(),
    }
    sufixo = str(ids["plan"])[:8]
    async with priv.begin() as c:
        await c.execute(text(
            "INSERT INTO plans (id, code, name, rate_limit_per_min, max_empresas,"
            " max_users, price_cents, is_active)"
            " VALUES (:id, :code, 'RLS Test', 120, 5, 3, 0, true)"
        ), {"id": ids["plan"], "code": f"rlstest-{sufixo}"})
        for chave, cnpj, slug in (
            ("tenant_a", f"90{sufixo.replace('-', '')[:6]}000101", f"rls-a-{sufixo}"),
            ("tenant_b", f"91{sufixo.replace('-', '')[:6]}000102", f"rls-b-{sufixo}"),
        ):
            await c.execute(text(
                "INSERT INTO tenants (id, cnpj, razao_social, slug, plan_id, status)"
                " VALUES (:id, :cnpj, 'Escritório RLS Test', :slug, :plan, 'trial')"
            ), {"id": ids[chave], "cnpj": cnpj, "slug": slug, "plan": ids["plan"]})
        await c.execute(text(
            "INSERT INTO empresas (id, tenant_id, cnpj, razao_social)"
            " VALUES (:ea, :ta, '11111111000191', 'Empresa do Tenant A'),"
            "        (:eb, :tb, '22222222000191', 'Empresa do Tenant B')"
        ), {"ea": ids["empresa_a"], "ta": ids["tenant_a"],
            "eb": ids["empresa_b"], "tb": ids["tenant_b"]})

    yield app_eng, ids

    async with priv.begin() as c:
        await c.execute(text("DELETE FROM empresas WHERE tenant_id IN (:a, :b)"),
                        {"a": ids["tenant_a"], "b": ids["tenant_b"]})
        await c.execute(text("DELETE FROM tenants WHERE id IN (:a, :b)"),
                        {"a": ids["tenant_a"], "b": ids["tenant_b"]})
        await c.execute(text("DELETE FROM plans WHERE id = :p"), {"p": ids["plan"]})
    await priv.dispose()
    await app_eng.dispose()


async def _ids_visiveis(app_eng, ids, tenant) -> set:
    """SELECT como o app: contexto do tenant setado na transação (como rls.py)."""
    async with app_eng.connect() as c, c.begin():
        if tenant is not None:
            await c.execute(_SET_TENANT, {"tid": str(ids[tenant])})
        rows = await c.execute(
            text("SELECT id FROM empresas WHERE id IN (:ea, :eb)"),
            {"ea": ids["empresa_a"], "eb": ids["empresa_b"]},
        )
        return {r[0] for r in rows}


async def test_tenant_nao_le_dados_de_outro(rls_env):
    app_eng, ids = rls_env
    assert await _ids_visiveis(app_eng, ids, "tenant_a") == {ids["empresa_a"]}
    assert await _ids_visiveis(app_eng, ids, "tenant_b") == {ids["empresa_b"]}


async def test_sem_contexto_nenhuma_linha_aparece(rls_env):
    """Fail-closed: esquecer o set_config não vaza dados — zera o resultado."""
    app_eng, ids = rls_env
    assert await _ids_visiveis(app_eng, ids, None) == set()


async def test_insert_com_tenant_alheio_e_recusado(rls_env):
    """WITH CHECK: mesmo autenticado como A, gravar linha do B é erro do BANCO."""
    app_eng, ids = rls_env
    with pytest.raises(DBAPIError, match="row-level security"):
        async with app_eng.connect() as c, c.begin():
            await c.execute(_SET_TENANT, {"tid": str(ids["tenant_a"])})
            await c.execute(text(
                "INSERT INTO empresas (id, tenant_id, cnpj, razao_social)"
                " VALUES (:id, :tb, '33333333000191', 'Invasora')"
            ), {"id": uuid4(), "tb": ids["tenant_b"]})


async def test_update_cross_tenant_nao_afeta_linhas(rls_env):
    app_eng, ids = rls_env
    async with app_eng.connect() as c, c.begin():
        await c.execute(_SET_TENANT, {"tid": str(ids["tenant_a"])})
        resultado = await c.execute(
            text("UPDATE empresas SET razao_social = 'hackeada' WHERE id = :eb"),
            {"eb": ids["empresa_b"]},
        )
        assert resultado.rowcount == 0   # USING filtra antes do UPDATE

    # E a linha do B segue intacta (visão do próprio B).
    async with app_eng.connect() as c, c.begin():
        await c.execute(_SET_TENANT, {"tid": str(ids["tenant_b"])})
        nome = await c.scalar(
            text("SELECT razao_social FROM empresas WHERE id = :eb"),
            {"eb": ids["empresa_b"]},
        )
        assert nome == "Empresa do Tenant B"
