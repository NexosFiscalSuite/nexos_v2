"""Rotas das regras De/Para CFOP -> Tipo de Item (GLOBAL, sem tenant)."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.cfop_rules.api.schemas import (
    CfopRegraCreate,
    CfopRegraResponse,
    CfopRegraUpdate,
)
from app.modules.cfop_rules.application.service import CfopRegraService
from app.modules.cfop_rules.infrastructure.models import CfopRegra
from app.modules.cfop_rules.infrastructure.repositories import norm_cfop
from app.shared.bulk_csv import BulkSpec, exportar_csv, importar_csv

router = APIRouter(prefix="/cfop-regras", tags=["Regras CFOP"])


def _norm_cfop_row(o: CfopRegraCreate) -> dict:
    d = o.model_dump()
    d["cfop_origem"] = norm_cfop(d.get("cfop_origem") or "")
    d["cfop_destino"] = norm_cfop(d.get("cfop_destino") or "") or d["cfop_origem"]
    if not d.get("usa_extensao"):
        d["extensao"] = None
    return d


_CFOP_SPEC = BulkSpec(CfopRegra, CfopRegraCreate, ("cfop_origem",), _norm_cfop_row)


@router.get("", response_model=list[CfopRegraResponse])
async def listar(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await CfopRegraService(session).list()


@router.post("", response_model=CfopRegraResponse, status_code=status.HTTP_201_CREATED)
async def criar(
    body: CfopRegraCreate,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    regra = await CfopRegraService(session).create(**body.model_dump())
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="cfop_regra.criar",
        entidade="cfop_regra", entidade_id=str(regra.id),
        detalhe={"origem": regra.cfop_origem, "destino": regra.cfop_destino, "tipo": regra.tipo_item},
    )
    return regra


@router.patch("/{rid}", response_model=CfopRegraResponse)
async def atualizar(
    rid: UUID,
    body: CfopRegraUpdate,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    regra = await CfopRegraService(session).update(rid, body.model_dump(exclude_unset=True))
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="cfop_regra.editar",
        entidade="cfop_regra", entidade_id=str(regra.id),
        detalhe={"origem": regra.cfop_origem, "destino": regra.cfop_destino, "tipo": regra.tipo_item},
    )
    return regra


@router.delete("/{rid}", status_code=status.HTTP_204_NO_CONTENT)
async def excluir(
    rid: UUID,
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    await CfopRegraService(session).delete(rid)
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="cfop_regra.remover",
        entidade="cfop_regra", entidade_id=str(rid), detalhe={},
    )


@router.get("/export")
async def exportar(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    csv_text = await exportar_csv(session, _CFOP_SPEC)
    return Response(
        content="﻿" + csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cfop_regras.csv"'},
    )


@router.post("/import")
async def importar(
    arquivo: UploadFile = File(...),
    claims: TokenClaims = Depends(require_role(Role.ADMIN)),
    session: AsyncSession = Depends(tenant_session),
):
    resumo = await importar_csv(session, _CFOP_SPEC, await arquivo.read())
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="cfop_regra.importar",
        entidade="cfop_regra", entidade_id=None,
        detalhe={k: v for k, v in resumo.items() if k != "erros"},
    )
    return resumo
