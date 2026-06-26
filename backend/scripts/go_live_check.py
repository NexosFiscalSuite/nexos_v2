"""Verificação única de go-live (fail-fast).

Roda TODAS as checagens de segurança/integridade que precisam estar verdes antes
de subir em produção e imprime um checklist. Sai com código != 0 se algo falhar
(útil em pipeline de deploy).

Uso:
    python -m scripts.go_live_check          # a partir de backend/
    # ou:  make go-live-check

Cobre:
  1. NEXOS_ENVIRONMENT == production
  2. NEXOS_JWT_SECRET forte (não é o default/placeholder, >= 32 chars)
  3. Role de runtime do app SEM superuser/bypassrls (senão a RLS é ignorada)
  4. Migrações no head (inclui 0020_force_rls)
  5. RLS habilitada E forçada (FORCE) em TODAS as tabelas tenant-scoped
"""
import asyncio
import sys

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import engine, privileged_engine
from app.core.preflight import (
    _MIN_SECRET_LEN,
    _SEGREDOS_PROIBIDOS,
    _SENHAS_FRACAS,
    _senha_da_url,
)

# Mantido em sincronia com a migration 0020_force_rls._TABELAS.
_TENANT_TABLES = (
    "tenants", "users", "refresh_tokens", "empresas", "processing_jobs",
    "notas", "nota_itens", "nota_eventos", "quebra_ciencia", "relatorio_modelos",
    "grupos", "grupo_membros", "empresa_grupo", "audit_log", "contrapartes",
    "nfe_cte_vinculo", "auditoria_icms_st",
)

settings = get_settings()
_falhas: list[str] = []


def _check(ok: bool, titulo: str, detalhe: str = "") -> None:
    marca = "✓" if ok else "✗"
    print(f"  [{marca}] {titulo}" + (f" — {detalhe}" if detalhe else ""))
    if not ok:
        _falhas.append(titulo)


def _alembic_head() -> str:
    cfg = Config("alembic.ini")
    return ScriptDirectory.from_config(cfg).get_current_head()


async def main() -> int:
    print("\n🔒 Go-live check — Nexos Fiscal Suite V2\n")

    # 1. Ambiente
    _check(settings.is_production, "Ambiente é produção",
           f"NEXOS_ENVIRONMENT={settings.environment!r}")

    # 2. Segredo JWT
    secret = (settings.jwt_secret or "").strip()
    forte = secret not in _SEGREDOS_PROIBIDOS and len(secret) >= _MIN_SECRET_LEN
    _check(forte, "JWT_SECRET forte",
           f"{len(secret)} chars" if forte else "default/placeholder ou curto")

    # 2b. Segredos de infra (banco + S3) não podem ser default/fracos
    s3_ok = (settings.s3_secret_key or "") not in _SENHAS_FRACAS and len(settings.s3_secret_key or "") >= 8
    db_ok = (
        _senha_da_url(settings.database_url) not in _SENHAS_FRACAS
        and _senha_da_url(settings.database_privileged_url) not in _SENHAS_FRACAS
    )
    _check(s3_ok and db_ok, "Segredos de infra (banco + S3) fortes",
           "ok" if (s3_ok and db_ok) else "há senha default/fraca em banco ou S3")

    # 3. Role de runtime do app (não pode ter superuser/bypassrls)
    async with engine.connect() as conn:
        row = (await conn.execute(text(
            "SELECT current_user, rolsuper, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        ))).first()
    usuario, rolsuper, rolbypass = (row[0], bool(row[1]), bool(row[2])) if row else ("?", True, True)
    _check(not (rolsuper or rolbypass), "Role do app SEM superuser/bypassrls",
           f"current_user={usuario}")

    # 4. Migrações no head (via role privilegiada, que é quem migra)
    head = _alembic_head()
    async with privileged_engine.connect() as conn:
        atual = (await conn.execute(text(
            "SELECT version_num FROM alembic_version"
        ))).scalar()
    _check(atual == head, "Migrações no head",
           f"db={atual} / esperado={head}")

    # 5. RLS habilitada E forçada em todas as tabelas tenant-scoped
    async with privileged_engine.connect() as conn:
        rows = (await conn.execute(text(
            "SELECT relname, relrowsecurity, relforcerowsecurity "
            "FROM pg_class WHERE relname = ANY(:t)"
        ), {"t": list(_TENANT_TABLES)})).all()
    estado = {r[0]: (bool(r[1]), bool(r[2])) for r in rows}
    faltando = [
        t for t in _TENANT_TABLES
        if estado.get(t, (False, False)) != (True, True)
    ]
    _check(not faltando, "RLS habilitada + FORCE em todas as tabelas tenant",
           "ok" if not faltando else f"pendentes: {', '.join(faltando)}")

    await engine.dispose()
    await privileged_engine.dispose()

    print()
    if _falhas:
        print(f"❌ REPROVADO — {len(_falhas)} item(ns): {', '.join(_falhas)}\n")
        return 1
    print("✅ APROVADO — ambiente pronto para produção.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
