"""Radar de saúde das matrizes (Fase 2): frescor calculado SÓ sobre as linhas
vigentes — regra encerrada não envelhece ninguém — e propostas pendentes no
resumo geral."""
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.matrizes_saude import saude_matrizes
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.propostas_models import MatrizProposta


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            MatrizMva.__table__, MatrizEnquadramentoSt.__table__,
            MatrizProtocoloSt.__table__, MatrizAliquota.__table__,
            MatrizFcp.__table__, MatrizProposta.__table__,
        ])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_frescor_por_matriz_e_resumo_geral(sessao):
    sessao.add_all([
        # Enquadramento vigente, verificado AGORA (default do cadastro) → 100%.
        MatrizEnquadramentoSt(
            uf_destino="MG", ncm="40111000", cest="0100500", regime="ST",
            data_inicio_vigencia=date(2026, 6, 1),
        ),
        # MVA vigente com verificação VELHA (jan/2025) → 0% na janela de 90d.
        MatrizMva(
            ncm="40111000", cest="0100500", uf_destino="MG",
            mva_original=Decimal("40.00"), data_inicio_vigencia=date(2026, 6, 1),
            ultima_verificacao_em=datetime(2025, 1, 1),
        ),
        # Alíquota ENCERRADA: fora do radar (não conta como vigente).
        MatrizAliquota(
            uf_destino="MG", aliq_modal=Decimal("18.00"),
            data_inicio_vigencia=date(2020, 1, 1), data_fim_vigencia=date(2021, 1, 1),
            ultima_verificacao_em=datetime(2020, 6, 1),
        ),
    ])
    sessao.add(MatrizProposta(
        tipo_matriz="enquadramento", acao="INSERIR", chave_resumo="MG · NCM x",
        payload={}, fonte="teste", hash_proposta="h1",
    ))
    await sessao.flush()

    s = await saude_matrizes(sessao)
    por = {m["tipo"]: m for m in s["matrizes"]}

    assert por["enquadramento"]["vigentes"] == 1
    assert por["enquadramento"]["pct_90d"] == 100
    assert por["mva"]["pct_90d"] == 0
    assert por["mva"]["verificacao_mais_antiga"].startswith("2025-01-01")
    assert por["aliquotas"]["vigentes"] == 0 and por["aliquotas"]["pct_90d"] is None

    geral = s["geral"]
    assert geral["vigentes"] == 2
    assert geral["pct_verificado_90d"] == 50       # 1 fresca de 2 vigentes
    assert geral["propostas_pendentes"] == 1
    assert geral["ultima_atualizacao"] is not None
