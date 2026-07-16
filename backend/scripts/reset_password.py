"""Recuperação de acesso por CLI — reset de senha e/ou troca de e-mail do usuário.

Uso (no servidor, a partir de backend/):
    # só redefinir a senha:
    docker compose -f docker-compose.prod.yml exec api python scripts/reset_password.py email@atual

    # redefinir a senha E trocar o e-mail:
    docker compose -f docker-compose.prod.yml exec api python scripts/reset_password.py email@atual novo@email

Roda com a role PRIVILEGIADA (BYPASSRLS) — a mesma do login/signup, pois a
recuperação acontece antes de existir sessão. A senha é pedida em prompt
oculto (getpass): não aparece na tela nem fica no histórico do shell.

⚠️ Se o e-mail trocado for de um CURADOR de matrizes, atualize também
NEXOS_MATRIZ_CURADORES no .env e recarregue api/worker.
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
    if len(sys.argv) not in (2, 3):
        print("Uso: python scripts/reset_password.py <email_atual> [novo_email]")
        return 2
    email = sys.argv[1].strip().lower()
    novo_email = sys.argv[2].strip().lower() if len(sys.argv) == 3 else None
    if novo_email and "@" not in novo_email:
        print(f"Novo e-mail inválido: {novo_email!r}. Nada alterado.")
        return 1

    senha = getpass(f"Nova senha para {novo_email or email} (mín. 8 caracteres): ")
    if len(senha) < 8:
        print("Senha muito curta (mínimo 8 caracteres). Nada alterado.")
        return 1
    if getpass("Confirme a nova senha: ") != senha:
        print("As senhas não conferem. Nada alterado.")
        return 1

    async with privileged_engine.begin() as conn:
        if novo_email:
            em_uso = await conn.scalar(
                text("SELECT count(*) FROM users WHERE email = :n"), {"n": novo_email}
            )
            if em_uso:
                print(f"O e-mail {novo_email!r} já está em uso. Nada alterado.")
                return 1
        resultado = await conn.execute(
            text(
                "UPDATE users SET password_hash = :h, is_active = true"
                + (", email = :n" if novo_email else "")
                + " WHERE email = :e"
            ),
            {"h": hash_password(senha), "e": email, **({"n": novo_email} if novo_email else {})},
        )
    await privileged_engine.dispose()

    if resultado.rowcount == 0:
        print(f"Nenhum usuário com o e-mail {email!r}. Nada alterado.")
        return 1
    print(f"✅ {resultado.rowcount} usuário(s) atualizado(s).")
    if novo_email:
        print(f"   E-mail: {email} → {novo_email}")
        print("   ⚠️ Se era curador de matrizes, atualize NEXOS_MATRIZ_CURADORES no .env.")
    print("   Senha redefinida (e usuário reativado, caso estivesse inativo).")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
