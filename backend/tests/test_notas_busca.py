"""Busca livre na listagem de notas (?q=): nº da NF, chave, nome e CNPJ.

Com centenas de notas importadas, paginar até achar UMA é inviável — a busca
resolve por nome (parcial, sem caixa) e por dígitos (número/chave/CNPJ).
"""
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.infrastructure.models import NfeCteVinculo, Nota
from app.modules.fiscal.infrastructure.repositories import NotaRepository

_TABELAS = [Nota.__table__, NfeCteVinculo.__table__]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _nota(tenant, empresa, chave, numero, nome_emit, cnpj_emit):
    return Nota(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa, chave_acesso=chave,
        tipo="NFe", fluxo="entrada", modelo="55", numero=numero,
        nome_emit=nome_emit, cnpj_emit=cnpj_emit,
        nome_dest="CLIENTE MG LTDA", cnpj_dest="22222222000122",
        data_emissao="2026-06-01", ano="2026", mes="06",
    )


async def test_busca_por_nome_numero_chave_e_cnpj(sessao):
    tenant, empresa = uuid4(), uuid4()
    sessao.add_all([
        _nota(tenant, empresa, "1" * 44, "6239", "ALTO CAFEZAL COM. IMP. E EXP. LTDA",
              "03280627000131"),
        _nota(tenant, empresa, "5" * 40 + "9876", "334", "JOSE C. GROSSI SEGUNDO",
              "09092087602"),
    ])
    await sessao.flush()
    repo = NotaRepository(sessao)

    # Nome parcial, caixa diferente.
    r = await repo.list(empresa, q="cafezal")
    assert r["total"] == 1 and r["notas"][0].numero == "6239"

    # Número da NF.
    r = await repo.list(empresa, q="334")
    assert r["total"] == 1 and r["notas"][0].nome_emit.startswith("JOSE")

    # Trecho da chave de acesso.
    r = await repo.list(empresa, q="9876")
    assert r["total"] == 1 and r["notas"][0].numero == "334"

    # CNPJ formatado (pontuação é ignorada — vale o dígito).
    r = await repo.list(empresa, q="03.280.627/0001-31")
    assert r["total"] == 1 and r["notas"][0].numero == "6239"

    # Sem correspondência.
    r = await repo.list(empresa, q="inexistente xyz")
    assert r["total"] == 0 and r["notas"] == []

    # q vazio/espaços não filtra nada.
    r = await repo.list(empresa, q="   ")
    assert r["total"] == 2
