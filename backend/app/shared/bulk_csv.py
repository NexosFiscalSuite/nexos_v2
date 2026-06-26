"""Núcleo genérico de Exportação/Importação em lote via planilha CSV.

Dirigido por um `BulkSpec` (modelo + schema de validação + chave de upsert), serve
qualquer tabela de regras (Matrizes, De/Para CFOP). Reaproveita o schema do CRUD
para validar linha a linha; erro de uma linha vira relatório (linha+motivo), não
derruba o lote. CSV em `;` (Excel-BR) e vírgula decimal normalizada.
"""
from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

_NUM_VIRGULA = re.compile(r"^\d+,\d+$")


@dataclass(frozen=True)
class BulkSpec:
    modelo: type
    schema: type[BaseModel]
    chave: tuple[str, ...]                                   # campos que identificam a linha
    # Como obter o dict de persistência do schema validado (default: model_dump).
    normalizar: Callable[[BaseModel], dict] = field(default=lambda obj: obj.model_dump())

    @property
    def colunas(self) -> list[str]:
        return list(self.schema.model_fields.keys())


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


async def exportar_csv(session: AsyncSession, spec: BulkSpec) -> str:
    """CSV com cabeçalho + linhas. Tabela vazia → só o cabeçalho (= template)."""
    cols = spec.colunas
    rows = (await session.execute(select(spec.modelo))).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_fmt(getattr(r, c)) for c in cols])
    return buf.getvalue()


async def importar_csv(session: AsyncSession, spec: BulkSpec, conteudo: bytes) -> dict:
    """Valida cada linha pelo schema e faz upsert por chave. Retorna o resumo
    com a lista de erros (linha + motivo) — nenhuma linha ruim derruba o lote."""
    cols = spec.colunas
    texto = conteudo.decode("utf-8-sig", errors="replace")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")

    erros: list[dict] = []
    validos: list[dict] = []
    for i, linha in enumerate(leitor, start=2):     # linha 1 = cabeçalho
        bruto = {}
        for c in cols:
            v = (linha.get(c) or "").strip()
            if not v:
                continue                            # omite → schema aplica default / acusa se required
            bruto[c] = v.replace(",", ".") if _NUM_VIRGULA.match(v) else v
        try:
            validos.append(spec.normalizar(spec.schema(**bruto)))
        except ValidationError as e:
            erros.append({"linha": i, "erro": _resumo_erro(e)})

    resumo = await _upsert(session, spec, validos)
    return {"linhas_validas": len(validos), **resumo, "erros": erros}


async def _upsert(session: AsyncSession, spec: BulkSpec, validos: list[dict]) -> dict:
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
                if c in d:
                    setattr(atual, c, d[c])
            atualizados += 1
        else:
            novo = spec.modelo(**{c: d[c] for c in spec.colunas if c in d})
            session.add(novo)
            existentes[chave] = novo                # evita duplicar dentro do mesmo arquivo
            inseridos += 1
    await session.flush()
    return {"inseridos": inseridos, "atualizados": atualizados}
