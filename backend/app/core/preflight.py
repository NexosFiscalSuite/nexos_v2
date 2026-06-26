"""Verificações de segurança executadas no boot (fail-fast).

Filosofia: é melhor a aplicação RECUSAR subir do que subir com uma brecha de
isolamento. Duas checagens, ambas relevantes para o go-live:

1. ``check_jwt_secret``  — em produção, o segredo HS256 NÃO pode ser o default
   do .env.example nem um valor curto/fraco. Como o token é simétrico, quem
   souber o segredo forja qualquer ``tid``/``role`` -> takeover total.

2. ``check_app_role_not_privileged`` — a conexão de runtime do app TEM que ser
   uma role sem SUPERUSER e sem BYPASSRLS. Se alguém apontar o DATABASE_URL para
   a role privilegiada por engano, a RLS é ignorada e o isolamento evapora em
   silêncio. Aqui isso vira um erro de boot explícito.
"""
import logging

from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.database import engine

logger = logging.getLogger("nexos")
settings = get_settings()

# Segredos que NUNCA podem aparecer em produção (default do repo + placeholders).
_SEGREDOS_PROIBIDOS = {
    "troque-este-segredo-em-producao",
    "change-me",
    "changeme",
    "secret",
    "",
}
_MIN_SECRET_LEN = 32

# Senhas default/fracas de infra (banco, S3/MinIO) — vindas do repo de dev.
_SENHAS_FRACAS = {
    "nexos", "nexos_app", "nexos12345", "postgres", "password",
    "passwd", "changeme", "admin", "root", "minio", "minioadmin", "",
}


class InsecureConfigurationError(RuntimeError):
    """Configuração insegura detectada no boot — a aplicação não deve subir."""


def check_jwt_secret() -> None:
    secret = (settings.jwt_secret or "").strip()
    fraco = secret in _SEGREDOS_PROIBIDOS or len(secret) < _MIN_SECRET_LEN

    if not fraco:
        return
    msg = (
        "NEXOS_JWT_SECRET é o valor default/placeholder ou tem menos de "
        f"{_MIN_SECRET_LEN} caracteres. Gere um forte: "
        'python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
    if settings.is_production:
        raise InsecureConfigurationError(msg)
    logger.warning("[preflight] %s (tolerado fora de produção)", msg)


def _senha_da_url(url: str) -> str:
    try:
        return make_url(url).password or ""
    except Exception:  # noqa: BLE001 — URL malformada: trata como sem senha
        return ""


def check_infra_secrets() -> None:
    """Senha de banco e credenciais de storage (S3/MinIO) não podem ser os
    defaults de dev em produção — senão o acesso ao banco/aos XMLs de todos os
    tenants fica trivial."""
    problemas: list[str] = []

    if (settings.s3_secret_key or "") in _SENHAS_FRACAS or len(settings.s3_secret_key or "") < 8:
        problemas.append("NEXOS_S3_SECRET_KEY é default/fraco (< 8 chars)")

    for nome, url in (
        ("NEXOS_DATABASE_URL", settings.database_url),
        ("NEXOS_DATABASE_PRIVILEGED_URL", settings.database_privileged_url),
    ):
        if _senha_da_url(url) in _SENHAS_FRACAS:
            problemas.append(f"{nome}: senha de banco default/fraca")

    if not problemas:
        return
    msg = "Segredos de infra inseguros -> " + "; ".join(problemas)
    if settings.is_production:
        raise InsecureConfigurationError(msg)
    logger.warning("[preflight] %s (tolerado fora de produção)", msg)


async def check_app_role_not_privileged() -> None:
    """A role de runtime do app não pode ser superuser nem ter BYPASSRLS."""
    async with engine.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT rolsuper, rolbypassrls "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            )
        ).first()

    if row is None:
        return
    rolsuper, rolbypassrls = bool(row[0]), bool(row[1])
    if not (rolsuper or rolbypassrls):
        return

    msg = (
        "A role de runtime do app (NEXOS_DATABASE_URL) tem "
        f"{'SUPERUSER ' if rolsuper else ''}"
        f"{'BYPASSRLS' if rolbypassrls else ''}".strip()
        + " — isso DESLIGA a RLS e quebra o isolamento entre tenants. "
        "Use uma role dedicada (nexos_app) sem esses atributos no runtime; "
        "deixe a role privilegiada só para migração/auth (NEXOS_DATABASE_PRIVILEGED_URL)."
    )
    if settings.is_production:
        raise InsecureConfigurationError(msg)
    logger.warning("[preflight] %s (tolerado fora de produção)", msg)


async def run_preflight() -> None:
    check_jwt_secret()
    check_infra_secrets()
    await check_app_role_not_privileged()
    logger.info("[preflight] verificações de segurança OK")
