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
from datetime import UTC, date, datetime

from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.domain.vigencia import intervalos_conflitam

_NUM_VIRGULA = re.compile(r"^\d+,\d+$")


class LinhaIgnorada(Exception):
    """A linha é válida, mas o usuário DEIXOU EM BRANCO a decisão que ela pede.

    Não é erro (não houve engano) nem cadastro (nada entra por omissão): a linha
    volta no resumo como "ignorada", com o motivo. Nasceu da lista de candidatos
    a Exceção de Item, que sai com `tributado_icms` vazio de propósito — quem
    decide se o produto é tributado é a pessoa, nunca o preenchimento default.
    """

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


@dataclass(frozen=True)
class BulkSpec:
    modelo: type
    schema: type[BaseModel]
    chave: tuple[str, ...]                                   # campos que identificam a linha
    # Como obter o dict de persistência do schema validado (default: model_dump).
    # Pode levantar ValueError (linha recusada, vira erro relatado) ou
    # LinhaIgnorada (linha em branco de propósito, vira "ignorada").
    normalizar: Callable[[BaseModel], dict] = field(default=lambda obj: obj.model_dump())
    # Famílias de vigência (ADR-0002) quando o MODELO não declara CHAVE_VIGENCIA
    # — o caso das tabelas cuja chave depende do contexto (tenant/empresa).
    chave_vigencia: tuple[str, ...] | None = None
    # Como renderizar cada coluna na EXPORTAÇÃO. O default lê o atributo homônimo;
    # tabelas com coluna derivada (ex.: cnpj_empresa a partir de empresa_id) ou
    # com booleano em português (SIM/NAO) trocam este hook.
    exportar_valor: Callable[[object, str], object] = field(
        default=lambda obj, coluna: getattr(obj, coluna)
    )

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


async def exportar_csv(session: AsyncSession, spec: BulkSpec, *, filtros=()) -> str:
    """CSV com cabeçalho + linhas. Tabela vazia → só o cabeçalho (= template).

    `filtros` são critérios SQLAlchemy opcionais (ex.: uma empresa só). O recorte
    por tenant continua sendo do RLS — nunca de um filtro que o chamador possa
    esquecer de passar.
    """
    cols = spec.colunas
    stmt = select(spec.modelo)
    if filtros:
        stmt = stmt.where(*filtros)
    rows = (await session.execute(stmt)).scalars().all()
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(cols)
    for r in rows:
        w.writerow([_fmt(spec.exportar_valor(r, c)) for c in cols])
    return buf.getvalue()


async def importar_csv(session: AsyncSession, spec: BulkSpec, conteudo: bytes) -> dict:
    """Valida cada linha pelo schema e faz upsert por chave. Retorna o resumo
    com a lista de erros (linha + motivo) — nenhuma linha ruim derruba o lote."""
    cols = spec.colunas
    texto = conteudo.decode("utf-8-sig", errors="replace")
    leitor = csv.DictReader(io.StringIO(texto), delimiter=";")

    erros: list[dict] = []
    ignoradas: list[dict] = []
    validos: list[tuple[int, dict]] = []            # (nº da linha no arquivo, dados)
    for i, linha in enumerate(leitor, start=2):     # linha 1 = cabeçalho
        bruto = {}
        for c in cols:
            v = (linha.get(c) or "").strip()
            if not v:
                continue                            # omite → schema aplica default / acusa se required
            bruto[c] = v.replace(",", ".") if _NUM_VIRGULA.match(v) else v
        try:
            validos.append((i, spec.normalizar(spec.schema(**bruto))))
        except LinhaIgnorada as e:
            ignoradas.append({"linha": i, "motivo": e.motivo})
        except ValidationError as e:
            erros.append({"linha": i, "erro": _resumo_erro(e)})
        except ValueError as e:                     # recusa do `normalizar` (ADR: linha ≠ lote)
            erros.append({"linha": i, "erro": str(e)})

    resumo = await _upsert(session, spec, validos, erros)
    return {
        "linhas_validas": len(validos), **resumo,
        "ignoradas": ignoradas, "erros": erros,
    }


async def _upsert(
    session: AsyncSession, spec: BulkSpec, validos: list[tuple[int, dict]], erros: list[dict]
) -> dict:
    existentes: dict[tuple, object] = {}
    for obj in (await session.execute(select(spec.modelo))).scalars():
        existentes[tuple(getattr(obj, k) for k in spec.chave)] = obj

    # Modelos com vigência (ADR-0002) validam a não-sobreposição por família:
    # linha que conflita vira erro relatado (linha + motivo), não entra no lote.
    chave_vig: tuple[str, ...] | None = (
        spec.chave_vigencia or getattr(spec.modelo, "CHAVE_VIGENCIA", None)
    )
    familias: dict[tuple, list] = {}
    if chave_vig:
        for obj in existentes.values():
            familias.setdefault(tuple(getattr(obj, c) for c in chave_vig), []).append(obj)

    nao_chave = [c for c in spec.colunas if c not in spec.chave]
    inseridos = atualizados = 0
    for linha_num, d in validos:
        chave = tuple(d[k] for k in spec.chave)
        atual = existentes.get(chave)
        if chave_vig:
            fam = familias.get(tuple(d[c] for c in chave_vig), [])
            conflito = next(
                (o for o in fam if o is not atual and intervalos_conflitam(
                    o.data_inicio_vigencia, o.data_fim_vigencia,
                    d["data_inicio_vigencia"], d.get("data_fim_vigencia"),
                )),
                None,
            )
            if conflito is not None:
                fim = conflito.data_fim_vigencia or "em aberto"
                erros.append({
                    "linha": linha_num,
                    "erro": "vigência sobrepõe linha existente "
                            f"({conflito.data_inicio_vigencia} – {fim}) — "
                            "encerre a vigência antiga e insira uma nova (ADR-0002)",
                })
                continue
        if atual is not None:
            for c in nao_chave:
                if c in d:
                    setattr(atual, c, d[c])
            # Reimportar a linha = reconferir (só nas tabelas com o carimbo).
            if hasattr(atual, "ultima_verificacao_em"):
                atual.ultima_verificacao_em = datetime.now(UTC)
            atualizados += 1
        else:
            # O dict vem do `normalizar` do spec (confiável): pode carregar
            # campos ALÉM das colunas da planilha — ex.: tenant_id injetado
            # para tabelas com RLS (empresas), que o CSV nunca expõe.
            novo = spec.modelo(**d)
            session.add(novo)
            existentes[chave] = novo                # evita duplicar dentro do mesmo arquivo
            if chave_vig:
                familias.setdefault(tuple(d[c] for c in chave_vig), []).append(novo)
            inseridos += 1
    await session.flush()
    return {"inseridos": inseridos, "atualizados": atualizados}
