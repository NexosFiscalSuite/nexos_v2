"""Serviço de auditoria: registrar (hook reutilizável) e listar a trilha."""
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.audit.infrastructure.models import AuditLog
from app.modules.audit.infrastructure.repositories import AuditRepository


class AuditService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AuditRepository(session)

    async def registrar(self, *, tenant_id: UUID, user_id: UUID | None, acao: str,
                        entidade: str | None = None, entidade_id: str | None = None,
                        detalhe: dict | None = None) -> None:
        """Grava uma entrada na trilha (best-effort, na mesma transação da ação)."""
        self.repo.add(AuditLog(
            id=uuid4(), tenant_id=tenant_id, user_id=user_id, acao=acao,
            entidade=entidade, entidade_id=entidade_id, detalhe=detalhe,
        ))
        await self.session.flush()

    async def listar(self, *, acao: str | None = None, user_id: UUID | None = None,
                     dias: int | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
        desde = None
        if dias:
            desde = datetime.now(UTC) - timedelta(days=dias)
        return await self.repo.list(acao=acao, user_id=user_id, desde=desde, limit=limit, offset=offset)

    async def acoes(self) -> list[str]:
        return await self.repo.acoes()
