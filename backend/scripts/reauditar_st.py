"""Reaudita o ICMS-ST de todas as NF-e/NFC-e já importadas (idempotente).

Útil após mudanças no motor/matrizes (ex.: cadastrar uma MVA nova) para
recalcular sem reimportar. Roda sob a role privilegiada (BYPASSRLS).

Uso:  ./.venv/Scripts/python.exe scripts/reauditar_st.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

import app.core.celery_app  # noqa: E402, F401 — registra TODOS os models (FKs)
from app.core.config import get_settings  # noqa: E402
from app.modules.fiscal.application.st_audit_service import StAuditService  # noqa: E402
from app.modules.fiscal.infrastructure.models import Nota  # noqa: E402


async def main() -> None:
    engine = create_async_engine(get_settings().database_privileged_url)
    async with async_sessionmaker(engine)() as s, s.begin():
        rows = (
            await s.execute(
                select(Nota.id, Nota.empresa_id).where(Nota.tipo.in_(["NFe", "NFCe"]))
            )
        ).all()
        svc = StAuditService(s)
        for nota_id, empresa_id in rows:
            await svc.auditar_nota(empresa_id, nota_id)
    await engine.dispose()
    print(f"Reauditadas {len(rows)} nota(s) NF-e/NFC-e.")


if __name__ == "__main__":
    asyncio.run(main())
