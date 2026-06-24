"""Seed da DEMO ponta a ponta no Postgres: escritório (tenant) + login + empresa
+ NF-e de autopeça com CT-e separado, rodando o motor de ST para gerar as
divergências reais. Idempotente (recria a demo a cada execução).

Roda sob a role PRIVILEGIADA (BYPASSRLS) para semear entre tenants.

Uso:  ./.venv/Scripts/python.exe scripts/seed_demo.py
"""
from __future__ import annotations

import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import delete, select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.modules.companies.infrastructure.models import Empresa  # noqa: E402
from app.modules.fiscal.application.st_audit_service import StAuditService  # noqa: E402
from app.modules.fiscal.infrastructure.models import (  # noqa: E402
    NfeCteVinculo,
    Nota,
    NotaItem,
)
from app.modules.identity.infrastructure.models import Plan, Tenant, User  # noqa: E402
from scripts.seed_matrizes import aplicar_seed  # noqa: E402

EMAIL = "analista@demo.fiscal"
SENHA = "demo12345"
SLUG = "demo"
CHAVE_NFE = "1" * 44


def _item(tenant_id, nota_id, n: int) -> NotaItem:
    # Autopeça CST 10 com ST ZERADO no XML (erro de emissão) → motor recalcula.
    return NotaItem(
        id=uuid4(), tenant_id=tenant_id, nota_id=nota_id, numero_item=n,
        ncm="87082919", cest="0107500", cfop="6404", orig="0", cst="10", mod_bc_st=4,
        quantidade=Decimal("1"), valor_produto=Decimal("731.35"),
        base_calculo=Decimal("731.35"), valor_icms=Decimal("87.76"), p_icms=Decimal("12"),
        p_mva_st=Decimal("71.78"), p_icms_st=Decimal("18.00"),
        v_bc_st=Decimal("0"), valor_icms_st=Decimal("0"),
    )


async def main() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_privileged_url)
    async with async_sessionmaker(engine)() as s, s.begin():
        # idempotência: apaga a demo anterior (cascateia tudo tenant-scoped).
        await s.execute(delete(Tenant).where(Tenant.slug == SLUG))
        await s.flush()

        plan_id = await s.scalar(select(Plan.id).limit(1))
        tenant = Tenant(
            id=uuid4(), cnpj="00000000000191", razao_social="Escritório Demo Contábil",
            slug=SLUG, plan_id=plan_id, status="active",
        )
        s.add(tenant)
        await s.flush()

        s.add(User(
            id=uuid4(), tenant_id=tenant.id, email=EMAIL, full_name="Analista Fiscal",
            password_hash=hash_password(SENHA), role="admin",
        ))
        empresa = Empresa(
            id=uuid4(), tenant_id=tenant.id, cnpj="22222222000122",
            razao_social="AUTOPECAS BRASIL LTDA", uf="MG", regime="Normal",
        )
        s.add(empresa)
        await s.flush()

        await aplicar_seed(s)   # matrizes globais (MVA 71,78% da autopeça etc.)

        nota = Nota(
            id=uuid4(), tenant_id=tenant.id, empresa_id=empresa.id, chave_acesso=CHAVE_NFE,
            tipo="NFe", fluxo="entrada", modelo="55", numero="1042",
            uf_emit="SP", uf_dest="MG", crt_emit="3", data_emissao="2026-06-01",
            nome_emit="AUTOPECAS BRASIL LTDA", cnpj_emit="11111111000111",
            ano="2026", mes="06", valor_total=Decimal("1462.70"),
        )
        s.add(nota)
        s.add(_item(tenant.id, nota.id, 1))
        s.add(_item(tenant.id, nota.id, 2))
        s.add(NfeCteVinculo(
            id=uuid4(), tenant_id=tenant.id, empresa_id=empresa.id,
            chave_nfe=CHAVE_NFE, chave_cte="3" * 44, vtprest=Decimal("136.10"), tp_cte="0",
        ))
        await s.flush()

        registros = await StAuditService(s).auditar_nota(empresa.id, nota.id)
        divergentes = sum(1 for r in registros if r.status == "DIVERGENTE")

    await engine.dispose()
    print("=" * 60)
    print(f"  Demo pronta: {divergentes} divergência(s) de ST geradas.")
    print(f"  LOGIN  -> e-mail: {EMAIL}")
    print(f"            senha : {SENHA}")
    print(f"            escritório (slug): {SLUG}")
    print("  Empresa: AUTOPECAS BRASIL LTDA · competência 06/2026")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
