"""Rotas fiscais: upload assíncrono + consulta/edição de notas + lote + DANFE."""
import io
import zipfile
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError, NotFoundError
from app.core.rate_limit import limiter
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.core.storage import get_storage, staging_key
from app.core.worker_db import worker_tenant_session
from app.modules.audit.application.service import AuditService
from app.modules.companies.infrastructure.repositories import EmpresaRepository
from app.modules.fiscal.api.schemas import (
    BulkCfop,
    BulkIds,
    BulkResult,
    BulkTipoNota,
    ItemUpdate,
    NotaDetailResponse,
    NotaItemResponse,
    NotaListResponse,
    NotaUpdate,
    UploadResponse,
)
from app.modules.fiscal.application.nota_service import NotaService
from app.modules.fiscal.domain.cfop_sped import TIPOS_SPED
from app.modules.fiscal.domain.tipos_nota import TIPOS_NOTA
from app.modules.fiscal.infrastructure.models import Nota, NotaItem
from app.modules.fiscal.infrastructure.repositories import NotaRepository
from app.modules.fiscal.workers import import_xmls
from app.modules.jobs.infrastructure.models import KIND_IMPORT, STATUS_QUEUED, ProcessingJob
from app.modules.jobs.infrastructure.repositories import JobRepository
from app.shared.danfe_api import gerar_danfe

router = APIRouter(prefix="/fiscal", tags=["Fiscal"])


def _detail(nota: Nota, itens: list[NotaItem]) -> NotaDetailResponse:
    d = NotaDetailResponse.model_validate(nota)
    d.itens = [NotaItemResponse.model_validate(i) for i in itens]
    return d


@router.post(
    "/empresas/{empresa_id}/upload",
    response_model=UploadResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit("30/minute")
async def upload_xmls(
    request: Request,
    empresa_id: UUID,
    files: list[UploadFile] = File(...),
    claims: TokenClaims = Depends(get_current_claims),
):
    """Recebe XMLs (ou .zip será suportado adiante), guarda no staging e enfileira.

    O job é criado e COMMITADO antes de enfileirar — evita corrida com o worker.
    """
    storage = get_storage()
    job_id = uuid4()

    staging: list[dict] = []
    for f in files:
        content = await f.read()
        if not content:
            continue
        fname = f.filename or "arquivo.xml"
        key = staging_key(claims.tid, job_id, f"{len(staging)}_{fname}")
        storage.put(key, content)
        staging.append({"key": key, "filename": fname})

    # Transação própria (commit ao sair do contexto) -> job já visível ao worker.
    async with worker_tenant_session(claims.tid) as s:
        empresa = await EmpresaRepository(s).by_id(empresa_id)
        if empresa is None:
            raise NotFoundError("Empresa não encontrada.")
        JobRepository(s).add(
            ProcessingJob(
                id=job_id,
                tenant_id=claims.tid,
                user_id=claims.sub,
                kind=KIND_IMPORT,
                status=STATUS_QUEUED,
                total=len(staging),
            )
        )

    import_xmls.delay(
        str(job_id), str(claims.tid), str(empresa_id), str(claims.sub), staging
    )
    return UploadResponse(job_id=job_id, status=STATUS_QUEUED, arquivos=len(staging))


@router.get("/empresas/{empresa_id}/notas", response_model=NotaListResponse)
async def list_notas(
    empresa_id: UUID,
    fluxo: str | None = None,
    ano: str | None = None,
    mes: str | None = None,
    status_: str | None = None,
    tipo: str | None = None,
    tipo_excluir: str | None = None,
    sort: str | None = None,
    order: str | None = None,
    page: int = 1,
    page_size: int = 20,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    return await NotaRepository(session).list(
        empresa_id, fluxo=fluxo, ano=ano, mes=mes, status=status_,
        tipo=tipo, tipo_excluir=tipo_excluir,
        sort=sort, order=order, page=page, page_size=page_size,
    )


@router.get("/tipos-sped", response_model=list[str])
async def tipos_sped(claims: TokenClaims = Depends(get_current_claims)):
    return TIPOS_SPED


@router.get("/tipos-nota", response_model=list[str])
async def tipos_nota(claims: TokenClaims = Depends(get_current_claims)):
    return TIPOS_NOTA


# ── Operações em lote (rotas LITERAIS antes de /notas/{nota_id}) ──────────────
@router.post("/empresas/{empresa_id}/notas/cancelar-lote", response_model=BulkResult)
async def cancelar_lote(
    empresa_id: UUID, body: BulkIds,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    n = await NotaService(session).cancelar_lote(empresa_id, body.ids)
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="nota.cancelar_lote",
        entidade="empresa", entidade_id=str(empresa_id), detalhe={"afetadas": n, "qtd_ids": len(body.ids)},
    )
    return BulkResult(afetadas=n)


@router.post("/empresas/{empresa_id}/notas/reativar-lote", response_model=BulkResult)
async def reativar_lote(
    empresa_id: UUID, body: BulkIds,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    n = await NotaService(session).reativar_lote(empresa_id, body.ids)
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="nota.reativar_lote",
        entidade="empresa", entidade_id=str(empresa_id), detalhe={"afetadas": n, "qtd_ids": len(body.ids)},
    )
    return BulkResult(afetadas=n)


@router.post("/empresas/{empresa_id}/notas/cfop-lote", response_model=BulkResult)
async def cfop_lote(
    empresa_id: UUID, body: BulkCfop,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    if not (body.cfop or "").strip():
        raise DomainError("Informe o CFOP.")
    return BulkResult(afetadas=await NotaService(session).alterar_cfop_lote(empresa_id, body.ids, body.cfop.strip()))


@router.post("/empresas/{empresa_id}/notas/tipo-lote", response_model=BulkResult)
async def tipo_lote(
    empresa_id: UUID, body: BulkTipoNota,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    if not (body.tipo_nota or "").strip():
        raise DomainError("Informe o tipo da nota.")
    return BulkResult(afetadas=await NotaService(session).tipo_nota_lote(empresa_id, body.ids, body.tipo_nota.strip()))


@router.post("/empresas/{empresa_id}/notas/xml-lote")
async def xml_lote(
    empresa_id: UUID, body: BulkIds,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    pares = await NotaService(session).storage_keys(empresa_id, body.ids)
    if not pares:
        raise NotFoundError("Nenhum XML disponível para as notas selecionadas.")
    storage = get_storage()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for chave, key in pares:
            try:
                zf.writestr(f"{chave}.xml", storage.get(key))
            except Exception:  # noqa: BLE001
                continue
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="xmls.zip"'},
    )


@router.post("/empresas/{empresa_id}/notas/danfe-lote")
async def danfe_lote(
    empresa_id: UUID, body: BulkIds,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    pares = await NotaService(session).storage_keys(empresa_id, body.ids)
    if not pares:
        raise NotFoundError("Nenhum XML disponível para gerar DANFE.")
    storage = get_storage()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for chave, key in pares:
            try:
                xml = storage.get(key).decode("utf-8", errors="ignore")
                pdf, err = await run_in_threadpool(gerar_danfe, xml)
                if pdf:
                    zf.writestr(f"{chave}.pdf", pdf)
            except Exception:  # noqa: BLE001
                continue
    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="danfes.zip"'},
    )


@router.get("/notas/{nota_id}", response_model=NotaDetailResponse)
async def get_nota(
    nota_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    nota, itens = await NotaService(session).get_detail(nota_id)
    return _detail(nota, itens)


@router.patch("/notas/{nota_id}", response_model=NotaDetailResponse)
async def update_nota(
    nota_id: UUID,
    body: NotaUpdate,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    nota, itens = await NotaService(session).update_nota(nota_id, body.model_dump(exclude_unset=True))
    return _detail(nota, itens)


@router.patch("/notas/{nota_id}/itens/{item_id}", response_model=NotaItemResponse)
async def update_item(
    nota_id: UUID,
    item_id: UUID,
    body: ItemUpdate,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    item = await NotaService(session).update_item(item_id, body.model_dump(exclude_unset=True))
    return NotaItemResponse.model_validate(item)


@router.post("/notas/{nota_id}/cancelar", response_model=NotaDetailResponse)
async def cancelar_nota(
    nota_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    nota, itens = await NotaService(session).cancelar(nota_id)
    return _detail(nota, itens)


@router.get("/notas/{nota_id}/xml")
async def download_xml(
    nota_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    nota = await NotaRepository(session).by_id(nota_id)
    if nota is None:
        raise NotFoundError("Nota não encontrada.")
    if not nota.storage_key:
        raise NotFoundError("XML não disponível para esta nota.")
    try:
        data = get_storage().get(nota.storage_key)
    except Exception as exc:  # noqa: BLE001
        raise NotFoundError("Arquivo XML não encontrado no storage.") from exc
    return Response(
        content=data,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{nota.chave_acesso}.xml"'},
    )


@router.get("/notas/{nota_id}/danfe")
async def download_danfe(
    nota_id: UUID,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    nota = await NotaRepository(session).by_id(nota_id)
    if nota is None or not nota.storage_key:
        raise NotFoundError("XML não disponível para gerar a DANFE.")
    try:
        xml = get_storage().get(nota.storage_key).decode("utf-8", errors="ignore")
    except Exception as exc:  # noqa: BLE001
        raise NotFoundError("Arquivo XML não encontrado no storage.") from exc
    pdf, err = await run_in_threadpool(gerar_danfe, xml)
    if not pdf:
        raise DomainError(err or "Falha ao gerar a DANFE.", code="danfe_error")
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nota.chave_acesso}.pdf"'},
    )
