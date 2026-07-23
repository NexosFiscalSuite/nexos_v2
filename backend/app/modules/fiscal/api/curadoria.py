"""Curadoria das Matrizes Fiscais — quem pode ESCREVER a regra global.

As matrizes (MVA, enquadramento, FCP, protocolos, alíquotas) são GLOBAIS: uma
edição vale para todas as empresas auditadas. A curadoria é trabalho diário dos
ANALISTAS (supervisores cadastram NCM/MVA da sua carteira) — por isso, desde
jul/2026, QUALQUER usuário autenticado escreve por padrão; a auditoria de
mudanças fica registrada no log.

`NEXOS_MATRIZ_CURADORES` é o freio de emergência opcional: preenchido com
e-mails separados por vírgula, SÓ esses usuários escrevem (independente do
papel). Vazio (default) = liberado para todos.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import PermissionDeniedError
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.identity.infrastructure.models import User


def curador_autorizado(email: str | None, permitidos: list[str]) -> bool:
    """Regra pura: lista vazia libera (default); senão, e-mail deve constar."""
    if not permitidos:
        return True
    return (email or "").strip().lower() in permitidos


async def require_curador(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
) -> TokenClaims:
    permitidos = get_settings().matriz_curadores_list
    if not permitidos:
        return claims
    email = await session.scalar(select(User.email).where(User.id == claims.sub))
    if not curador_autorizado(email, permitidos):
        raise PermissionDeniedError(
            "Escrita nas Matrizes Fiscais é restrita aos curadores configurados "
            "(NEXOS_MATRIZ_CURADORES)."
        )
    return claims
