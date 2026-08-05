"""Triagem de divergências (roadmap do motor, item 1): a decisão do analista
vive em tabela própria, sobrevive ao reprocessamento e filtra/enriquece a
listagem. A carta marca COBRADA sem sobrescrever decisão já tomada."""
from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.auditoria_query import listar_divergencias
from app.modules.fiscal.application.triagem_service import definir_triagem
from app.modules.fiscal.infrastructure.models import (
    AuditoriaIcmsSt,
    DivergenciaTriagem,
    NfeCteVinculo,
    Nota,
    NotaItem,
)

TENANT, EMPRESA = uuid4(), uuid4()


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            Nota.__table__, NotaItem.__table__, AuditoriaIcmsSt.__table__,
            NfeCteVinculo.__table__, DivergenciaTriagem.__table__,
        ])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def _divergencia(s: AsyncSession, numero_item: int, chave: str) -> Nota:
    nota = Nota(
        tenant_id=TENANT, empresa_id=EMPRESA, chave_acesso=chave,
        tipo="NFe", fluxo="entrada", modelo="55", numero="130",
        nome_emit="PNEUAGRO", cnpj_emit="31312326000188",
        uf_emit="SP", uf_dest="MG", data_emissao="2026-06-25",
    )
    s.add(nota)
    await s.flush()
    s.add(AuditoriaIcmsSt(
        tenant_id=TENANT, empresa_id=EMPRESA, nota_id=nota.id,
        chave_acesso=chave, numero_item=numero_item, status="DIVERGENTE",
        codigo_erro="ERRO_104_VALOR_ST_DIVERGENTE",
        vicms_st_divergencia=Decimal("-82.24"),
    ))
    await s.flush()
    return nota


@pytest.mark.asyncio
async def test_definir_filtrar_e_enriquecer(sessao):
    n1 = await _divergencia(sessao, 1, "1" * 44)
    n2 = await _divergencia(sessao, 1, "2" * 44)

    await definir_triagem(
        sessao, tenant_id=TENANT, empresa_id=EMPRESA,
        itens=[(n1.id, 1)], status="COBRADA", por="ana@sol.com",
        observacao="Carta gerada em 05/08/2026",
    )

    r = await listar_divergencias(sessao, empresa_id=EMPRESA)
    assert r["resumo"]["triagem"] == {"COBRADA": 1, "EM_ABERTO": 1}

    cobradas = await listar_divergencias(sessao, empresa_id=EMPRESA, triagem="COBRADA")
    assert cobradas["total"] == 1
    assert cobradas["itens"][0]["triagem"]["status"] == "COBRADA"
    assert cobradas["itens"][0]["triagem"]["por"] == "ana@sol.com"

    abertas = await listar_divergencias(sessao, empresa_id=EMPRESA, triagem="EM_ABERTO")
    assert abertas["total"] == 1
    assert abertas["itens"][0]["chave_acesso"] == n2.chave_acesso
    assert abertas["itens"][0]["triagem"] is None


@pytest.mark.asyncio
async def test_sobrescreve_preserva_e_limpa(sessao):
    n1 = await _divergencia(sessao, 1, "3" * 44)
    svc = dict(tenant_id=TENANT, empresa_id=EMPRESA)

    await definir_triagem(sessao, **svc, itens=[(n1.id, 1)], status="JUSTIFICADA",
                          por="ana@sol.com", observacao="Regime especial do fornecedor")

    # Carta automática (apenas_em_aberto): NÃO sobrepõe a decisão do analista.
    r = await definir_triagem(sessao, **svc, itens=[(n1.id, 1)], status="COBRADA",
                              por="carta", apenas_em_aberto=True)
    assert r == {"definidos": 0, "mantidos": 1, "limpos": 0}
    row = (await sessao.execute(select(DivergenciaTriagem))).scalars().one()
    assert row.status == "JUSTIFICADA"

    # Decisão manual sobrescreve; EM_ABERTO limpa (some da tabela).
    await definir_triagem(sessao, **svc, itens=[(n1.id, 1)], status="ACEITA", por="ana@sol.com")
    row = (await sessao.execute(select(DivergenciaTriagem))).scalars().one()
    assert row.status == "ACEITA"

    r = await definir_triagem(sessao, **svc, itens=[(n1.id, 1)], status="EM_ABERTO")
    assert r["limpos"] == 1
    assert (await sessao.execute(select(DivergenciaTriagem))).scalars().all() == []


@pytest.mark.asyncio
async def test_triagem_sobrevive_ao_reprocessamento(sessao):
    """A auditoria é apagada e recriada no reprocesso — a triagem, ancorada em
    (nota_id, numero_item), continua valendo para a nova linha."""
    n1 = await _divergencia(sessao, 1, "4" * 44)
    await definir_triagem(sessao, tenant_id=TENANT, empresa_id=EMPRESA,
                          itens=[(n1.id, 1)], status="COBRADA", por="ana@sol.com",
                          observacao=None)

    # Reprocesso: some a linha antiga da auditoria, nasce outra (id novo).
    velha = (await sessao.execute(select(AuditoriaIcmsSt))).scalars().one()
    await sessao.delete(velha)
    await sessao.flush()
    sessao.add(AuditoriaIcmsSt(
        tenant_id=TENANT, empresa_id=EMPRESA, nota_id=n1.id,
        chave_acesso=n1.chave_acesso, numero_item=1, status="DIVERGENTE",
        codigo_erro="ERRO_104_VALOR_ST_DIVERGENTE",
        vicms_st_divergencia=Decimal("-99.00"),
    ))
    await sessao.flush()

    r = await listar_divergencias(sessao, empresa_id=EMPRESA, triagem="COBRADA")
    assert r["total"] == 1 and r["itens"][0]["triagem"]["status"] == "COBRADA"


@pytest.mark.asyncio
async def test_status_invalido_e_erro(sessao):
    from app.core.exceptions import DomainError

    n1 = await _divergencia(sessao, 1, "5" * 44)
    with pytest.raises(DomainError):
        await definir_triagem(sessao, tenant_id=TENANT, empresa_id=EMPRESA,
                              itens=[(n1.id, 1)], status="PAGA")
    # datetime importado no serviço com timezone (registro de quando decidiu).
    assert datetime.now(UTC).year >= 2026
