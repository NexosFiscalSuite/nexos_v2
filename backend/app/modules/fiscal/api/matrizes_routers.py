"""CRUD de Matrizes Fiscais — tabelas GLOBAIS (sem RLS): MVA, Enquadramento,
FCP, Protocolos e Alíquotas.

Leitura: qualquer usuário autenticado. Escrita: também aberta a qualquer
usuário autenticado (`require_curador` — a curadoria é trabalho diário dos
analistas); `NEXOS_MATRIZ_CURADORES` preenchido vira freio de emergência por
e-mail. Um factory registra os 4 verbos por matriz para não repetir o mesmo
CRUD cinco vezes.
"""
from collections.abc import Callable
from datetime import UTC, date, datetime
from typing import Generic, TypeVar
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import Base
from app.core.exceptions import ConflictError, NotFoundError
from app.core.rls import tenant_session
from app.core.security import TokenClaims, get_current_claims
from app.modules.audit.application.service import AuditService
from app.modules.companies.infrastructure.models import Empresa
from app.modules.fiscal.api.curadoria import require_curador
from app.modules.fiscal.api.matrizes_schemas import (
    ExcecaoProdutoCreate,
    ExcecaoProdutoResponse,
    ExcecaoProdutoUpdate,
    MatrizAliquotaCreate,
    MatrizAliquotaResponse,
    MatrizAliquotaUpdate,
    MatrizEnquadramentoCreate,
    MatrizEnquadramentoResponse,
    MatrizEnquadramentoUpdate,
    MatrizFcpCreate,
    MatrizFcpResponse,
    MatrizFcpUpdate,
    MatrizMvaCreate,
    MatrizMvaResponse,
    MatrizMvaUpdate,
    MatrizProtocoloCreate,
    MatrizProtocoloResponse,
    MatrizProtocoloUpdate,
)
from app.modules.fiscal.application.cobertura_service import CoberturaService
from app.modules.fiscal.application.matrizes_saude import saude_matrizes
from app.modules.fiscal.application.pares_interestaduais import pares_interestaduais
from app.modules.fiscal.application.reprocess_service import ReprocessService
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.models import ExcecaoEnquadramentoStProduto
from app.modules.fiscal.infrastructure.vigencia import sobreposicao_existente
from app.shared.domain.value_objects import only_digits

router = APIRouter(prefix="/matrizes", tags=["Matrizes Fiscais"])

T = TypeVar("T")


class Pagina(BaseModel, Generic[T]):
    """Envelope de paginação das listagens. A base auto-alimentada (crawler
    CONFAZ × 7 UFs) tem dezenas de milhares de linhas — a tela pagina no
    servidor em vez de carregar tudo de uma vez."""

    items: list[T]
    total: int
    page: int
    page_size: int


async def _empresa_do_tenant(session: AsyncSession, empresa_id: UUID) -> Empresa:
    empresa = await session.get(Empresa, empresa_id)
    if empresa is None:
        raise NotFoundError("Empresa não encontrada.")
    return empresa


@router.get("/excecoes-produto", response_model=Pagina[ExcecaoProdutoResponse])
async def listar_excecoes_produto(
    empresa_id: UUID | None = Query(default=None),
    codigo: str | None = Query(default=None),
    ncm: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    stmt = select(ExcecaoEnquadramentoStProduto)
    if empresa_id:
        stmt = stmt.where(ExcecaoEnquadramentoStProduto.empresa_id == empresa_id)
    if codigo:
        stmt = stmt.where(
            ExcecaoEnquadramentoStProduto.codigo_produto.ilike(f"%{codigo.strip()}%")
        )
    if ncm:
        stmt = stmt.where(ExcecaoEnquadramentoStProduto.ncm.like(f"{only_digits(ncm)}%"))
    total = await session.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ) or 0
    rows = (await session.execute(
        stmt.order_by(
            ExcecaoEnquadramentoStProduto.empresa_id,
            ExcecaoEnquadramentoStProduto.codigo_produto,
        ).offset((page - 1) * page_size).limit(page_size)
    )).scalars().all()
    return Pagina(items=list(rows), total=total, page=page, page_size=page_size)


async def _garantir_excecao_unica(
    session: AsyncSession, dados: dict, excluir_id: UUID | None = None,
) -> None:
    if not dados["ativo"]:
        return
    fim = dados["data_fim_vigencia"] or date.max
    stmt = select(ExcecaoEnquadramentoStProduto.id).where(
        ExcecaoEnquadramentoStProduto.empresa_id == dados["empresa_id"],
        ExcecaoEnquadramentoStProduto.codigo_produto == dados["codigo_produto"],
        ExcecaoEnquadramentoStProduto.ativo.is_(True),
        ExcecaoEnquadramentoStProduto.data_inicio_vigencia <= fim,
        (
            ExcecaoEnquadramentoStProduto.data_fim_vigencia.is_(None)
            | (ExcecaoEnquadramentoStProduto.data_fim_vigencia >= dados["data_inicio_vigencia"])
        ),
    )
    if excluir_id:
        stmt = stmt.where(ExcecaoEnquadramentoStProduto.id != excluir_id)
    if await session.scalar(stmt):
        raise ConflictError(
            "Já existe uma exceção ativa para esta empresa e código de produto "
            "com vigência sobreposta."
        )


@router.post(
    "/excecoes-produto", response_model=ExcecaoProdutoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def criar_excecao_produto(
    body: ExcecaoProdutoCreate,
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    dados = body.normalizado()
    await _empresa_do_tenant(session, dados["empresa_id"])
    await _garantir_excecao_unica(session, dados)
    linha = ExcecaoEnquadramentoStProduto(
        **dados, tenant_id=claims.tid, definido_por=str(claims.sub)
    )
    session.add(linha)
    await session.flush()
    reprocesso = await ReprocessService(session).reprocessar_produto(
        linha.empresa_id, linha.codigo_produto
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="excecao_st_produto.criar",
        entidade="excecao_st_produto", entidade_id=str(linha.id),
        detalhe={"empresa_id": str(linha.empresa_id), "codigo": linha.codigo_produto,
                 "tributado_icms": linha.tributado_icms, **reprocesso},
    )
    return linha


@router.patch("/excecoes-produto/{linha_id}", response_model=ExcecaoProdutoResponse)
async def editar_excecao_produto(
    linha_id: UUID, body: ExcecaoProdutoUpdate,
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    linha = await session.get(ExcecaoEnquadramentoStProduto, linha_id)
    if linha is None:
        raise NotFoundError("Exceção não encontrada.")
    empresa_anterior = linha.empresa_id
    codigo_anterior = linha.codigo_produto
    dados = body.normalizado()
    await _empresa_do_tenant(session, dados["empresa_id"])
    await _garantir_excecao_unica(session, dados, linha_id)
    for campo, valor in dados.items():
        setattr(linha, campo, valor)
    linha.definido_por = str(claims.sub)
    linha.updated_at = datetime.now(UTC)
    await session.flush()
    reprocesso = await ReprocessService(session).reprocessar_produto(
        linha.empresa_id, linha.codigo_produto
    )
    if (empresa_anterior, codigo_anterior) != (linha.empresa_id, linha.codigo_produto):
        anterior = await ReprocessService(session).reprocessar_produto(
            empresa_anterior, codigo_anterior
        )
        reprocesso["notas_reprocessadas_anterior"] = anterior["notas_reprocessadas"]
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="excecao_st_produto.editar",
        entidade="excecao_st_produto", entidade_id=str(linha.id),
        detalhe={"empresa_id": str(linha.empresa_id), "codigo": linha.codigo_produto,
                 "tributado_icms": linha.tributado_icms, **reprocesso},
    )
    return linha


@router.delete("/excecoes-produto/{linha_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remover_excecao_produto(
    linha_id: UUID,
    claims: TokenClaims = Depends(require_curador),
    session: AsyncSession = Depends(tenant_session),
):
    linha = await session.get(ExcecaoEnquadramentoStProduto, linha_id)
    if linha is None:
        raise NotFoundError("Exceção não encontrada.")
    empresa_id = linha.empresa_id
    codigo_produto = linha.codigo_produto
    await session.delete(linha)
    await session.flush()
    reprocesso = await ReprocessService(session).reprocessar_produto(
        empresa_id, codigo_produto
    )
    await AuditService(session).registrar(
        tenant_id=claims.tid, user_id=claims.sub, acao="excecao_st_produto.remover",
        entidade="excecao_st_produto", entidade_id=str(linha_id),
        detalhe={"empresa_id": str(empresa_id), "codigo": codigo_produto, **reprocesso},
    )


async def _garantir_sem_sobreposicao(session, modelo, dados: dict, excluir_id=None):
    """ADR-0002 (regra 4): mudou a taxa? Encerre a vigência antiga e INSIRA uma
    nova linha — nunca duas vigentes na mesma data para a mesma chave."""
    conflito = await sobreposicao_existente(session, modelo, dados, excluir_id)
    if conflito is not None:
        fim = conflito.data_fim_vigencia or "em aberto"
        raise ConflictError(
            "Vigência sobrepõe a linha existente "
            f"#{conflito.id} ({conflito.data_inicio_vigencia} – {fim}). "
            "Encerre a vigência da linha atual e insira uma nova (ADR-0002)."
        )


def _registrar_crud(
    sub: str,
    modelo: type[Base],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    response_schema: type[BaseModel],
    *,
    entidade: str,
    detalhe: Callable[[object], dict],
    filtrar: Callable | None = None,
) -> None:
    """Registra GET/POST/PATCH/DELETE de uma matriz sob /matrizes/{sub}."""

    @router.get(f"/{sub}", response_model=Pagina[response_schema], name=f"listar_{sub}")
    async def _listar(
        uf: str | None = Query(default=None, description="Filtra por UF destino"),
        ncm: str | None = Query(default=None, description="Filtra por NCM (prefixo)"),
        cest: str | None = Query(default=None, description="Filtra por CEST (prefixo)"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=50),
        claims: TokenClaims = Depends(get_current_claims),
        session: AsyncSession = Depends(tenant_session),
    ):
        stmt = select(modelo)
        if filtrar is not None:
            stmt = filtrar(stmt, uf, ncm, cest)
        total = await session.scalar(
            select(func.count()).select_from(stmt.order_by(None).subquery())
        ) or 0
        rows = (await session.execute(
            stmt.offset((page - 1) * page_size).limit(page_size)
        )).scalars().all()
        return Pagina(items=list(rows), total=total, page=page, page_size=page_size)

    @router.post(
        f"/{sub}", response_model=response_schema,
        status_code=status.HTTP_201_CREATED, name=f"criar_{sub}",
    )
    async def _criar(
        body: create_schema,  # type: ignore[valid-type]
        claims: TokenClaims = Depends(require_curador),
        session: AsyncSession = Depends(tenant_session),
    ):
        dados = body.normalizado()
        await _garantir_sem_sobreposicao(session, modelo, dados)
        linha = modelo(**dados)
        session.add(linha)
        await session.flush()
        await AuditService(session).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao=f"{entidade}.criar",
            entidade=entidade, entidade_id=str(linha.id), detalhe=detalhe(linha),
        )
        return linha

    @router.patch(f"/{sub}/{{linha_id}}", response_model=response_schema, name=f"editar_{sub}")
    async def _editar(
        linha_id: int,
        body: update_schema,  # type: ignore[valid-type]
        claims: TokenClaims = Depends(require_curador),
        session: AsyncSession = Depends(tenant_session),
    ):
        linha = await session.get(modelo, linha_id)
        if linha is None:
            raise NotFoundError("Matriz não encontrada.")
        dados = body.normalizado()
        await _garantir_sem_sobreposicao(session, modelo, dados, excluir_id=linha_id)
        for campo, valor in dados.items():
            setattr(linha, campo, valor)
        # Editar = reconferir: renova o carimbo de verificação (Fase 2).
        linha.ultima_verificacao_em = datetime.now(UTC)
        await session.flush()
        await AuditService(session).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao=f"{entidade}.editar",
            entidade=entidade, entidade_id=str(linha.id), detalhe=detalhe(linha),
        )
        return linha

    @router.delete(
        f"/{sub}/{{linha_id}}", status_code=status.HTTP_204_NO_CONTENT, name=f"remover_{sub}",
    )
    async def _remover(
        linha_id: int,
        claims: TokenClaims = Depends(require_curador),
        session: AsyncSession = Depends(tenant_session),
    ):
        linha = await session.get(modelo, linha_id)
        if linha is None:
            raise NotFoundError("Matriz não encontrada.")
        await session.delete(linha)
        await AuditService(session).registrar(
            tenant_id=claims.tid, user_id=claims.sub, acao=f"{entidade}.remover",
            entidade=entidade, entidade_id=str(linha_id), detalhe={},
        )


def _ordenar(modelo, *cols):
    """Filtros combináveis (UF + NCM + CEST, por prefixo) + ordenação, fechados
    sobre o modelo da matriz. CEST só filtra onde a coluna existe (MVA/Enq.)."""
    def _f(stmt, uf, ncm, cest):
        if uf:
            stmt = stmt.where(modelo.uf_destino == uf.upper())
        if ncm:
            stmt = stmt.where(modelo.ncm.like(f"{only_digits(ncm)}%"))
        if cest and hasattr(modelo, "cest"):
            stmt = stmt.where(modelo.cest.like(f"{only_digits(cest)}%"))
        return stmt.order_by(*cols)
    return _f


_registrar_crud(
    "mva", MatrizMva, MatrizMvaCreate, MatrizMvaUpdate, MatrizMvaResponse,
    entidade="matriz_mva",
    detalhe=lambda m: {"ncm": m.ncm, "cest": m.cest, "uf": m.uf_destino},
    filtrar=_ordenar(MatrizMva, MatrizMva.uf_destino, MatrizMva.ncm, MatrizMva.cest),
)
_registrar_crud(
    "enquadramento", MatrizEnquadramentoSt, MatrizEnquadramentoCreate,
    MatrizEnquadramentoUpdate, MatrizEnquadramentoResponse,
    entidade="matriz_enquadramento",
    detalhe=lambda m: {"ncm": m.ncm, "cest": m.cest, "uf": m.uf_destino, "regime": m.regime},
    filtrar=_ordenar(
        MatrizEnquadramentoSt, MatrizEnquadramentoSt.uf_destino,
        MatrizEnquadramentoSt.ncm, MatrizEnquadramentoSt.cest,
    ),
)
_registrar_crud(
    "fcp", MatrizFcp, MatrizFcpCreate, MatrizFcpUpdate, MatrizFcpResponse,
    entidade="matriz_fcp",
    detalhe=lambda m: {"uf": m.uf_destino, "ncm": m.ncm, "fcp_st": str(m.aliq_fcp_st)},
    filtrar=_ordenar(MatrizFcp, MatrizFcp.uf_destino, MatrizFcp.ncm),
)
def _filtrar_protocolos(stmt, uf, ncm, cest):
    """Protocolo: NCM vazio = acordo do PAR INTEIRO (vale p/ qualquer NCM) —
    filtrar por NCM precisa MANTER essas linhas, senão a tela esconderia um
    acordo que se aplica ao produto pesquisado."""
    if uf:
        stmt = stmt.where(MatrizProtocoloSt.uf_destino == uf.upper())
    if ncm:
        stmt = stmt.where(or_(
            MatrizProtocoloSt.ncm.is_(None),
            MatrizProtocoloSt.ncm.like(f"{only_digits(ncm)}%"),
        ))
    return stmt.order_by(MatrizProtocoloSt.uf_origem, MatrizProtocoloSt.uf_destino)


_registrar_crud(
    "protocolos", MatrizProtocoloSt, MatrizProtocoloCreate, MatrizProtocoloUpdate,
    MatrizProtocoloResponse,
    entidade="matriz_protocolo",
    detalhe=lambda m: {"origem": m.uf_origem, "destino": m.uf_destino, "acordo": m.numero_acordo},
    filtrar=_filtrar_protocolos,
)


def _filtrar_aliquota(stmt, uf, ncm, cest):
    """Alíquota não tem NCM (chave é só a UF) — o filtro genérico não serve."""
    if uf:
        stmt = stmt.where(MatrizAliquota.uf_destino == uf.upper())
    return stmt.order_by(MatrizAliquota.uf_destino, MatrizAliquota.data_inicio_vigencia.desc())


@router.get("/saude")
async def saude_matrizes_endpoint(
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Radar de frescor da base (Fase 2): % das linhas vigentes verificadas
    nos últimos 90 dias, a verificação mais antiga por matriz e as propostas
    aguardando revisão — o que está envelhecendo aparece antes de virar erro."""
    return await saude_matrizes(session)


@router.get("/pares-interestaduais")
async def pares_interestaduais_endpoint(
    limite: int = Query(default=50, ge=1, le=100),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Fila de pares UF→UF (Fase 3): o que a carteira movimenta entre estados
    × a curadoria de Protocolos. Par não avaliado trava o motor interestadual
    (ERRO_PROTOCOLO_NAO_AVALIADO) — ordenado por dinheiro em jogo."""
    return await pares_interestaduais(session, limite=limite)


@router.get("/cobertura")
async def cobertura_matrizes(
    empresa_id: UUID | None = Query(default=None, description="Limita a uma empresa"),
    uf: str | None = Query(default=None, description="UF de destino"),
    ano: str | None = Query(default=None, description="Competência: ano (AAAA)"),
    mes: str | None = Query(default=None, description="Competência: mês (MM)"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    claims: TokenClaims = Depends(get_current_claims),
    session: AsyncSession = Depends(tenant_session),
):
    """Fila de curadoria: agrupa os itens importados por NCM×CEST×UF, confronta
    com as matrizes vigentes e ordena por valor — mostra exatamente o que
    cadastrar primeiro (e quando parar)."""
    return await CoberturaService(session).cobertura(
        empresa_id=empresa_id, uf=uf, ano=ano, mes=mes,
        page=page, page_size=page_size,
    )


_registrar_crud(
    "aliquotas", MatrizAliquota, MatrizAliquotaCreate, MatrizAliquotaUpdate,
    MatrizAliquotaResponse,
    entidade="matriz_aliquota",
    detalhe=lambda m: {"uf": m.uf_destino, "modal": str(m.aliq_modal)},
    filtrar=_filtrar_aliquota,
)
