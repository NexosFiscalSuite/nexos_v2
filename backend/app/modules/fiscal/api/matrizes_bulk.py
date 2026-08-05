"""Exportação/Importação em lote das Matrizes Fiscais (planilha CSV).

A lógica genérica vive em app.shared.bulk_csv; aqui só o registry das 4 matrizes
(modelo + schema + chave de upsert) e os endpoints.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.exceptions import NotFoundError
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.fiscal.api.curadoria import require_curador
from app.modules.fiscal.api.matrizes_schemas import (
    MatrizAliquotaCreate,
    MatrizEnquadramentoCreate,
    MatrizFcpCreate,
    MatrizMvaCreate,
    MatrizProtocoloCreate,
)
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.shared.bulk_csv import BulkSpec, exportar_csv, importar_csv

router = APIRouter(prefix="/matrizes", tags=["Matrizes Fiscais"])

_NORM = lambda o: o.normalizado()   # noqa: E731 — os schemas de matriz têm normalizado()

# Cada matriz: model + schema (reuso do CRUD) + chave de upsert (com vigência, ADR-0002).
MATRIZES: dict[str, BulkSpec] = {
    "mva": BulkSpec(MatrizMva, MatrizMvaCreate,
                    ("ncm", "cest", "uf_destino", "data_inicio_vigencia"), _NORM),
    "enquadramento": BulkSpec(MatrizEnquadramentoSt, MatrizEnquadramentoCreate,
                              ("uf_destino", "ncm", "cest", "data_inicio_vigencia"), _NORM),
    "fcp": BulkSpec(MatrizFcp, MatrizFcpCreate,
                    ("uf_destino", "ncm", "data_inicio_vigencia"), _NORM),
    "protocolos": BulkSpec(MatrizProtocoloSt, MatrizProtocoloCreate,
                           ("uf_origem", "uf_destino", "numero_acordo", "ncm", "data_inicio_vigencia"), _NORM),
    "aliquotas": BulkSpec(MatrizAliquota, MatrizAliquotaCreate,
                          ("uf_destino", "data_inicio_vigencia"), _NORM),
}


def _spec(tipo: str) -> BulkSpec:
    spec = MATRIZES.get(tipo)
    if spec is None:
        raise NotFoundError(f"Matriz '{tipo}' não existe (use: {', '.join(MATRIZES)}).")
    return spec


@router.get("/{tipo}/export")
async def exportar_matriz(
    tipo: str,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    csv_text = await exportar_csv(session, _spec(tipo))
    return Response(
        content="﻿" + csv_text,                  # BOM → Excel abre com acentos
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="matriz_{tipo}.csv"'},
    )


@router.post("/{tipo}/import")
async def importar_matriz(
    tipo: str,
    arquivo: UploadFile = File(...),
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    resumo = await importar_csv(session, _spec(tipo), await arquivo.read())
    return {"tipo": tipo, **resumo}
