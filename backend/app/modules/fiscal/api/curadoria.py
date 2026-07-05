"""Curadoria das Matrizes Fiscais — quem pode ESCREVER a regra global.

As matrizes (MVA, enquadramento, FCP, protocolos, alíquotas) são GLOBAIS: uma
edição vale para todas as empresas auditadas. Editar matriz é curadoria de
conteúdo tributário, não administração de tenant — papéis diferentes.

Opt-in por configuração: com `NEXOS_MATRIZ_CURADORES` vazio (default), qualquer
ADMIN escreve (comportamento histórico). Preenchido com e-mails separados por
vírgula, só esses usuários (ainda exigindo ADMIN) passam.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import PermissionDeniedError
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims
from app.modules.identity.infrastructure.models import User


def curador_autorizado(email: str | None, permitidos: list[str]) -> bool:
    """Regra pura: lista vazia libera (histórico); senão, e-mail deve constar."""
    if not permitidos:
        return True
    return (email or "").strip().lower() in permitidos


async def require_curador(
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
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
