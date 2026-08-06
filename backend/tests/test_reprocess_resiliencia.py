"""Reprocessamento de pendências: uma nota podre não derruba o lote.

O motor de ST já segue esse princípio POR ITEM ("input podre vira diagnóstico,
nunca crash do lote" — docstring do engine). A orquestração do reprocessamento
não seguia: uma única exceção subia como HTTP 500, o usuário via só "erro",
nenhuma nota era destravada e não havia como saber QUAL nota quebrou.
"""
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.cfop_rules.infrastructure.models import CfopRegra
from app.modules.fiscal.application.reprocess_service import ReprocessService
from app.modules.fiscal.infrastructure.models import AuditoriaIcmsSt, Nota, NotaItem

_TABELAS = [
    Nota.__table__, NotaItem.__table__, AuditoriaIcmsSt.__table__, CfopRegra.__table__,
]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _nota(tenant, empresa, chave):
    return Nota(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa, chave_acesso=chave,
        tipo="NFe", fluxo="entrada", modelo="55", uf_dest="MG", uf_emit="SP",
        data_emissao="2026-06-01", ano="2026", mes="06", status="ativa",
    )


def _travada(tenant, empresa, nota):
    """Item NAO_AUDITAVEL COM código de erro — é o que entra no reprocesso."""
    return AuditoriaIcmsSt(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa, nota_id=nota.id,
        chave_acesso=nota.chave_acesso, numero_item=1,
        vbc_st_calculado=Decimal("0"), vicms_st_calculado=Decimal("0"),
        status="NAO_AUDITAVEL", codigo_erro="ERRO_MVA_NAO_ENCONTRADA",
    )


async def _duas_travadas(s: AsyncSession):
    tenant, empresa = uuid4(), uuid4()
    boa, podre = _nota(tenant, empresa, "1" * 44), _nota(tenant, empresa, "2" * 44)
    s.add_all([boa, podre, _travada(tenant, empresa, boa), _travada(tenant, empresa, podre)])
    await s.flush()
    return empresa, boa, podre


async def test_uma_nota_quebrada_nao_derruba_o_lote(sessao):
    """Era o 500: a exceção da primeira nota abortava tudo."""
    empresa, boa, podre = await _duas_travadas(sessao)
    servico = ReprocessService(sessao)
    chamadas: list = []

    async def auditar(eid, nid):
        chamadas.append(nid)
        if nid == podre.id:
            raise RuntimeError("XML sem <emit> — dado corrompido")

    servico.audit.auditar_nota = auditar

    r = await servico.reprocessar_pendentes(empresa)

    # As DUAS foram tentadas: a falha não interrompeu a varredura.
    assert set(chamadas) == {boa.id, podre.id}
    assert r["falhas"] == 1
    assert r["notas_reprocessadas"] == 1        # só a que passou é contada
    assert [f["nota_id"] for f in r["falhas_detalhe"]] == [str(podre.id)]
    # O motivo vai junto: sem ele o usuário sabe que falhou e não sabe por quê.
    assert "RuntimeError" in r["falhas_detalhe"][0]["erro"]
    assert "dado corrompido" in r["falhas_detalhe"][0]["erro"]


async def test_sessao_continua_utilizavel_depois_da_falha(sessao):
    """A falha é isolada por SAVEPOINT: se a sessão ficasse suja, todas as
    notas seguintes cairiam em cascata por causa de uma só."""
    empresa, boa, podre = await _duas_travadas(sessao)
    servico = ReprocessService(sessao)

    async def auditar(eid, nid):
        if nid == podre.id:
            raise RuntimeError("boom")

    servico.audit.auditar_nota = auditar
    await servico.reprocessar_pendentes(empresa)

    # A sessão segue viva: dá para consultar depois do erro.
    assert await sessao.scalar(
        AuditoriaIcmsSt.__table__.select().where(
            AuditoriaIcmsSt.nota_id == boa.id
        ).with_only_columns(AuditoriaIcmsSt.id).limit(1)
    ) is not None


async def test_sem_falha_o_resumo_nao_muda_de_forma(sessao):
    """Não-regressão do contrato: lote saudável continua devolvendo os mesmos
    contadores, agora com `falhas` em zero."""
    empresa, boa, podre = await _duas_travadas(sessao)
    servico = ReprocessService(sessao)

    async def auditar(eid, nid):
        return None

    servico.audit.auditar_nota = auditar

    r = await servico.reprocessar_pendentes(empresa)

    assert r["notas_reprocessadas"] == 2
    assert r["falhas"] == 0
    assert r["falhas_detalhe"] == []
    assert r["cfop_reclassificados"] == 0
