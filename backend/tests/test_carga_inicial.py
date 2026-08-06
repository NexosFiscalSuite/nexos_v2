"""Carga inicial das matrizes: semeia o verificado SEM sobrescrever nada,
é idempotente, e o aprovar_lote por FONTE só aprova a origem pedida."""
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.propostas_service import PropostasService
from app.modules.fiscal.crawlers.carga_inicial import aplicar_seed_aliquotas_fcp
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizFcp,
    MatrizMva,
)
from app.modules.fiscal.infrastructure.propostas_models import MatrizProposta


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            MatrizAliquota.__table__, MatrizFcp.__table__,
            MatrizMva.__table__, MatrizProposta.__table__,
        ])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_seed_preenche_e_e_idempotente(sessao):
    r1 = await aplicar_seed_aliquotas_fcp(sessao)
    assert r1 == {"aliquotas_inseridas": 8, "fcp_inseridos": 1, "ja_existiam": 0}

    # RJ tem as DUAS vigências (18%+2% até 19/03/2024; 20%+2% depois).
    rj = (await sessao.execute(
        select(MatrizAliquota).where(MatrizAliquota.uf_destino == "RJ")
        .order_by(MatrizAliquota.data_inicio_vigencia)
    )).scalars().all()
    assert [(x.aliq_modal, x.data_fim_vigencia) for x in rj] == [
        (Decimal("18.00"), date(2024, 3, 19)), (Decimal("20.00"), None),
    ]

    r2 = await aplicar_seed_aliquotas_fcp(sessao)   # rodar de novo: nada duplica
    assert r2["aliquotas_inseridas"] == 0 and r2["ja_existiam"] == 9
    total = await sessao.scalar(select(func.count()).select_from(MatrizAliquota))
    assert total == 8


@pytest.mark.asyncio
async def test_seed_semeia_a_aliquota_do_estado_sem_reducao(sessao):
    """A carga é a regra do ESTADO: todas as linhas entram como NCM 'GERAL' e
    sem redução de base. Alíquota reduzida por produto é dado normativo e entra
    só pela curadoria — o robô não chuta número de lei.

    O 'GERAL' também é o que faz a checagem de sobreposição funcionar: a família
    de vigência é (uf_destino, ncm)."""
    await aplicar_seed_aliquotas_fcp(sessao)

    linhas = (await sessao.execute(select(MatrizAliquota))).scalars().all()
    assert {x.ncm for x in linhas} == {"GERAL"}
    assert {x.p_red_bc_st for x in linhas} == {Decimal("0.00")}


@pytest.mark.asyncio
async def test_seed_nunca_sobrescreve_linha_existente(sessao):
    """O escritório já tinha MG cadastrada (valor próprio): a carga pula MG e
    preenche só o que falta — linha existente tem sempre prioridade."""
    sessao.add(MatrizAliquota(
        uf_destino="MG", aliq_modal=Decimal("18.00"),
        base_legal="Cadastro do escritório", data_inicio_vigencia=date(2023, 1, 1),
    ))
    await sessao.flush()

    r = await aplicar_seed_aliquotas_fcp(sessao)
    assert r["aliquotas_inseridas"] == 7 and r["ja_existiam"] == 1

    mg = (await sessao.execute(
        select(MatrizAliquota).where(MatrizAliquota.uf_destino == "MG")
    )).scalars().one()
    assert mg.base_legal == "Cadastro do escritório"   # intocada


@pytest.mark.asyncio
async def test_aprovar_lote_filtra_por_fonte(sessao):
    payload = {"ncm": "40111000", "cest": "1600100", "uf_destino": "MG",
               "mva_original": "42.00", "base_legal": "x",
               "data_inicio_vigencia": "2026-06-01", "data_fim_vigencia": None}
    sessao.add_all([
        MatrizProposta(tipo_matriz="mva", acao="INSERIR", chave_resumo="MG · a",
                       payload=payload, fonte="SEFAZ-MG", hash_proposta="h1"),
        MatrizProposta(tipo_matriz="mva", acao="INSERIR", chave_resumo="MG · b",
                       payload={**payload, "cest": "1600200"},
                       fonte="OUTRA FONTE", hash_proposta="h2"),
    ])
    await sessao.flush()

    r = await PropostasService(sessao).aprovar_lote(
        revisor="carga inicial automática (robô)", tipo="mva", fonte="SEFAZ-MG",
    )
    assert r["aprovadas"] == 1 and r["falhas"] == []

    por_fonte = dict((await sessao.execute(
        select(MatrizProposta.fonte, MatrizProposta.status)
    )).all())
    assert por_fonte == {"SEFAZ-MG": "APROVADA", "OUTRA FONTE": "PENDENTE"}
    linhas = await sessao.scalar(select(func.count()).select_from(MatrizMva))
    assert linhas == 1
