"""Repositório da trilha de auditoria."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.infrastructure.models import AuditLog
from app.modules.identity.infrastructure.models import User


class AuditRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    def add(self, entry: AuditLog) -> None:
        self.session.add(entry)

    async def list(self, *, acao: str | None = None, user_id: UUID | None = None,
                   desde: datetime | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
        stmt = (
            select(AuditLog, User.full_name)
            .join(User, User.id == AuditLog.user_id, isouter=True)
        )
        if acao:
            stmt = stmt.where(AuditLog.acao == acao)
        if user_id:
            stmt = stmt.where(AuditLog.user_id == user_id)
        if desde:
            stmt = stmt.where(AuditLog.created_at >= desde)
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(limit).offset(offset)
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "id": a.id, "acao": a.acao, "entidade": a.entidade, "entidade_id": a.entidade_id,
                "detalhe": a.detalhe, "created_at": a.created_at,
                "user_id": a.user_id, "user_nome": nome,
            }
            for a, nome in rows
        ]

    async def acoes(self) -> list[str]:
        res = await self.session.execute(select(AuditLog.acao).distinct().order_by(AuditLog.acao))
        return [r[0] for r in res.all()]
