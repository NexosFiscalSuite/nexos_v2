"""RBAC — papéis e dependency de autorização.

Papéis herdados do legado (decisão de Fase 1): admin > supervisor > user.
A hierarquia é por nível: quem tem nível >= ao exigido passa.
"""
from enum import Enum

from fastapi import Depends

from app.core.exceptions import PermissionDeniedError
from app.core.security import TokenClaims, get_current_claims


class Role(str, Enum):
    ADMIN = "admin"            # admin do escritório (gestão do tenant)
    SUPERVISOR = "supervisor"  # visão ampliada / supervisão de grupos
    USER = "user"             # operador comum (escopo por grupos)


# Nível numérico para comparação de hierarquia.
_ROLE_LEVEL: dict[str, int] = {
    Role.USER.value: 1,
    Role.SUPERVISOR.value: 2,
    Role.ADMIN.value: 3,
}


def role_level(role: str) -> int:
    return _ROLE_LEVEL.get(role, 0)


def require_role(minimum: Role):
    """Dependency factory: exige `minimum` ou superior.

    Uso:  @router.get(..., dependencies=[Depends(require_role(Role.ADMIN))])
    ou:   claims = Depends(require_role(Role.SUPERVISOR))
    """

    async def _guard(claims: TokenClaims = Depends(get_current_claims)) -> TokenClaims:
        if role_level(claims.role) < role_level(minimum.value):
            raise PermissionDeniedError(
                f"Requer papel '{minimum.value}' ou superior."
            )
        return claims

    return _guard
