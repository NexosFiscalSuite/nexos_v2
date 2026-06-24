"""Casos de uso de grupos (CRUD + controle de acesso por empresa)."""
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, DomainError, NotFoundError
from app.modules.grupos.infrastructure.models import (
    PAPEL_SUPERVISOR,
    Grupo,
)
from app.modules.grupos.infrastructure.repositories import GrupoRepository


class GrupoService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = GrupoRepository(session)

    async def list(self) -> list[dict]:
        grupos = await self.repo.list()
        membros, empresas, sup = await self.repo.counts()
        out = []
        for g in grupos:
            s = sup.get(g.id)
            out.append({
                "id": g.id, "nome": g.nome, "descricao": g.descricao,
                "qtd_membros": membros.get(g.id, 0), "qtd_empresas": empresas.get(g.id, 0),
                "supervisor_id": s[0] if s else None, "supervisor_nome": s[1] if s else None,
                "created_at": g.created_at,
            })
        return out

    async def get(self, grupo_id: UUID) -> dict:
        g = await self.repo.by_id(grupo_id)
        if g is None:
            raise NotFoundError("Grupo não encontrado.")
        membros = await self.repo.membros(grupo_id)
        sup = next((m.user_id for m in membros if m.papel == PAPEL_SUPERVISOR), None)
        return {
            "id": g.id, "nome": g.nome, "descricao": g.descricao,
            "empresa_ids": await self.repo.empresa_ids(grupo_id),
            "user_ids": [m.user_id for m in membros if m.papel != PAPEL_SUPERVISOR],
            "supervisor_id": sup, "created_at": g.created_at,
        }

    async def create(self, *, tenant_id: UUID, nome: str, descricao: str | None,
                     empresa_ids, user_ids, supervisor_id) -> dict:
        if not (nome or "").strip():
            raise DomainError("Nome do grupo é obrigatório.")
        grupo = Grupo(id=uuid4(), tenant_id=tenant_id, nome=nome.strip(), descricao=(descricao or None))
        self.repo.add(grupo)
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            raise ConflictError("Já existe um grupo com esse nome.") from e
        await self.repo.set_vinculos(tenant_id, grupo.id, empresa_ids, user_ids, supervisor_id)
        await self.session.flush()
        return await self.get(grupo.id)

    async def update(self, grupo_id: UUID, *, tenant_id: UUID, nome: str, descricao: str | None,
                     empresa_ids, user_ids, supervisor_id) -> dict:
        g = await self.repo.by_id(grupo_id)
        if g is None:
            raise NotFoundError("Grupo não encontrado.")
        if not (nome or "").strip():
            raise DomainError("Nome do grupo é obrigatório.")
        g.nome = nome.strip()
        g.descricao = descricao or None
        try:
            await self.session.flush()
        except IntegrityError as e:
            await self.session.rollback()
            raise ConflictError("Já existe um grupo com esse nome.") from e
        await self.repo.set_vinculos(tenant_id, grupo_id, empresa_ids, user_ids, supervisor_id)
        await self.session.flush()
        return await self.get(grupo_id)

    async def delete(self, grupo_id: UUID) -> None:
        if await self.repo.by_id(grupo_id) is None:
            raise NotFoundError("Grupo não encontrado.")
        await self.repo.delete(grupo_id)
