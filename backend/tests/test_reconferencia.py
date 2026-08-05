"""Reconferência semestral (Fase 4): linha vigente não verificada no ciclo
vira proposta REVALIDAR; aprovar renova o carimbo SEM mudar valores; rejeição
segura só o ciclo corrente — no seguinte a pergunta volta (hash com ciclo)."""
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.propostas_service import PropostasService
from app.modules.fiscal.crawlers.reconferencia import propor_reconferencia
from app.modules.fiscal.infrastructure.matrizes_models import MatrizAliquota, MatrizFcp
from app.modules.fiscal.infrastructure.propostas_models import MatrizProposta

CICLO = "2026-2"
INICIO = datetime(2026, 7, 1, tzinfo=UTC)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            MatrizAliquota.__table__, MatrizFcp.__table__, MatrizProposta.__table__,
        ])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_cria_para_velhas_e_pula_frescas(sessao):
    sessao.add_all([
        # MG: alíquota e FCP verificadas ANTES do ciclo → reconferir.
        MatrizAliquota(
            uf_destino="MG", aliq_modal=Decimal("18.00"),
            data_inicio_vigencia=date(2024, 1, 1),
            ultima_verificacao_em=datetime(2026, 1, 10),
        ),
        MatrizFcp(
            uf_destino="MG", ncm="GERAL", aliq_fcp_st=Decimal("2.00"),
            data_inicio_vigencia=date(2024, 1, 1),
            ultima_verificacao_em=datetime(2026, 1, 10),
        ),
        # SP: verificada AGORA (default do cadastro) → fresca, fica de fora.
        MatrizAliquota(
            uf_destino="SP", aliq_modal=Decimal("18.00"),
            data_inicio_vigencia=date(2024, 1, 1),
        ),
    ])
    await sessao.flush()

    r = await propor_reconferencia(sessao, ["MG", "SP"], ciclo=CICLO, inicio_ciclo=INICIO)
    assert r["propostas"] == 2 and r["frescas"] == 1

    # Idempotente dentro do ciclo: pendentes seguram a re-proposta.
    r2 = await propor_reconferencia(sessao, ["MG", "SP"], ciclo=CICLO, inicio_ciclo=INICIO)
    assert r2["propostas"] == 0


@pytest.mark.asyncio
async def test_confirmar_renova_carimbo_sem_mudar_valores(sessao):
    sessao.add(MatrizAliquota(
        uf_destino="MG", aliq_modal=Decimal("18.00"), aliq_fcp_integrado=Decimal("0"),
        base_legal="Lei 6.763/1975", data_inicio_vigencia=date(2024, 1, 1),
        ultima_verificacao_em=datetime(2026, 1, 10),
    ))
    await sessao.flush()
    await propor_reconferencia(sessao, ["MG"], ciclo=CICLO, inicio_ciclo=INICIO)

    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    assert p.acao == "REVALIDAR"
    await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")

    linha = (await sessao.execute(select(MatrizAliquota))).scalars().one()
    assert linha.aliq_modal == Decimal("18.00")          # nada mudou
    assert linha.base_legal == "Lei 6.763/1975"
    assert linha.ultima_verificacao_em != datetime(2026, 1, 10)   # carimbo renovado

    # Renovada dentro do ciclo → não volta à fila.
    r = await propor_reconferencia(sessao, ["MG"], ciclo=CICLO, inicio_ciclo=INICIO)
    assert r["propostas"] == 0 and r["frescas"] == 1


@pytest.mark.asyncio
async def test_rejeicao_vale_so_para_o_ciclo(sessao):
    sessao.add(MatrizAliquota(
        uf_destino="MG", aliq_modal=Decimal("18.00"),
        data_inicio_vigencia=date(2024, 1, 1),
        ultima_verificacao_em=datetime(2026, 1, 10),
    ))
    await sessao.flush()
    await propor_reconferencia(sessao, ["MG"], ciclo=CICLO, inicio_ciclo=INICIO)
    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    await PropostasService(sessao).rejeitar(p.id, revisor="ana@sol.com", motivo="vou ajustar")

    # Mesmo ciclo: rejeitada segura.
    r = await propor_reconferencia(sessao, ["MG"], ciclo=CICLO, inicio_ciclo=INICIO)
    assert r["propostas"] == 0

    # Ciclo seguinte: a pergunta volta (hash inclui o ciclo).
    r2 = await propor_reconferencia(
        sessao, ["MG"], ciclo="2027-1", inicio_ciclo=datetime(2027, 1, 1, tzinfo=UTC),
    )
    assert r2["propostas"] == 1
