"""Edição/inativação de usuários — travas de lockout do UserService.

As regras que NÃO podem regredir: ninguém se inativa nem se rebaixa, e o
escritório nunca fica sem um administrador ativo (senão o tenant vira órfão:
não sobra ninguém capaz de gerir usuários).
"""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.exceptions import DomainError, NotFoundError
from app.core.security import verify_password
from app.modules.identity.application.auth_service import UserService
from app.modules.identity.infrastructure.models import User

TENANT = uuid4()


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def _seed(s: AsyncSession):
    svc = UserService(s)
    admin = await svc.create_user(
        tenant_id=TENANT, email="admin@sol.com", full_name="Admin",
        password="senha-forte-123", role="admin",
    )
    comum = await svc.create_user(
        tenant_id=TENANT, email="ana@sol.com", full_name="Ana",
        password="senha-forte-123", role="user",
    )
    return svc, admin, comum


async def test_edita_nome_papel_e_senha(sessao):
    svc, admin, comum = await _seed(sessao)

    v = await svc.update_user(
        tenant_id=TENANT, user_id=comum.id, editor_id=admin.id,
        full_name="Ana Souza", role="supervisor", password="nova-senha-123",
    )

    assert v.full_name == "Ana Souza"
    assert v.role == "supervisor"
    salvo = await sessao.get(User, comum.id)
    assert verify_password(salvo.password_hash, "nova-senha-123")


async def test_inativa_e_reativa(sessao):
    svc, admin, comum = await _seed(sessao)

    v = await svc.update_user(
        tenant_id=TENANT, user_id=comum.id, editor_id=admin.id, is_active=False
    )
    assert v.is_active is False

    v = await svc.update_user(
        tenant_id=TENANT, user_id=comum.id, editor_id=admin.id, is_active=True
    )
    assert v.is_active is True


async def test_admin_nao_inativa_a_si_mesmo(sessao):
    svc, admin, _ = await _seed(sessao)
    with pytest.raises(DomainError, match="inativar o próprio"):
        await svc.update_user(
            tenant_id=TENANT, user_id=admin.id, editor_id=admin.id, is_active=False
        )


async def test_admin_nao_rebaixa_o_proprio_papel(sessao):
    svc, admin, _ = await _seed(sessao)
    with pytest.raises(DomainError, match="próprio papel"):
        await svc.update_user(
            tenant_id=TENANT, user_id=admin.id, editor_id=admin.id, role="user"
        )


async def test_escritorio_nunca_fica_sem_admin_ativo(sessao):
    """Defesa extra além da auto-proteção: rebaixar/inativar o ÚNICO admin
    ativo é bloqueado mesmo se o editor for outro (ex.: chamada direta à API)."""
    svc, admin, _ = await _seed(sessao)
    with pytest.raises(DomainError, match="ao menos um administrador"):
        await svc.update_user(
            tenant_id=TENANT, user_id=admin.id, editor_id=uuid4(), role="user"
        )

    # Com um SEGUNDO admin ativo, aí sim pode rebaixar o primeiro.
    await svc.create_user(
        tenant_id=TENANT, email="admin2@sol.com", full_name="Admin Dois",
        password="senha-forte-123", role="admin",
    )
    v = await svc.update_user(
        tenant_id=TENANT, user_id=admin.id, editor_id=uuid4(), role="supervisor"
    )
    assert v.role == "supervisor"


async def test_papel_invalido_e_rejeitado(sessao):
    svc, admin, comum = await _seed(sessao)
    with pytest.raises(DomainError, match="Papel inválido"):
        await svc.update_user(
            tenant_id=TENANT, user_id=comum.id, editor_id=admin.id, role="chefe"
        )


async def test_usuario_de_outro_tenant_nao_e_encontrado(sessao):
    """Cinto e suspensório: além da RLS, o serviço confere o tenant_id."""
    svc, admin, comum = await _seed(sessao)
    with pytest.raises(NotFoundError):
        await svc.update_user(
            tenant_id=uuid4(), user_id=comum.id, editor_id=admin.id, full_name="X Y"
        )
