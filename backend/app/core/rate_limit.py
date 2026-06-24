"""Rate limiting com slowapi.

Chave = tenant (não IP): cada escritório tem seu próprio balde, o que é justo
sob NAT/proxy onde muitos usuários compartilham IP. Sem token (rotas públicas
como login), cai para o IP.

Tiers por plano: o plano vai dentro do JWT, então `plan_limit` deriva o limite
sem tocar no banco. Rotas sensíveis (login) usam limites estáticos menores.
"""
from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings
from app.core.security import decode_token

settings = get_settings()

# Limite por minuto conforme o plano (espelha a coluna plans.rate_limit_per_min).
PLAN_LIMITS: dict[str, str] = {
    "trial": "120/minute",
    "free": "120/minute",
    "pro": "600/minute",
    "enterprise": "3000/minute",
}


def _claims_from_request(request: Request):
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        try:
            return decode_token(auth[7:])
        except Exception:
            return None
    return None


def tenant_key_func(request: Request) -> str:
    """Balde do rate limit: tenant se autenticado, senão IP."""
    claims = _claims_from_request(request)
    if claims is not None:
        return f"tenant:{claims.tid}"
    return f"ip:{get_remote_address(request)}"


def plan_limit() -> str:
    """Limite default global (fallback). O tier real por plano é aplicado nas
    rotas via `@limiter.limit(plan_limit_for_request)` quando desejado."""
    return settings.rate_limit_default


limiter = Limiter(
    key_func=tenant_key_func,
    storage_uri=settings.redis_url,
    default_limits=[settings.rate_limit_default],
    # headers_enabled=True exigiria um parâmetro `response: Response` em TODA rota
    # com @limiter.limit (senão o slowapi estoura ao injetar os headers). Como as
    # rotas retornam modelos Pydantic, mantemos desligado. O 429 segue funcionando.
    headers_enabled=False,
    # Se o Redis cair, NÃO derruba a API com 500 — libera a requisição (fail-open).
    swallow_errors=True,
)
