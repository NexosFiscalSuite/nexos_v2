"""Exceções de domínio + tradução para respostas HTTP.

As camadas de domínio/aplicação levantam estas exceções sem saber de HTTP.
Os handlers (registrados no main.py) fazem a ponte para o status code certo.
"""
from fastapi import Request
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Erro de regra de negócio. status_code default 400."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_failed"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )
