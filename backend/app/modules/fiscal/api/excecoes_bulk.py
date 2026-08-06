"""Exceções de Item em LOTE (planilha CSV), por empresa e por FORNECEDOR.

Por que existe
--------------
A Exceção de Item é a decisão "este produto é tributado normalmente, apesar de o
NCM/CST da nota dizer ST". Cadastrar isso um a um pela tela não escala: um
cliente tem centenas de itens nessa situação. Aqui o escritório baixa a lista,
decide na planilha e sobe de volta.

O código do produto (cProd) é do FORNECEDOR, não do mundo: dois fornecedores
usam códigos diferentes para o mesmo produto e — pior — o MESMO código para
produtos distintos. Por isso a planilha tem `cnpj_fornecedor`; em branco, a
regra vale para qualquer fornecedor.

As três pontas
--------------
- `GET  /matrizes/excecoes-produto/candidatos` — a lista REAL de trabalho: os
  itens já importados que o motor tratou como ST, agrupados por fornecedor +
  código, ordenados por dinheiro. Sai no MESMO layout do import, com a coluna
  `tributado_icms` VAZIA de propósito.
- `POST /matrizes/excecoes-produto/import` — sobe a planilha. Linha com
  `tributado_icms` em branco é IGNORADA (não cadastra): nada entra por omissão,
  quem decide o que é tributado é a pessoa.
- `GET  /matrizes/excecoes-produto/export` — a base atual (vazia = só o
  cabeçalho, que serve de template).

A empresa entra pelo CNPJ, nunca pelo UUID — ninguém digita UUID em planilha; o
CNPJ é resolvido DENTRO do tenant e, se não existir, a linha vira erro relatado
(o import de exceções jamais cadastra empresa). O `tenant_id` nunca vem da
planilha: é sempre injetado dos claims (regra 1 do CLAUDE.md).
"""
from __future__ import annotations

import csv
import io
from collections.abc import Sequence
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from pydantic import BaseModel, BeforeValidator, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from app.core.exceptions import DomainError
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.companies.infrastructure.models import Empresa
from app.modules.fiscal.api.curadoria import require_curador
from app.modules.fiscal.application.reprocess_service import ReprocessService
from app.modules.fiscal.infrastructure.models import (
    AuditoriaIcmsSt,
    ExcecaoEnquadramentoStProduto,
    Nota,
    NotaItem,
)
from app.shared.bulk_csv import BulkSpec, LinhaIgnorada, exportar_csv, importar_csv
from app.shared.domain.value_objects import DocumentoFiscal, only_digits

router = APIRouter(prefix="/matrizes", tags=["Matrizes Fiscais"])


# ── SIM/NÃO da planilha ──────────────────────────────────────────────────────
# Excel-BR, colega apressado e export do sistema escrevem a mesma coisa de seis
# jeitos. Aceitamos todos na entrada; o que não dá para reconhecer vira erro de
# linha (nunca um "False" por palpite, que aqui significaria mandar cobrar ST).
_SIM = {"sim", "s", "true", "t", "1", "verdadeiro", "v", "x"}
_NAO = {"nao", "não", "n", "false", "f", "0", "falso"}


def _sim_nao(valor: object) -> object:
    if valor is None or isinstance(valor, bool):
        return valor
    texto = str(valor).strip().lower()
    if not texto:
        return None                       # em branco = decisão não tomada
    if texto in _SIM:
        return True
    if texto in _NAO:
        return False
    raise ValueError(f"'{valor}' não é SIM nem NAO (também aceita true/false e 1/0)")


#: SIM/NAO obrigatório (tem default no schema).
SimNao = Annotated[bool, BeforeValidator(_sim_nao)]
#: SIM/NAO que ADMITE branco — branco quer dizer "ainda não decidi".
SimNaoOuBranco = Annotated[bool | None, BeforeValidator(_sim_nao)]


def _documento(valor: str, campo: str) -> str:
    try:
        return DocumentoFiscal(valor).value
    except DomainError as e:
        raise ValueError(f"{campo}: {getattr(e, 'message', None) or e}") from e


class ExcecaoLinha(BaseModel):
    """Uma linha da planilha — a ORDEM dos campos é a ordem das colunas do CSV.

    Contrato fechado com a tela (o front monta o template a partir daqui):
    cnpj_empresa;cnpj_fornecedor;codigo_produto;descricao_produto;ncm;
    tributado_icms;lei_icms;data_inicio_vigencia;data_fim_vigencia;ativo
    """

    cnpj_empresa: str = Field(
        ..., examples=["11.444.777/0001-61"],
        description="CNPJ (ou CPF/CEI) da EMPRESA do escritório, com ou sem "
                    "pontuação. Precisa já estar cadastrada — o import de "
                    "exceções nunca cria empresa.",
    )
    cnpj_fornecedor: str = Field(
        default="", examples=["04.640.241/0001-56", ""],
        description="CNPJ/CPF do fornecedor que usa esse código de produto. "
                    "Em branco = vale para qualquer fornecedor.",
    )
    codigo_produto: str = Field(..., min_length=1, max_length=60, examples=["7891"])
    descricao_produto: str | None = Field(default=None, max_length=500)
    ncm: str | None = Field(default=None, max_length=10)
    tributado_icms: SimNaoOuBranco = Field(
        default=None, examples=["SIM"],
        description="SIM = o produto é tributado normalmente (não é ST). "
                    "NAO = segue sujeito ao ICMS-ST. EM BRANCO = a linha é "
                    "IGNORADA, nada é cadastrado.",
    )
    lei_icms: str | None = Field(
        default=None, max_length=2000,
        description="Base normativa que sustenta a decisão (vai para a carta).",
    )
    data_inicio_vigencia: date = Field(..., examples=["2026-01-01"])
    data_fim_vigencia: date | None = Field(default=None, examples=[""])
    ativo: SimNao = Field(default=True, examples=["SIM"])

    @field_validator("cnpj_empresa")
    @classmethod
    def _empresa_valida(cls, v: str) -> str:
        return _documento(v, "cnpj_empresa")

    @field_validator("cnpj_fornecedor")
    @classmethod
    def _fornecedor_valido(cls, v: str) -> str:
        return _documento(v, "cnpj_fornecedor") if (v or "").strip() else ""

    @field_validator("data_fim_vigencia")
    @classmethod
    def _periodo_valido(cls, v: date | None, info):
        inicio = info.data.get("data_inicio_vigencia")
        if v is not None and inicio is not None and v < inicio:
            raise ValueError("data final não pode ser anterior à inicial")
        return v


#: Cabeçalho oficial do CSV — a fonte única é o schema (o front lê daqui).
COLUNAS_CSV_EXCECOES: tuple[str, ...] = tuple(ExcecaoLinha.model_fields.keys())


def _persistir(
    linha: ExcecaoLinha, *, tenant_id: UUID, empresas: dict[str, UUID], autor: str,
    afetados: set[tuple[UUID, str]] | None = None,
) -> dict:
    """Schema validado → dict de persistência. Recusa a linha (ValueError) ou a
    ignora (LinhaIgnorada) quando não há decisão a gravar."""
    if linha.tributado_icms is None:
        raise LinhaIgnorada(
            "coluna 'tributado_icms' em branco — escreva SIM (produto tributado) "
            "ou NAO (segue em ST) para esta linha valer"
        )
    empresa_id = empresas.get(linha.cnpj_empresa)
    if empresa_id is None:
        raise ValueError(
            f"cnpj_empresa: {DocumentoFiscal(linha.cnpj_empresa).formatted} não "
            "está cadastrado neste escritório — cadastre a empresa antes de "
            "importar as exceções dela"
        )
    dados = linha.model_dump()
    dados.pop("cnpj_empresa")
    dados["empresa_id"] = empresa_id
    dados["tenant_id"] = tenant_id                    # SEMPRE dos claims
    dados["definido_por"] = autor
    dados["codigo_produto"] = linha.codigo_produto.strip().upper()
    dados["ncm"] = only_digits(linha.ncm or "") or None
    dados["descricao_produto"] = (linha.descricao_produto or "").strip() or None
    dados["lei_icms"] = (linha.lei_icms or "").strip() or None
    if afetados is not None:
        afetados.add((empresa_id, dados["codigo_produto"]))
    return dados


async def _empresas_do_tenant(session: AsyncSession, tenant_id: UUID) -> dict[str, UUID]:
    """CNPJ → id das empresas do escritório (o RLS já recorta; o filtro
    explícito mantém o mesmo comportamento fora do Postgres, nos testes)."""
    linhas = await session.execute(
        select(Empresa.cnpj, Empresa.id).where(Empresa.tenant_id == tenant_id)
    )
    return {only_digits(cnpj): eid for cnpj, eid in linhas}


async def spec_excecoes(
    session: AsyncSession, tenant_id: UUID, autor: str = "",
    afetados: set[tuple[UUID, str]] | None = None,
) -> BulkSpec:
    """Spec por requisição: o tenant do usuário logado entra em toda linha criada
    e o mapa de empresas resolve o CNPJ da planilha para o `empresa_id`.

    `afetados` (opcional) recolhe os pares (empresa, código) que a planilha
    tocou — é o que o import usa depois para reauditar as notas certas.
    """
    empresas = await _empresas_do_tenant(session, tenant_id)
    por_id = {eid: cnpj for cnpj, eid in empresas.items()}

    def exportar_valor(obj, coluna: str):
        if coluna == "cnpj_empresa":
            return por_id.get(obj.empresa_id, "")
        if coluna in ("tributado_icms", "ativo"):
            return "SIM" if getattr(obj, coluna) else "NAO"
        return getattr(obj, coluna)

    return BulkSpec(
        ExcecaoEnquadramentoStProduto,
        ExcecaoLinha,
        chave=("empresa_id", "cnpj_fornecedor", "codigo_produto", "data_inicio_vigencia"),
        normalizar=lambda o: _persistir(
            o, tenant_id=tenant_id, empresas=empresas, autor=autor, afetados=afetados
        ),
        # ADR-0002: duas vigências abertas para o mesmo (empresa, fornecedor,
        # código) tornariam a busca do motor ambígua — a segunda vira erro de
        # linha, com a instrução de encerrar a antiga.
        chave_vigencia=("empresa_id", "cnpj_fornecedor", "codigo_produto"),
        exportar_valor=exportar_valor,
    )


# ── Candidatos: a lista real de trabalho ─────────────────────────────────────
def _primeiro_do_mes(iso: str | None) -> str:
    """'2026-06-17' → '2026-06-01'. Só recorta a data que JÁ está na nota: é
    sugestão de início de vigência para a planilha, não afirmação de norma."""
    try:
        d = date.fromisoformat((iso or "")[:10])
    except ValueError:
        d = date.today()
    return d.replace(day=1).isoformat()


async def candidatos_excecao(
    session: AsyncSession,
    tenant_id: UUID,
    *,
    empresa_id: UUID | None = None,
    ano: str | None = None,
    mes: str | None = None,
) -> list[dict]:
    """Itens já importados que o motor tratou como ST, por fornecedor + código.

    "Tratado como ST" = a auditoria calculou base/ICMS-ST para o item OU a nota
    veio com ST destacado (o caso do João: produto com NCM e CST de ST que, na
    verdade, é tributado). Item sem auditoria não entra — o candidato nasce de
    uma decisão do motor, nunca de um chute sobre o NCM.

    Sai de fora o que JÁ tem exceção cadastrada (do fornecedor ou genérica):
    a lista é fila de trabalho, não inventário.

    Ordem: dinheiro primeiro (valor), depois quantidade de itens — o mesmo
    critério do relatório de lacunas de MVA.
    """
    n, it, au = Nota, NotaItem, AuditoriaIcmsSt
    stmt = (
        select(
            n.empresa_id.label("empresa_id"),
            func.coalesce(n.cnpj_emit, "").label("cnpj_fornecedor"),
            func.upper(func.trim(it.codigo)).label("codigo"),
            func.min(it.descricao).label("descricao"),
            func.min(it.ncm).label("ncm"),
            func.count(it.id).label("itens"),
            func.count(func.distinct(it.nota_id)).label("notas"),
            func.coalesce(func.sum(it.valor_produto), 0).label("valor"),
            func.min(n.data_emissao).label("emissao_min"),
        )
        .join(n, it.nota_id == n.id)
        .join(au, (au.nota_id == n.id) & (au.numero_item == it.numero_item))
        .where(
            n.status == "ativa",
            n.fluxo.in_(("entrada", "saida")),
            it.codigo.isnot(None), it.codigo != "",
            or_(
                au.vbc_st_calculado > 0, au.vicms_st_calculado > 0,
                au.vbc_st_xml > 0, au.vicms_st_xml > 0,
            ),
        )
        .group_by(n.empresa_id, func.coalesce(n.cnpj_emit, ""),
                  func.upper(func.trim(it.codigo)))
    )
    if empresa_id:
        stmt = stmt.where(n.empresa_id == empresa_id)
    if ano:
        stmt = stmt.where(n.ano == ano)
    if mes:
        stmt = stmt.where(n.mes == mes)

    ja_cadastrados = {
        (e, f, c)
        for e, f, c in await session.execute(
            select(
                ExcecaoEnquadramentoStProduto.empresa_id,
                ExcecaoEnquadramentoStProduto.cnpj_fornecedor,
                func.upper(func.trim(ExcecaoEnquadramentoStProduto.codigo_produto)),
            )
        )
    }
    cnpj_da_empresa = {
        eid: cnpj for cnpj, eid in (await _empresas_do_tenant(session, tenant_id)).items()
    }

    linhas: list[dict] = []
    for r in (await session.execute(stmt)).mappings().all():
        fornecedor = only_digits(r["cnpj_fornecedor"] or "")
        codigo = (r["codigo"] or "").strip().upper()
        # Regra do fornecedor OU regra genérica já resolvem este código.
        if {(r["empresa_id"], fornecedor, codigo),
                (r["empresa_id"], "", codigo)} & ja_cadastrados:
            continue
        linhas.append({
            "cnpj_empresa": cnpj_da_empresa.get(r["empresa_id"], ""),
            "cnpj_fornecedor": fornecedor,
            "codigo_produto": codigo,
            "descricao_produto": (r["descricao"] or "")[:120],
            "ncm": only_digits(r["ncm"] or ""),
            "itens": int(r["itens"]),
            "notas": int(r["notas"]),
            "valor": float(r["valor"] or 0),
            "data_inicio_vigencia": _primeiro_do_mes(r["emissao_min"]),
        })
    linhas.sort(key=lambda g: (g["valor"], g["itens"]), reverse=True)
    return linhas


def candidatos_csv(linhas: Sequence[dict]) -> str:
    """A lista de candidatos no layout EXATO do importador.

    `tributado_icms` sai em branco de propósito: o arquivo é um questionário, não
    um cadastro pronto. Escreva SIM só nos itens que são tributados de verdade e
    suba — o importador ignora (e conta) as linhas que continuarem em branco.
    """
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    w.writerow(COLUNAS_CSV_EXCECOES)
    for g in linhas:
        w.writerow([
            g["cnpj_empresa"], g["cnpj_fornecedor"], g["codigo_produto"],
            g["descricao_produto"], g["ncm"],
            "",                                  # tributado_icms — só a pessoa decide
            "",                                  # lei_icms — base normativa
            g["data_inicio_vigencia"], "",
            "SIM",
        ])
    return buf.getvalue()


def _csv_response(texto: str, nome: str) -> Response:
    return Response(
        content="﻿" + texto,               # BOM → Excel abre com acentos
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/excecoes-produto/export")
async def exportar_excecoes(
    empresa_id: UUID | None = Query(default=None),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Planilha das exceções já cadastradas (vazia = template com o cabeçalho).

    Edite e suba de volta pelo "Importar planilha": o upsert é por empresa +
    fornecedor + código + início de vigência.
    """
    spec = await spec_excecoes(session, claims.tid)
    filtros = (
        (ExcecaoEnquadramentoStProduto.empresa_id == empresa_id,) if empresa_id else ()
    )
    return _csv_response(
        await exportar_csv(session, spec, filtros=filtros), "excecoes_item.csv"
    )


@router.get("/excecoes-produto/candidatos")
async def candidatos_excecoes(
    empresa_id: UUID | None = Query(default=None),
    ano: str | None = Query(default=None, examples=["2026"]),
    mes: str | None = Query(default=None, examples=["07"]),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Os itens que o motor tratou como ST, prontos para virar exceção.

    Sai no MESMO layout do import, ordenado por dinheiro, com a coluna
    `tributado_icms` VAZIA — o arquivo pergunta, não responde.
    """
    linhas = await candidatos_excecao(
        session, claims.tid, empresa_id=empresa_id, ano=ano, mes=mes
    )
    return _csv_response(candidatos_csv(linhas), "excecoes_candidatos.csv")


@router.post("/excecoes-produto/import")
async def importar_excecoes(
    arquivo: UploadFile = File(...),
    reprocessar: bool = Query(
        default=True,
        description="Reaudita as notas dos produtos afetados logo após a carga. "
                    "Desligue em lotes muito grandes e rode o reprocessamento "
                    "depois — a auditoria fica desatualizada até lá.",
    ),
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    """Cadastro em lote das Exceções de Item.

    Upsert por empresa + fornecedor + código + início de vigência. Linha com
    `tributado_icms` em branco é IGNORADA (nada entra por omissão) e volta no
    resumo em `ignoradas`; linha ruim vira erro relatado (linha + motivo) sem
    derrubar o lote.
    """
    afetados: set[tuple[UUID, str]] = set()
    spec = await spec_excecoes(
        session, claims.tid, autor=str(claims.sub), afetados=afetados
    )
    resumo = await importar_csv(session, spec, await arquivo.read())

    # A exceção MUDA a decisão fiscal de notas já auditadas: sem reauditar, a
    # tela continuaria mostrando ST em item que o escritório acabou de declarar
    # tributado. Deduplicado por (empresa, código) — o motor reaudita a nota
    # inteira de qualquer forma.
    notas = 0
    if reprocessar:
        servico = ReprocessService(session)
        for empresa_id, codigo in afetados:
            notas += (await servico.reprocessar_produto(empresa_id, codigo))[
                "notas_reprocessadas"
            ]
    resumo["notas_reprocessadas"] = notas

    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="excecao_st_produto.importar",
        entidade="excecao_st_produto",
        detalhe={
            "inseridos": resumo.get("inseridos"),
            "atualizados": resumo.get("atualizados"),
            "ignoradas": len(resumo.get("ignoradas") or []),
            "erros": len(resumo.get("erros") or []),
            "notas_reprocessadas": notas,
        },
    )
    return resumo
