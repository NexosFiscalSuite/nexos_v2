"""Casos de uso de empresas (sob RLS — tenant já isolado pela session)."""
from __future__ import annotations

from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, PermissionDeniedError
from app.core.security import TokenClaims
from app.modules.companies.infrastructure.models import Empresa
from app.modules.companies.infrastructure.repositories import EmpresaRepository
from app.modules.grupos.infrastructure.repositories import GrupoRepository
from app.shared.domain.value_objects import CNPJ

# Papéis com visão de todas as empresas do escritório (sem filtro por grupo).
_FULL_ACCESS = {"admin", "supervisor"}


class EmpresaService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = EmpresaRepository(session)

    async def list(self, tenant_id: UUID) -> list[Empresa]:
        return await self.repo.list_by_tenant(tenant_id)

    async def list_for(self, claims: TokenClaims) -> list[Empresa]:
        """admin/supervisor veem todas; `user` só vê empresas dos seus grupos."""
        if claims.role in _FULL_ACCESS:
            return await self.repo.list_by_tenant(claims.tid)
        ids = await GrupoRepository(self.session).empresa_ids_for_user(claims.sub)
        return await self.repo.list_by_ids(claims.tid, ids) if ids else []

    async def get(self, empresa_id: UUID) -> Empresa | None:
        return await self.repo.by_id(empresa_id)

    async def get_for(self, claims: TokenClaims, empresa_id: UUID) -> Empresa | None:
        """Carrega a empresa respeitando o acesso por grupo do `user`."""
        empresa = await self.repo.by_id(empresa_id)
        if empresa is None:
            return None
        if claims.role not in _FULL_ACCESS:
            ids = await GrupoRepository(self.session).empresa_ids_for_user(claims.sub)
            if empresa_id not in ids:
                raise PermissionDeniedError("Você não tem acesso a esta empresa.")
        return empresa

    async def create(self, *, tenant_id: UUID, cnpj: str, razao_social: str, **extra) -> Empresa:
        cnpj_vo = CNPJ(cnpj)
        if await self.repo.by_cnpj(tenant_id, cnpj_vo.value):
            raise ConflictError("Empresa já cadastrada para este escritório.")
        empresa = Empresa(
            id=uuid4(),
            tenant_id=tenant_id,
            cnpj=cnpj_vo.value,
            razao_social=razao_social.strip(),
            nome_fantasia=extra.get("nome_fantasia"),
            regime=extra.get("regime"),
            uf=extra.get("uf"),
            municipio=extra.get("municipio"),
            inscricao_estadual=extra.get("inscricao_estadual"),
        )
        self.repo.add(empresa)
        await self.session.flush()
        return empresa
