"""Exportação/Importação em lote das Matrizes Fiscais (planilha CSV).

Fluxo do Go-Live: o usuário baixa a base (ou o template, se vazia), edita no
Excel e sobe de volta. O upsert reaproveita os MESMOS schemas do CRUD para
validar linha a linha (tipos, UF, regime, vigência) — erro de uma linha não
derruba o lote: vira um relatório por número de linha.

CSV em `;` (Excel-BR) com BOM UTF-8 para abrir acentuado direto no Excel.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date

from fastapi import APIRouter, Depends, File, UploadFile
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.exceptions import NotFoundError
from app.core.rbac import Role, require_role
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.fiscal.api.matrizes_schemas import (
    MatrizEnquadramentoCreate,
    MatrizFcpCreate,
    MatrizMvaCreate,
    MatrizProtocoloCreate,
)
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)

router = APIRouter(prefix="/matrizes", tags=["Matrizes Fiscais"])


@dataclass(frozen=True)
class _Spec:
    modelo: type
    schema: type[BaseModel]
    chave: tuple[str, ...]      # campos que identificam a linha (upsert)

    @property
    def colunas(self) -> list[str]:
        return list(self.schema.model_fields.keys())


# Cada matriz: model + schema de validação (reuso do CRUD) + chave de upsert
# (inclui a vigência — ADR-0002 — para não colidir versões da mesma regra).
MATRIZES: dict[str, _Spec] = {
    "mva": _Spec(MatrizMva, MatrizMvaCreate, ("ncm", "cest", "uf_destino", "data_inicio_vigencia")),
    "enquadramento": _Spec(
        MatrizEnquadramentoSt, MatrizEnquadramentoCreate,
        ("uf_destino", "ncm", "cest", "data_inicio_vigencia"),
    ),
    "fcp": _Spec(MatrizFcp, MatrizFcpCreate, ("uf_destino", "ncm", "data_inicio_vigencia")),
    "protocolos": _Spec(
        MatrizProtocoloSt, MatrizProtocoloCreate,
        ("uf_origem", "uf_destino", "numero_acordo", "data_inicio_vigencia"),
    ),
}

_NUM_VIRGULA = re.compile(r"^\d+,\d+$")   # "42,00" (Excel-BR) -> "42.00"


def _spec(tipo: str) -> _Spec:
    spec = MATRIZES.get(tipo)
    if spec is None:
        raise NotFoundError(f"Matriz '{tipo}' não existe (use: {', '.join(MATRIZES)}).")
    return spec


def _fmt(v) -> str:
    if v is None:
        return ""
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _resumo_erro(e: ValidationError) -> str:
    return "; ".join(
        f"{'.'.join(str(x) for x in err['loc'])}: {err['msg']}" for err in e.errors()[:3]
    )


async def exportar_csv(session: AsyncSession, tipo: str) -> str:
    """CSV com cabeçalho + linhas. Tabela vazia → só o cabeçalho (= template)."""
    spec = _spec(tipo)
    cols = spec.colunas
    rows = (await session.execute(select(spec.modelo))).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_fmt(getattr(r, c)) for c in cols])
    return buf.getvalue()


async def importar_csv(session: AsyncSession, tipo: str, conteudo: bytes) -> dict:
    """Valida cada linha pelo schema e faz upsert por chave. Retorna o resumo
    com a lista de erros (linha + motivo) — nenhuma linha ruim derruba o lote."""
    spec = _spec(tipo)
    cols = spec.colunas
    texto = conteudo.decode("utf-8-sig", errors="replace")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")

    erros: list[dict] = []
    validos: list[dict] = []
    for i, linha in enumerate(leitor, start=2):   # linha 1 = cabeçalho
        bruto = {}
        for c in cols:
            v = (linha.get(c) or "").strip()
            v = v.replace(",", ".") if _NUM_VIRGULA.match(v) else v
            bruto[c] = v or None                  # vazio → None (campos opcionais)
        try:
            validos.append(spec.schema(**bruto).normalizado())
        except ValidationError as e:
            erros.append({"linha": i, "erro": _resumo_erro(e)})

    resumo = await _upsert(session, spec, validos)
    return {"tipo": tipo, "linhas_validas": len(validos), **resumo, "erros": erros}


async def _upsert(session: AsyncSession, spec: _Spec, validos: list[dict]) -> dict:
    # Pré-carrega a matriz inteira (tabelas pequenas) e indexa por chave — sem N+1.
    existentes: dict[tuple, object] = {}
    for obj in (await session.execute(select(spec.modelo))).scalars():
        existentes[tuple(getattr(obj, k) for k in spec.chave)] = obj

    nao_chave = [c for c in spec.colunas if c not in spec.chave]
    inseridos = atualizados = 0
    for d in validos:
        chave = tuple(d[k] for k in spec.chave)
        atual = existentes.get(chave)
        if atual is not None:
            for c in nao_chave:
                setattr(atual, c, d[c])
            atualizados += 1
        else:
            novo = spec.modelo(**d)
            session.add(novo)
            existentes[chave] = novo              # evita duplicar dentro do mesmo arquivo
            inseridos += 1
    await session.flush()
    return {"inseridos": inseridos, "atualizados": atualizados}


@router.get("/{tipo}/export")
async def exportar_matriz(
    tipo: str,
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    csv_text = await exportar_csv(session, tipo)
    return Response(
        content="﻿" + csv_text,              # BOM → Excel abre com acentos
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="matriz_{tipo}.csv"'},
    )


@router.post("/{tipo}/import")
async def importar_matriz(
    tipo: str,
    arquivo: UploadFile = File(...),
    claims: TokenClaims = Depends(require_role(Role.SUPERVISOR)),
    session: AsyncSession = Depends(tenant_session),
):
    conteudo = await arquivo.read()
    return await importar_csv(session, tipo, conteudo)
