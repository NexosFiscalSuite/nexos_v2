"""Segurança: hashing de senha (Argon2), emissão/validação de JWT e a
dependency que extrai as claims do request.

Fica em `core` (não num módulo) porque RLS e rate limit também dependem das
claims do token — é infraestrutura transversal, não regra de negócio.
"""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import AuthenticationError

settings = get_settings()
_ph = PasswordHasher()

ACCESS = "access"
REFRESH = "refresh"


# Senhas ---------------------------------------------------------------------

def hash_password(plain: str) -> str:
    return _ph.hash(plain)


def verify_password(stored_hash: str, plain: str) -> bool:
    try:
        return _ph.verify(stored_hash, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _ph.check_needs_rehash(stored_hash)


# Tokens ---------------------------------------------------------------------

class TokenClaims(BaseModel):
    sub: UUID          # user_id
    tid: UUID          # tenant_id
    role: str          # admin | supervisor | user
    plan: str          # código do plano (drive de rate-limit/quotas)
    type: str          # access | refresh
    jti: UUID          # id único do token (revogação de refresh)


def _encode(claims: dict, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {**claims, "iat": now, "exp": now + ttl}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: UUID, tenant_id: UUID, role: str, plan: str) -> str:
    return _encode(
        {
            "sub": str(user_id),
            "tid": str(tenant_id),
            "role": role,
            "plan": plan,
            "type": ACCESS,
            "jti": str(uuid4()),
        },
        timedelta(minutes=settings.access_token_ttl_min),
    )


def create_refresh_token(
    *, user_id: UUID, tenant_id: UUID, role: str, plan: str, jti: UUID
) -> str:
    return _encode(
        {
            "sub": str(user_id),
            "tid": str(tenant_id),
            "role": role,
            "plan": plan,
            "type": REFRESH,
            "jti": str(jti),
        },
        timedelta(days=settings.refresh_token_ttl_days),
    )


def decode_token(token: str) -> TokenClaims:
    try:
        payload = jwt.decode(
            token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
        )
        return TokenClaims(**payload)
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token expirado.", code="token_expired") from exc
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise AuthenticationError("Token inválido.", code="token_invalid") from exc


# Dependency -----------------------------------------------------------------

_bearer = HTTPBearer(auto_error=False)


async def get_current_claims(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> TokenClaims:
    if creds is None or not creds.credentials:
        raise AuthenticationError("Credenciais ausentes.", code="missing_credentials")
    claims = decode_token(creds.credentials)
    if claims.type != ACCESS:
        raise AuthenticationError(
            "Use um access token nesta rota.", code="wrong_token_type"
        )
    return claims
