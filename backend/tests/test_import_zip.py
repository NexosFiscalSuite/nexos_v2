"""Importação de .zip: expansão no worker, com guardas anti zip-bomb.

Cada XML interno é processado como se fosse enviado avulso (mesmo parse,
mesmo dedupe); PDFs e afins dentro do ZIP são ignorados; ZIP aninhado e
membros gigantes viram erro relatado sem derrubar o lote.
"""
import io
import zipfile
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
_CNPJ_EMPRESA = "22222222000122"


def _nfe(chave: str) -> bytes:
    return f"""<nfeProc><NFe><infNFe Id="NFe{chave}">
      <ide><mod>55</mod><serie>1</serie><nNF>{chave[:3]}</nNF><dhEmi>2026-06-01T10:00:00-03:00</dhEmi></ide>
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


def _zip(arquivos: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for nome, conteudo in arquivos.items():
            zf.writestr(nome, conteudo)
    return buf.getvalue()


class StorageFake:
    def __init__(self):
        self.dados = {}

    def get(self, key):
        return self.dados[key]

    def put(self, key, content):
        self.dados[key] = content

    def delete(self, key):
        self.dados.pop(key, None)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def _importar(sessao, storage, conteudo: bytes, nome: str) -> dict:
    tenant_id = uuid4()
    empresa = Empresa(id=uuid4(), tenant_id=tenant_id, cnpj=_CNPJ_EMPRESA,
                      razao_social="CLIENTE MG")
    storage.put("staging/lote", conteudo)
    return await ImportService(sessao, storage).import_staged(
        tenant_id=tenant_id, empresa=empresa, user_id=uuid4(),
        staging=[{"key": "staging/lote", "filename": nome}],
    )


async def test_zip_expande_e_importa_os_xmls(sessao):
    """ZIP com 2 NF-e + 1 PDF: importa as notas, ignora o resto, sem erro."""
    conteudo = _zip({
        "pasta/nota1.xml": _nfe("6" * 44),
        "nota2.xml": _nfe("7" * 44),
        "danfe.pdf": b"%PDF-1.4 lixo",
    })
    r = await _importar(sessao, StorageFake(), conteudo, "junho.zip")

    assert r["importadas"] == 2
    assert r["erros"] == []
    assert r["total_arquivos"] == 2                       # 2 XMLs (o .zip sai da conta)
    assert await sessao.scalar(select(func.count()).select_from(Nota)) == 2

    # Nome rastreável: lote » arquivo interno (útil no relatório de erros).
    # (sem erro aqui; a rastreabilidade é validada no teste de zip aninhado)


async def test_zip_dedupe_continua_valendo(sessao):
    """A mesma chave dentro do ZIP (duplicada) não vira nota duplicada."""
    conteudo = _zip({"a.xml": _nfe("8" * 44), "b.xml": _nfe("8" * 44)})
    r = await _importar(sessao, StorageFake(), conteudo, "lote.zip")

    assert r["importadas"] == 1
    assert len(r["duplicadas"]) == 1
    assert await sessao.scalar(select(func.count()).select_from(Nota)) == 1


async def test_zip_aninhado_e_corrompido_viram_erro_relatado(sessao):
    interno = _zip({"x.xml": _nfe("9" * 44)})
    conteudo = _zip({"ok.xml": _nfe("1" * 43 + "2"), "dentro.zip": interno})
    r = await _importar(sessao, StorageFake(), conteudo, "misto.zip")
    assert r["importadas"] == 1                           # o XML solto entrou
    assert any("ZIP dentro de ZIP" in e["erro"] for e in r["erros"])
    assert any("dentro.zip" in e["arquivo"] for e in r["erros"])

    r2 = await _importar(sessao, StorageFake(), b"PK\x03\x04nao-e-zip", "quebrado.zip")
    assert r2["importadas"] == 0
    assert any("corrompido" in e["erro"] for e in r2["erros"])


async def test_xml_avulso_segue_intocado(sessao):
    r = await _importar(sessao, StorageFake(), _nfe("3" * 44), "avulso.xml")
    assert r["importadas"] == 1
    assert r["total_arquivos"] == 1
