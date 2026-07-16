"""Entry point da API Nexos V2 (app factory)."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.database import privileged_engine
from app.core.exceptions import DomainError, domain_error_handler
from app.core.logging import setup_logging
from app.core.rate_limit import limiter
from app.core.security_headers import SecurityHeadersMiddleware
from app.modules.audit.api.routers import router as audit_router
from app.modules.cfop_rules.api.routers import router as cfop_regras_router
from app.modules.companies.api.routers import router as empresas_router
from app.modules.compliance.api.routers import router as compliance_router
from app.modules.contrapartes.api.routers import lookup_router
from app.modules.contrapartes.api.routers import router as contrapartes_router
from app.modules.dashboard.api.routers import router as dashboard_router
from app.modules.fiscal.api.auditoria_routers import router as auditoria_st_router
from app.modules.fiscal.api.ibscbs_routers import router as ibscbs_router
from app.modules.fiscal.api.matrizes_bulk import router as matrizes_bulk_router
from app.modules.fiscal.api.matrizes_routers import router as matrizes_router
from app.modules.fiscal.api.routers import router as fiscal_router
from app.modules.grupos.api.routers import router as grupos_router
from app.modules.identity.api.routers import auth_router, users_router
from app.modules.jobs.api.routers import router as jobs_router
from app.modules.reporting.api.routers import router as reporting_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    # Sentry (opcional, NEXOS_SENTRY_DSN) — antes de tudo para capturar até
    # falha de preflight/startup.
    from app.core.observability import init_sentry
    init_sentry()
    # Preflight de segurança (fail-fast em produção): segredo JWT forte + a role
    # de runtime do app não pode ter SUPERUSER/BYPASSRLS (senão a RLS é ignorada).
    from app.core.preflight import run_preflight
    await run_preflight()
    # Provisiona o storage (cria o bucket S3) antes de aceitar uploads. Tolera
    # falha transitória do MinIO no boot: o _ensure_bucket roda de novo no 1º uso.
    try:
        from fastapi.concurrency import run_in_threadpool

        from app.core.storage import ensure_storage_ready
        await run_in_threadpool(ensure_storage_ready)
    except Exception:  # noqa: BLE001 — startup resiliente; storage reprovisiona sob demanda
        logging.getLogger("nexos").warning("Falha ao provisionar o storage no startup; tentará no 1º uso.")
    yield
    await privileged_engine.dispose()


def create_app() -> FastAPI:
    is_prod = settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version="2.0.0",
        description="SaaS multi-tenant para escritórios de contabilidade (RLS + RBAC).",
        lifespan=lifespan,
        # Em produção, desativa docs interativas + schema OpenAPI para reduzir a
        # superfície de ataque (e liberar a CSP estrita, que quebraria o Swagger).
        docs_url=None if is_prod else "/docs",
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )

    # Headers de segurança (HSTS + CSP só em prod; demais sempre). Adicionado
    # primeiro -> fica na camada mais externa, garantindo os headers em toda resposta.
    app.add_middleware(
        SecurityHeadersMiddleware,
        hsts=is_prod,
        csp="default-src 'none'; frame-ancestors 'none'; base-uri 'none'" if is_prod else None,
    )

    # Rate limiting (slowapi)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list or ["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Handlers de domínio -> HTTP
    app.add_exception_handler(DomainError, domain_error_handler)

    # Rotas
    p = settings.api_prefix
    app.include_router(auth_router, prefix=p)
    app.include_router(users_router, prefix=p)
    app.include_router(empresas_router, prefix=p)
    app.include_router(fiscal_router, prefix=p)
    app.include_router(auditoria_st_router, prefix=p)
    app.include_router(ibscbs_router, prefix=p)
    app.include_router(matrizes_router, prefix=p)
    app.include_router(matrizes_bulk_router, prefix=p)
    app.include_router(compliance_router, prefix=p)
    app.include_router(reporting_router, prefix=p)
    app.include_router(jobs_router, prefix=p)
    app.include_router(dashboard_router, prefix=p)
    app.include_router(contrapartes_router, prefix=p)
    app.include_router(lookup_router, prefix=p)
    app.include_router(cfop_regras_router, prefix=p)
    app.include_router(grupos_router, prefix=p)
    app.include_router(audit_router, prefix=p)

    @app.get("/health", tags=["Infra"])
    async def health():
        db_ok = True
        try:
            async with privileged_engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        except Exception:
            db_ok = False
        return {
            "status": "ok" if db_ok else "degraded",
            "app": settings.app_name,
            "version": "2.0.0",
            "database": "ok" if db_ok else "down",
        }

    return app


app = create_app()
