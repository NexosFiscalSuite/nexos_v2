"""Casos de uso de Identity.

Dois serviços, por nível de privilégio da session:

* ``AuthService``  -> session PRIVILEGIADA (BYPASSRLS). Operações cross-tenant:
  signup (cria tenant), login (acha usuário antes do contexto) e refresh.
* ``UserService``  -> session RLS (tenant_session). Gestão de usuários DENTRO
  do tenant; o banco já garante o isolamento.
"""
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import (
    AuthenticationError,
    ConflictError,
    DomainError,
    NotFoundError,
)
from app.core.rbac import Role
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.modules.identity.application.dtos import TokenPair, UserView
from app.modules.identity.infrastructure.models import RefreshToken, Tenant, User
from app.modules.identity.infrastructure.repositories import (
    PlanRepository,
    RefreshTokenRepository,
    TenantRepository,
    UserRepository,
)
from app.shared.domain.value_objects import CNPJ

settings = get_settings()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _to_view(u: User) -> UserView:
    return UserView(
        id=u.id,
        tenant_id=u.tenant_id,
        email=u.email,
        full_name=u.full_name,
        role=u.role,
        is_active=u.is_active,
        created_at=u.created_at,
        last_login=u.last_login,
    )


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.plans = PlanRepository(session)
        self.tenants = TenantRepository(session)
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)

    # -- signup -------------------------------------------------------------
    async def register_tenant(
        self,
        *,
        cnpj: str,
        razao_social: str,
        slug: str,
        admin_email: str,
        admin_full_name: str,
        admin_password: str,
        plan_code: str = "trial",
    ) -> TokenPair:
        cnpj_vo = CNPJ(cnpj)  # valida dígitos
        slug = slug.strip().lower()

        if await self.tenants.by_cnpj(cnpj_vo.value):
            raise ConflictError("Já existe um escritório com este CNPJ.")
        if await self.tenants.by_slug(slug):
            raise ConflictError("Este identificador (slug) já está em uso.")

        plan = await self.plans.by_code(plan_code)
        if plan is None:
            raise NotFoundError(f"Plano '{plan_code}' não encontrado.")

        tenant = Tenant(
            id=uuid4(),
            cnpj=cnpj_vo.value,
            razao_social=razao_social.strip(),
            slug=slug,
            plan_id=plan.id,
            status="trial",
            trial_ends_at=datetime.now(UTC) + timedelta(days=14),
        )
        self.tenants.add(tenant)

        admin = User(
            id=uuid4(),
            tenant_id=tenant.id,
            email=admin_email.strip().lower(),
            full_name=admin_full_name.strip(),
            password_hash=hash_password(admin_password),
            role=Role.ADMIN.value,
            is_active=True,
        )
        self.users.add(admin)
        await self.session.flush()

        pair = await self._issue_tokens(admin, plan_code=plan.code)
        await self.session.commit()
        return pair

    # -- login --------------------------------------------------------------
    async def login(
        self, *, email: str, password: str, tenant_slug: str | None = None
    ) -> TokenPair:
        email = email.strip().lower()

        if tenant_slug:
            tenant = await self.tenants.by_slug(tenant_slug.strip().lower())
            if tenant is None:
                raise AuthenticationError("Credenciais inválidas.")
            user = await self.users.by_email(tenant.id, email)
            candidates = [user] if user else []
        else:
            candidates = await self.users.list_by_email_global(email)

        if len(candidates) > 1:
            raise DomainError(
                "E-mail vinculado a mais de um escritório. Informe o identificador (slug).",
                code="tenant_required",
            )
        user = candidates[0] if candidates else None

        # Verifica a senha mesmo sem usuário (mitiga enumeração por timing).
        stored = user.password_hash if user else hash_password("dummy")
        if not verify_password(stored, password) or user is None:
            raise AuthenticationError("Credenciais inválidas.")
        if not user.is_active:
            raise AuthenticationError("Usuário inativo.")

        tenant = await self.tenants.by_id(user.tenant_id)
        if tenant is None or tenant.status == "suspended":
            raise AuthenticationError("Escritório suspenso. Contate o suporte.")

        await self.users.touch_last_login(user)
        pair = await self._issue_tokens(user, plan_code=tenant.plan.code)
        await self.session.commit()
        return pair

    # -- refresh (rotação) --------------------------------------------------
    async def refresh(self, *, refresh_token: str) -> TokenPair:
        claims = decode_token(refresh_token)
        if claims.type != "refresh":
            raise AuthenticationError("Token não é de refresh.", code="wrong_token_type")

        stored = await self.refresh_tokens.by_jti(claims.jti)
        if (
            stored is None
            or stored.revoked
            or stored.token_hash != _hash_token(refresh_token)
            or stored.expires_at < datetime.now(UTC)
        ):
            raise AuthenticationError("Refresh token inválido.", code="invalid_refresh")

        stored.revoked = True  # rotação: o antigo morre ao ser usado
        user = await self.users.by_id(claims.sub)
        if user is None or not user.is_active:
            raise AuthenticationError("Usuário indisponível.")

        tenant = await self.tenants.by_id(user.tenant_id)
        pair = await self._issue_tokens(user, plan_code=tenant.plan.code)
        await self.session.commit()
        return pair

    # -- helper -------------------------------------------------------------
    async def _issue_tokens(self, user: User, *, plan_code: str) -> TokenPair:
        jti = uuid4()
        access = create_access_token(
            user_id=user.id, tenant_id=user.tenant_id, role=user.role, plan=plan_code
        )
        refresh = create_refresh_token(
            user_id=user.id,
            tenant_id=user.tenant_id,
            role=user.role,
            plan=plan_code,
            jti=jti,
        )
        self.refresh_tokens.add(
            RefreshToken(
                id=uuid4(),
                jti=jti,
                tenant_id=user.tenant_id,
                user_id=user.id,
                token_hash=_hash_token(refresh),
                expires_at=datetime.now(UTC)
                + timedelta(days=settings.refresh_token_ttl_days),
            )
        )
        return TokenPair(access_token=access, refresh_token=refresh)


class UserService:
    """Gestão de usuários dentro do tenant (session já isolada por RLS)."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.users = UserRepository(session)

    async def list_users(self, tenant_id: UUID) -> list[UserView]:
        rows = await self.users.list_by_tenant(tenant_id)
        return [_to_view(u) for u in rows]

    async def create_user(
        self,
        *,
        tenant_id: UUID,
        email: str,
        full_name: str,
        password: str,
        role: str = Role.USER.value,
    ) -> UserView:
        email = email.strip().lower()
        if role not in (r.value for r in Role):
            raise DomainError(f"Papel inválido: {role}.")
        if await self.users.by_email(tenant_id, email):
            raise ConflictError("Já existe um usuário com este e-mail.")

        user = User(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            full_name=full_name.strip(),
            password_hash=hash_password(password),
            role=role,
            is_active=True,
        )
        self.users.add(user)
        # NÃO commitamos aqui: a tenant_session detém a transação (o SET LOCAL
        # do tenant tem que viver na MESMA transação das queries). Só flush —
        # o commit acontece ao fim do request, no dependency tenant_session.
        await self.session.flush()
        return _to_view(user)
