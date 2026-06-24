"""Repositório de grupos (sob RLS — tenant isolado pela session)."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.companies.infrastructure.models import Empresa
from app.modules.grupos.infrastructure.models import (
    PAPEL_MEMBRO,
    PAPEL_SUPERVISOR,
    EmpresaGrupo,
    Grupo,
    GrupoMembro,
)
from app.modules.identity.infrastructure.models import User


class GrupoRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, grupo_id: UUID) -> Grupo | None:
        return await self.session.get(Grupo, grupo_id)

    async def list(self) -> list[Grupo]:
        res = await self.session.execute(select(Grupo).order_by(Grupo.nome))
        return list(res.scalars().all())

    async def membros(self, grupo_id: UUID) -> list[GrupoMembro]:
        res = await self.session.execute(select(GrupoMembro).where(GrupoMembro.grupo_id == grupo_id))
        return list(res.scalars().all())

    async def empresa_ids(self, grupo_id: UUID) -> list[UUID]:
        res = await self.session.execute(
            select(EmpresaGrupo.empresa_id).where(EmpresaGrupo.grupo_id == grupo_id)
        )
        return [r[0] for r in res.all()]

    async def counts(self) -> tuple[dict, dict, dict]:
        """(membros_por_grupo, empresas_por_grupo, supervisor_por_grupo{gid:(uid,nome)})."""
        m = (await self.session.execute(
            select(GrupoMembro.grupo_id, func.count()).group_by(GrupoMembro.grupo_id)
        )).all()
        e = (await self.session.execute(
            select(EmpresaGrupo.grupo_id, func.count()).group_by(EmpresaGrupo.grupo_id)
        )).all()
        sup = (await self.session.execute(
            select(GrupoMembro.grupo_id, User.id, User.full_name)
            .join(User, User.id == GrupoMembro.user_id)
            .where(GrupoMembro.papel == PAPEL_SUPERVISOR)
        )).all()
        return (
            {gid: n for gid, n in m},
            {gid: n for gid, n in e},
            {gid: (uid, nome) for gid, uid, nome in sup},
        )

    async def empresa_ids_for_user(self, user_id: UUID) -> set[UUID]:
        """Empresas acessíveis a um usuário via seus grupos."""
        res = await self.session.execute(
            select(EmpresaGrupo.empresa_id)
            .join(GrupoMembro, GrupoMembro.grupo_id == EmpresaGrupo.grupo_id)
            .where(GrupoMembro.user_id == user_id)
        )
        return {r[0] for r in res.all()}

    async def _valid_ids(self, model, ids: list[UUID]) -> set[UUID]:
        """Filtra ids que existem no tenant (RLS) — evita vínculo cross-tenant."""
        if not ids:
            return set()
        res = await self.session.execute(select(model.id).where(model.id.in_(ids)))
        return {r[0] for r in res.all()}

    def add(self, grupo: Grupo) -> None:
        self.session.add(grupo)

    async def set_vinculos(self, tenant_id: UUID, grupo_id: UUID, empresa_ids, user_ids, supervisor_id):
        # limpa vínculos atuais
        await self.session.execute(delete(EmpresaGrupo).where(EmpresaGrupo.grupo_id == grupo_id))
        await self.session.execute(delete(GrupoMembro).where(GrupoMembro.grupo_id == grupo_id))

        emp_ok = await self._valid_ids(Empresa, list(empresa_ids or []))
        for eid in emp_ok:
            self.session.add(EmpresaGrupo(grupo_id=grupo_id, empresa_id=eid, tenant_id=tenant_id))

        user_ok = await self._valid_ids(User, list({*(user_ids or []), *([supervisor_id] if supervisor_id else [])}))
        sup = supervisor_id if supervisor_id in user_ok else None
        for uid in user_ok:
            if uid == sup:
                continue
            self.session.add(GrupoMembro(grupo_id=grupo_id, user_id=uid, tenant_id=tenant_id, papel=PAPEL_MEMBRO))
        if sup:
            self.session.add(GrupoMembro(grupo_id=grupo_id, user_id=sup, tenant_id=tenant_id, papel=PAPEL_SUPERVISOR))

    async def delete(self, grupo_id: UUID) -> None:
        await self.session.execute(delete(EmpresaGrupo).where(EmpresaGrupo.grupo_id == grupo_id))
        await self.session.execute(delete(GrupoMembro).where(GrupoMembro.grupo_id == grupo_id))
        g = await self.by_id(grupo_id)
        if g:
            await self.session.delete(g)
