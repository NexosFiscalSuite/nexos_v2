"""Prova de fogo — paridade banco↔motor (integração ponta a ponta).

Substitui os mocks fixos do laboratório pelo dado REAL vindo do banco: o loader
async vai ao SQLite (com filtro de vigência), traz a MVA 71,78% da autopeça e
hidrata os repositórios; o motor (puro, síncrono) calcula e crava o gabarito
de R$ 177,50 — o mesmo do laboratório, agora alimentado pela infraestrutura.
"""
from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.domain.st import Crt, ItemFiscal, Operacao, StAuditEngine
from app.modules.fiscal.infrastructure.matrizes_loaders import MatrizesLoader
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from scripts.seed_matrizes import aplicar_seed

_TABELAS = [
    MatrizMva.__table__,
    MatrizEnquadramentoSt.__table__,
    MatrizFcp.__table__,
    MatrizProtocoloSt.__table__,
    MatrizAliquota.__table__,
]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        await aplicar_seed(s)        # popula com os NCMs do Vault/laboratórios
        await s.commit()
        yield s
    await engine.dispose()


async def test_paridade_autopeca_banco_para_motor(sessao):
    """Loader busca no banco -> hidrata repos -> motor crava R$ 177,50."""
    item = ItemFiscal(
        numero_item=1, ncm="87082919", cest="0107500", cfop="6102", orig="0",
        cst="00", mod_bc_st=4,
        v_prod=Decimal("731.35"), v_frete=Decimal("68.05"),     # frete do CT-e rateado
        v_bc=Decimal("731.35"), v_icms=Decimal("87.76"), p_icms=Decimal("12"),
        v_bc_st=Decimal("0"), v_icms_st=Decimal("0"),           # remetente omitiu o ST
    )
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=date(2026, 6, 1))

    # 1) Camada async: vai ao banco e hidrata os repositórios sync.
    matrizes = await MatrizesLoader(sessao).hidratar([item], op)

    # 2) Motor puro/síncrono consome os repositórios hidratados.
    engine = StAuditEngine(
        mva_repo=matrizes.mva,
        enquadramento_repo=matrizes.enquadramento,
        fcp_repo=matrizes.fcp,
        aliquota_repo=matrizes.aliquota,
    )
    r = engine.auditar_item(item, op)

    # A MVA 71,78% veio do BANCO (não de mock fixo) — e a alíquota também.
    assert r.memoria.mva_original == Decimal("71.78")
    assert r.memoria.aliquota_matriz_id is not None
    assert r.memoria.mva_matriz_id is not None
    assert r.memoria.mva_foi_ajustada is True
    assert round(r.memoria.mva_aplicada, 2) == Decimal("84.35")
    assert r.memoria.base_st_calculada == Decimal("1473.69")
    # Gabarito cravado, agora alimentado pela infraestrutura.
    assert r.memoria.icms_st_calculado == Decimal("177.50")


async def test_paridade_vigencia_fora_de_periodo(sessao):
    """Nota anterior à vigência (2024-01-01): o loader não acha MVA -> NAO_AUDITAVEL."""
    item = ItemFiscal(
        numero_item=1, ncm="87082919", cest="0107500", cfop="6102", orig="0",
        cst="00", mod_bc_st=4, v_prod=Decimal("731.35"),
    )
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=date(2023, 1, 1))

    matrizes = await MatrizesLoader(sessao).hidratar([item], op)
    engine = StAuditEngine(
        mva_repo=matrizes.mva,
        enquadramento_repo=matrizes.enquadramento,
        fcp_repo=matrizes.fcp,
        aliquota_repo=matrizes.aliquota,
    )
    r = engine.auditar_item(item, op)
    # Sem matriz vigente em 2023 -> motor não audita (depende do dado da matriz).
    assert r.status == "NAO_AUDITAVEL"
