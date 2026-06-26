"""Middleware ASGI que injeta headers de segurança em toda resposta HTTP.

Implementação ASGI pura (não BaseHTTPMiddleware) — sem overhead por request.

Headers sempre presentes:
  * X-Content-Type-Options: nosniff      -> bloqueia MIME sniffing
  * X-Frame-Options: DENY                -> anti-clickjacking (legado)
  * Referrer-Policy: no-referrer         -> não vaza URL em navegações externas
  * X-Permitted-Cross-Domain-Policies: none

Condicionais (ligados só em produção, ver main.py):
  * Content-Security-Policy              -> `default-src 'none'` quebra o Swagger,
    por isso só entra quando /docs está desativado (prod).
  * Strict-Transport-Security (HSTS)     -> força HTTPS no browser por 1 ano.
"""
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False, csp: str | None = None) -> None:
        self.app = app
        self._headers: list[tuple[bytes, bytes]] = [
            (b"x-content-type-options", b"nosniff"),
            (b"x-frame-options", b"DENY"),
            (b"referrer-policy", b"no-referrer"),
            (b"x-permitted-cross-domain-policies", b"none"),
        ]
        if csp:
            self._headers.append((b"content-security-policy", csp.encode()))
        if hsts:
            self._headers.append(
                (b"strict-transport-security", b"max-age=31536000; includeSubDomains; preload")
            )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = message.setdefault("headers", [])
                presentes = {k.lower() for k, _ in headers}
                for k, v in self._headers:
                    if k not in presentes:  # não sobrescreve o que a rota já setou
                        headers.append((k, v))
            await send(message)

        await self.app(scope, receive, send_wrapper)
