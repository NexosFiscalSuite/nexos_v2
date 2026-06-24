"""Repositório de processing_jobs."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.jobs.infrastructure.models import ProcessingJob


class JobRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def by_id(self, job_id: UUID) -> ProcessingJob | None:
        return await self.session.get(ProcessingJob, job_id)

    async def list_by_tenant(self, tenant_id: UUID, limit: int = 50) -> list[ProcessingJob]:
        res = await self.session.execute(
            select(ProcessingJob)
            .where(ProcessingJob.tenant_id == tenant_id)
            .order_by(ProcessingJob.created_at.desc())
            .limit(limit)
        )
        return list(res.scalars().all())

    def add(self, job: ProcessingJob) -> None:
        self.session.add(job)
