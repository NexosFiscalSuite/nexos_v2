"""Reset de senha por linha de comando — runbook de emergência ("esqueci o admin").

Uso (no servidor, a partir de backend/):
    docker compose -f docker-compose.prod.yml exec api python scripts/reset_password.py email@dominio

Roda com a role PRIVILEGIADA (BYPASSRLS) — a mesma do login/signup, pois o
reset acontece antes de existir sessão. A senha é pedida em prompt oculto
(getpass): não aparece na tela nem fica no histórico do shell.
"""
from __future__ import annotations

import asyncio
import sys
from getpass import getpass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.database import privileged_engine  # noqa: E402
from app.core.security import hash_password  # noqa: E402


async def _main() -> int:
    if len(sys.argv) != 2:
        print("Uso: python scripts/reset_password.py <email>")
        return 2
    email = sys.argv[1].strip().lower()

    senha = getpass(f"Nova senha para {email} (mín. 8 caracteres): ")
    if len(senha) < 8:
        print("Senha muito curta (mínimo 8 caracteres). Nada alterado.")
        return 1
    if getpass("Confirme a nova senha: ") != senha:
        print("As senhas não conferem. Nada alterado.")
        return 1

    async with privileged_engine.begin() as conn:
        resultado = await conn.execute(
            text("UPDATE users SET password_hash = :h, is_active = true WHERE email = :e"),
            {"h": hash_password(senha), "e": email},
        )
    await privileged_engine.dispose()

    if resultado.rowcount == 0:
        print(f"Nenhum usuário com o e-mail {email!r}. Nada alterado.")
        return 1
    print(f"✅ Senha redefinida para {resultado.rowcount} usuário(s) com o e-mail {email!r}.")
    print("   (Usuário também foi reativado, caso estivesse inativo.)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
