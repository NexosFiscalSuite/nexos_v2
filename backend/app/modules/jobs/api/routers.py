"""Rotas de consulta de jobs (o frontend faz polling para o feedback visual)."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.jobs.api.schemas import JobResponse
from app.modules.jobs.infrastructure.repositories import JobRepository

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get("", response_model=list[JobResponse])
async def list_jobs(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await JobRepository(session).list_by_tenant(claims.tid)


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    job = await JobRepository(session).by_id(job_id)
    if job is None:  # RLS já garante que só vê jobs do próprio tenant
        raise NotFoundError("Job não encontrado.")
    return job
