"""Fila de pares interestaduais (Fase 3): movimento real das notas × curadoria
de protocolos — ordenada por valor, com canceladas/CT-e/operação interna fora."""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.pares_interestaduais import pares_interestaduais
from app.modules.fiscal.infrastructure.matrizes_models import MatrizProtocoloSt
from app.modules.fiscal.infrastructure.models import Nota


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[Nota.__table__, MatrizProtocoloSt.__table__],
        )
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _nota(uf_emit: str, uf_dest: str, valor: str, **extra) -> Nota:
    campos = {
        "tenant_id": uuid4(), "empresa_id": uuid4(), "chave_acesso": str(uuid4()),
        "tipo": "NFe", "fluxo": "entrada", "modelo": "55",
        "uf_emit": uf_emit, "uf_dest": uf_dest, "valor_total": Decimal(valor),
    }
    campos.update(extra)
    return Nota(**campos)


@pytest.mark.asyncio
async def test_pares_ordenados_por_valor_com_curadoria(sessao):
    sessao.add_all([
        _nota("SP", "MG", "100.00"),
        _nota("SP", "MG", "200.00"),
        _nota("PR", "MG", "50.00"),
        _nota("MG", "MG", "999.00"),                      # interna: fora
        _nota("SP", "MG", "888.00", status="cancelada"),  # cancelada: fora
        _nota("RS", "MG", "777.00", fluxo="cte"),         # CT-e: fora (ST é mercadoria)
    ])
    # PR→MG curado com acordo ATIVO vigente; SP→MG sem NENHUMA linha.
    sessao.add(MatrizProtocoloSt(
        uf_origem="PR", uf_destino="MG", numero_acordo="Protocolo ICMS 41/2008",
        situacao="ATIVO", data_inicio_vigencia=date(2020, 1, 1),
    ))
    await sessao.flush()

    r = await pares_interestaduais(sessao)
    assert [(p["uf_origem"], p["uf_destino"]) for p in r["pares"]] == [("SP", "MG"), ("PR", "MG")]

    sp_mg, pr_mg = r["pares"]
    assert sp_mg["notas"] == 2 and sp_mg["valor"] == 300.0
    assert sp_mg["curado"] is False                       # trava o motor
    assert pr_mg["curado"] is True and pr_mg["acordos_ativos"] == 1
    assert r["nao_avaliados"] == 1


@pytest.mark.asyncio
async def test_sem_acordo_tambem_e_curadoria(sessao):
    """Registro explícito de que NÃO há acordo destrava o par (antecipação) —
    aparece como curado, com zero acordos ativos."""
    sessao.add(_nota("GO", "MG", "10.00"))
    sessao.add(MatrizProtocoloSt(
        uf_origem="GO", uf_destino="MG", numero_acordo="Sem acordo no par",
        situacao="SEM_ACORDO", data_inicio_vigencia=date(2020, 1, 1),
    ))
    await sessao.flush()

    r = await pares_interestaduais(sessao)
    par = r["pares"][0]
    assert par["curado"] is True and par["acordos_ativos"] == 0
    assert r["nao_avaliados"] == 0
