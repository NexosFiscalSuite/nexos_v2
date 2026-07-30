"""Visibilidade de empresas por papel (list_for/get_for).

Regra: só o ADMIN vê todas as empresas do escritório. Supervisor e usuário
comum veem apenas as dos grupos em que estão — o supervisor do grupo é
gravado como GrupoMembro com papel "supervisor", então a consulta por grupo
cobre os dois papéis.
"""
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.exceptions import PermissionDeniedError
from app.core.security import TokenClaims
from app.modules.companies.application.service import EmpresaService
from app.modules.companies.infrastructure.models import Empresa
from app.modules.grupos.infrastructure.models import (
    PAPEL_MEMBRO,
    PAPEL_SUPERVISOR,
    EmpresaGrupo,
    Grupo,
    GrupoMembro,
)

_TABELAS = [Empresa.__table__, Grupo.__table__, GrupoMembro.__table__, EmpresaGrupo.__table__]

TENANT = uuid4()
ADMIN, SUPERVISOR, MEMBRO, SEM_GRUPO = uuid4(), uuid4(), uuid4(), uuid4()


def _claims(user_id, role):
    return TokenClaims(sub=user_id, tid=TENANT, role=role,
                       plan="pro", type="access", jti=uuid4())


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        e1 = Empresa(id=uuid4(), tenant_id=TENANT, cnpj="11444777000161",
                     razao_social="DO GRUPO LTDA")
        e2 = Empresa(id=uuid4(), tenant_id=TENANT, cnpj="04640241000156",
                     razao_social="FORA DO GRUPO LTDA")
        g = Grupo(id=uuid4(), tenant_id=TENANT, nome="Equipe ST")
        s.add_all([e1, e2, g])
        s.add_all([
            GrupoMembro(grupo_id=g.id, user_id=SUPERVISOR, tenant_id=TENANT,
                        papel=PAPEL_SUPERVISOR),
            GrupoMembro(grupo_id=g.id, user_id=MEMBRO, tenant_id=TENANT,
                        papel=PAPEL_MEMBRO),
            EmpresaGrupo(grupo_id=g.id, empresa_id=e1.id, tenant_id=TENANT),
        ])
        await s.flush()
        yield s, e1, e2
    await engine.dispose()


async def test_admin_ve_todas(sessao):
    s, _e1, _e2 = sessao
    nomes = [e.razao_social for e in await EmpresaService(s).list_for(_claims(ADMIN, "admin"))]
    assert nomes == ["DO GRUPO LTDA", "FORA DO GRUPO LTDA"]


async def test_supervisor_so_ve_empresas_dos_seus_grupos(sessao):
    s, e1, e2 = sessao
    svc = EmpresaService(s)
    vistas = await svc.list_for(_claims(SUPERVISOR, "supervisor"))
    assert [e.id for e in vistas] == [e1.id]

    # Acesso direto à empresa fora do grupo também é barrado.
    with pytest.raises(PermissionDeniedError):
        await svc.get_for(_claims(SUPERVISOR, "supervisor"), e2.id)
    assert (await svc.get_for(_claims(SUPERVISOR, "supervisor"), e1.id)).id == e1.id


async def test_membro_comum_so_ve_empresas_dos_seus_grupos(sessao):
    s, e1, _e2 = sessao
    vistas = await EmpresaService(s).list_for(_claims(MEMBRO, "user"))
    assert [e.id for e in vistas] == [e1.id]


async def test_quem_nao_tem_grupo_nao_ve_nada(sessao):
    s, _e1, _e2 = sessao
    assert await EmpresaService(s).list_for(_claims(SEM_GRUPO, "supervisor")) == []
    assert await EmpresaService(s).list_for(_claims(SEM_GRUPO, "user")) == []
