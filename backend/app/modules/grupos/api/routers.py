"""Rotas de grupos (controle de acesso). Leitura: supervisor+. Escrita: admin."""
from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims
from app.modules.audit.application.service import AuditService
from app.modules.grupos.api.schemas import GrupoBody, GrupoDetail, GrupoListItem
from app.modules.grupos.application.service import GrupoService

router = APIRouter(prefix="/grupos", tags=["Grupos"])


@router.get("", response_model=list[GrupoListItem])
async def listar(
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await GrupoService(session).list()


@router.get("/{grupo_id}", response_model=GrupoDetail)
async def obter(
    grupo_id: UUID,
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    return await GrupoService(session).get(grupo_id)


@router.post("", response_model=GrupoDetail, status_code=status.HTTP_201_CREATED)
async def criar(
    body: GrupoBody,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    g = await GrupoService(session).create(
        tenant_id=claims.tid, nome=body.nome, descricao=body.descricao,
        empresa_ids=body.empresa_ids, user_ids=body.user_ids, supervisor_id=body.supervisor_id,
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="grupo.criar",
        entidade="grupo", entidade_id=str(g["id"]),
        detalhe={"nome": g["nome"], "empresas": len(body.empresa_ids), "membros": len(body.user_ids)},
    )
    return g


@router.put("/{grupo_id}", response_model=GrupoDetail)
async def atualizar(
    grupo_id: UUID,
    body: GrupoBody,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    g = await GrupoService(session).update(
        grupo_id, tenant_id=claims.tid, nome=body.nome, descricao=body.descricao,
        empresa_ids=body.empresa_ids, user_ids=body.user_ids, supervisor_id=body.supervisor_id,
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="grupo.editar",
        entidade="grupo", entidade_id=str(grupo_id), detalhe={"nome": g["nome"]},
    )
    return g


@router.delete("/{grupo_id}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir(
    grupo_id: UUID,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    await GrupoService(session).delete(grupo_id)
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="grupo.excluir",
        entidade="grupo", entidade_id=str(grupo_id),
    )
