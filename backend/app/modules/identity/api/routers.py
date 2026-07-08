"""Rotas do Identity: autenticação (pública) e gestão de usuários (RLS + RBAC)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import privileged_session
from app.core.rate_limit import limiter
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.identity.api.schemas import (
    CreateUserRequest,
    LoginRequest,
    RefreshRequest,
    RegisterTenantRequest,
    TokenResponse,
    UpdateUserRequest,
    UserResponse,
)
from app.modules.identity.application.auth_service import AuthService, UserService

# ── Autenticação (rotas públicas, sem contexto de tenant) ────────────────────
auth_router = APIRouter(prefix="/auth", tags=["Auth"])


@auth_router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(
    request: Request,
    body: RegisterTenantRequest,
    session: AsyncSession = Depends(privileged_session),
):
    """Signup de um novo escritório (tenant) + usuário admin inicial."""
    pair = await AuthService(session).register_tenant(
        cnpj=body.cnpj,
        razao_social=body.razao_social,
        slug=body.slug,
        admin_email=body.admin_email,
        admin_full_name=body.admin_full_name,
        admin_password=body.admin_password,
        plan_code=body.plan_code,
    )
    return pair


@auth_router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    session: AsyncSession = Depends(privileged_session),
):
    return await AuthService(session).login(
        email=body.email, password=body.password, tenant_slug=body.tenant_slug
    )


@auth_router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh(
    request: Request,
    body: RefreshRequest,
    session: AsyncSession = Depends(privileged_session),
):
    return await AuthService(session).refresh(refresh_token=body.refresh_token)


@auth_router.get("/me", response_model=UserResponse)
async def me(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Dados do usuário logado (lido já sob RLS)."""
    users = await UserService(session).list_users(claims.tid)
    current = next((u for u in users if u.id == claims.sub), None)
    if current is None:  # defensivo: token válido mas usuário sumiu
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Usuário não encontrado.")
    return current


# ── Gestão de usuários (dentro do tenant) ────────────────────────────────────
users_router = APIRouter(prefix="/users", tags=["Usuários"])


@users_router.get("", response_model=list[UserResponse])
async def list_users(
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await UserService(session).list_users(claims.tid)


@users_router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    body: CreateUserRequest,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    user = await UserService(session).create_user(
        tenant_id=claims.tid,
        email=body.email,
        full_name=body.full_name,
        password=body.password,
        role=body.role,
    )
    from app.modules.audit.application.service import AuditService

    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="usuario.criar",
        entidade="usuario", entidade_id=str(user.id),
        detalhe={"email": user.email, "role": user.role},
    )
    return user


@users_router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID,
    body: UpdateUserRequest,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    """Edita nome/papel/senha e ativa/inativa o usuário. Inativado não loga
    nem renova a sessão (o access token corrente expira em minutos)."""
    user = await UserService(session).update_user(
        tenant_id=claims.tid,
        user_id=user_id,
        editor_id=claims.sub,
        full_name=body.full_name,
        role=body.role,
        password=body.password,
        is_active=body.is_active,
    )
    from app.modules.audit.application.service import AuditService

    detalhe = {
        "full_name": body.full_name,
        "role": body.role,
        "is_active": body.is_active,
        "senha_alterada": True if body.password else None,
    }
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="usuario.editar",
        entidade="usuario", entidade_id=str(user.id),
        detalhe={k: v for k, v in detalhe.items() if v is not None},
    )
    return user
