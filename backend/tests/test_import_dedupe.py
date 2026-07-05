"""Dedupe da importação de XML: reimportar o mesmo lote NUNCA duplica nota.

Duas frentes: (1) o mesmo arquivo em lotes separados vira "duplicada" no
resumo; (2) o mesmo arquivo repetido DENTRO do mesmo lote também deduplica
(o flush intermediário garante que o by_chave da mesma transação enxergue).
"""
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.cfop_rules.infrastructure.models import CfopRegra
from app.modules.companies.infrastructure.models import Empresa
from app.modules.contrapartes.infrastructure.models import Contraparte
from app.modules.fiscal.application.import_service import ImportService
from app.modules.fiscal.infrastructure.models import (
    NfeCteVinculo,
    Nota,
    NotaEvento,
    NotaItem,
)

_TABELAS = [
    Nota.__table__, NotaItem.__table__, NotaEvento.__table__,
    NfeCteVinculo.__table__, Contraparte.__table__, CfopRegra.__table__,
]

_CHAVE = "5" * 44
_CNPJ_EMPRESA = "22222222000122"

_NFE = f"""<nfeProc><NFe><infNFe Id="NFe{_CHAVE}">
  <ide><mod>55</mod><serie>1</serie><nNF>7</nNF><dhEmi>2026-06-01T10:00:00-03:00</dhEmi></ide>
  <emit><CNPJ>11111111000111</CNPJ><xNome>FORNECEDOR SP</xNome><CRT>3</CRT>
    <enderEmit><UF>SP</UF></enderEmit></emit>
  <dest><CNPJ>{_CNPJ_EMPRESA}</CNPJ><xNome>CLIENTE MG</xNome>
    <enderDest><UF>MG</UF></enderDest></dest>
  <det nItem="1">
    <prod><cProd>P1</cProd><xProd>Produto</xProd><NCM>40111000</NCM><CFOP>6102</CFOP>
      <uCom>UN</uCom><qCom>1</qCom><vUnCom>100.00</vUnCom><vProd>100.00</vProd></prod>
    <imposto><ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>100.00</vBC>
      <pICMS>12.00</pICMS><vICMS>12.00</vICMS></ICMS00></ICMS></imposto>
  </det>
  <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
</infNFe></NFe></nfeProc>""".encode()


class StorageFake:
    """Storage em memória: o suficiente para o ciclo staging → final do import."""

    def __init__(self):
        self.dados: dict[str, bytes] = {}

    def get(self, key: str) -> bytes:
        return self.dados[key]

    def put(self, key: str, content: bytes) -> None:
        self.dados[key] = content

    def delete(self, key: str) -> None:
        self.dados.pop(key, None)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _empresa(tenant_id) -> Empresa:
    return Empresa(
        id=uuid4(), tenant_id=tenant_id, cnpj=_CNPJ_EMPRESA, razao_social="CLIENTE MG",
    )


async def _importar(sessao, storage, tenant_id, empresa, chaves: list[str]) -> dict:
    for k in chaves:
        storage.put(k, _NFE)
    service = ImportService(sessao, storage)
    return await service.import_staged(
        tenant_id=tenant_id, empresa=empresa, user_id=uuid4(),
        staging=[{"key": k, "filename": f"{k}.xml"} for k in chaves],
    )


async def test_reimportar_mesmo_xml_nao_duplica(sessao):
    tenant_id = uuid4()
    empresa, storage = _empresa(tenant_id), StorageFake()

    r1 = await _importar(sessao, storage, tenant_id, empresa, ["lote1/a.xml"])
    assert r1["importadas"] == 1
    assert r1["duplicadas"] == []

    # Mesmo XML num segundo lote: vira "duplicada" no resumo, sem nova nota.
    r2 = await _importar(sessao, storage, tenant_id, empresa, ["lote2/a.xml"])
    assert r2["importadas"] == 0
    assert r2["duplicadas"] == [{"arquivo": "lote2/a.xml.xml", "chave": _CHAVE}]

    assert await sessao.scalar(select(func.count()).select_from(Nota)) == 1
    assert await sessao.scalar(select(func.count()).select_from(NotaItem)) == 1


async def test_mesmo_xml_repetido_no_mesmo_lote_deduplica(sessao):
    tenant_id = uuid4()
    empresa, storage = _empresa(tenant_id), StorageFake()

    r = await _importar(sessao, storage, tenant_id, empresa, ["a.xml", "b.xml"])

    assert r["importadas"] == 1
    assert len(r["duplicadas"]) == 1
    assert await sessao.scalar(select(func.count()).select_from(Nota)) == 1

    # E o valor persistido é o do XML (sanidade do caminho feliz).
    nota = (await sessao.execute(select(Nota))).scalar_one()
    assert nota.valor_total == Decimal("100.00")
    assert nota.fluxo == "entrada"
