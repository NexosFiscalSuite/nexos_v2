"""Verificação de IBS/CBS (ano-teste 2026): parser, classificação e backfill.

Gabarito legal: ADCT art. 125 (EC 132/2023) — destaque de IBS 0,1% + CBS 0,9%
em 2026 para o regime normal; Simples/MEI (CRT 1/4) dispensados.
"""
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.ibscbs_service import (
    ALIQUOTA_DIVERGENTE,
    DISPENSADO,
    OK,
    SEM_DESTAQUE,
    VALOR_DIVERGENTE,
    IbsCbsService,
    classificar_item,
)
from app.modules.fiscal.domain.parser import parse_xml
from app.modules.fiscal.infrastructure.models import Nota, NotaItem

_D = Decimal


# --------------------------------------------------------------------------- #
# Parser: extração do grupo <IBSCBS> (NT 2025.002)
# --------------------------------------------------------------------------- #
def _nfe(chave: str, ibscbs: str, crt: str = "3") -> bytes:
    return f"""<nfeProc><NFe><infNFe Id="NFe{chave}">
      <ide><mod>55</mod><serie>1</serie><nNF>10</nNF><dhEmi>2026-06-01T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>11111111000111</CNPJ><xNome>FORNECEDOR SP</xNome><CRT>{crt}</CRT>
        <enderEmit><UF>SP</UF></enderEmit></emit>
      <dest><CNPJ>22222222000122</CNPJ><xNome>CLIENTE MG</xNome>
        <enderDest><UF>MG</UF></enderDest></dest>
      <det nItem="1">
        <prod><cProd>P1</cProd><xProd>Produto</xProd><NCM>40111000</NCM><CFOP>6102</CFOP>
          <uCom>UN</uCom><qCom>1</qCom><vUnCom>1000.00</vUnCom><vProd>1000.00</vProd></prod>
        <imposto>
          <ICMS><ICMS00><orig>0</orig><CST>00</CST><vBC>1000.00</vBC>
            <pICMS>12.00</pICMS><vICMS>120.00</vICMS></ICMS00></ICMS>
          {ibscbs}
        </imposto>
      </det>
      <total><ICMSTot><vNF>1000.00</vNF></ICMSTot></total>
    </infNFe></NFe></nfeProc>""".encode()


_IBSCBS_OK = """<IBSCBS><CST>000</CST><cClassTrib>000001</cClassTrib>
  <gIBSCBS><vBC>1000.00</vBC>
    <gIBSUF><pIBSUF>0.10</pIBSUF><vIBSUF>1.00</vIBSUF></gIBSUF>
    <gIBSMun><pIBSMun>0.00</pIBSMun><vIBSMun>0.00</vIBSMun></gIBSMun>
    <vIBS>1.00</vIBS>
    <gCBS><pCBS>0.90</pCBS><vCBS>9.00</vCBS></gCBS>
  </gIBSCBS></IBSCBS>"""


def test_parser_extrai_grupo_ibscbs():
    parsed = parse_xml(_nfe("1" * 44, _IBSCBS_OK))
    item = parsed["itens"][0]
    assert item["cst_ibs_cbs"] == "000"
    assert item["v_bc_ibs_cbs"] == 1000.0
    assert item["p_ibs_uf"] == 0.10
    assert item["v_ibs_uf"] == 1.0
    assert item["p_ibs_mun"] == 0.0
    assert item["p_cbs"] == 0.90
    assert item["v_cbs"] == 9.0


def test_parser_sem_grupo_ibscbs_zera_campos():
    parsed = parse_xml(_nfe("2" * 44, ""))
    item = parsed["itens"][0]
    assert item["cst_ibs_cbs"] is None
    assert item["p_ibs_uf"] == 0.0
    assert item["v_cbs"] == 0.0


# --------------------------------------------------------------------------- #
# Classificação pura (o gabarito do ano-teste)
# --------------------------------------------------------------------------- #
def _cls(**kw) -> str:
    base = dict(
        crt_emit="3",
        p_ibs_uf=_D("0.10"), p_ibs_mun=_D("0"),
        v_ibs_uf=_D("1.00"), v_ibs_mun=_D("0"),
        p_cbs=_D("0.90"), v_cbs=_D("9.00"), v_bc=_D("1000"),
    )
    base.update(kw)
    return classificar_item(**base)


def test_destaque_correto_e_ok():
    assert _cls() == OK


def test_simples_e_dispensado_mesmo_sem_destaque():
    assert _cls(crt_emit="1", p_ibs_uf=_D("0"), v_ibs_uf=_D("0"),
                p_cbs=_D("0"), v_cbs=_D("0")) == DISPENSADO
    assert _cls(crt_emit="4", p_ibs_uf=_D("0"), v_ibs_uf=_D("0"),
                p_cbs=_D("0"), v_cbs=_D("0")) == DISPENSADO


def test_regime_normal_sem_destaque_e_apontado():
    assert _cls(p_ibs_uf=_D("0"), v_ibs_uf=_D("0"),
                p_cbs=_D("0"), v_cbs=_D("0")) == SEM_DESTAQUE


def test_aliquota_fora_do_teste_diverge():
    assert _cls(p_cbs=_D("1.50")) == ALIQUOTA_DIVERGENTE      # CBS != 0,9
    assert _cls(p_ibs_uf=_D("0.30")) == ALIQUOTA_DIVERGENTE   # IBS != 0,1


def test_ibs_dividido_entre_uf_e_municipio_soma_certa_e_ok():
    """Tolerante ao rateio: o que vale é o TOTAL do IBS = 0,1%."""
    assert _cls(p_ibs_uf=_D("0.05"), p_ibs_mun=_D("0.05"),
                v_ibs_uf=_D("0.50"), v_ibs_mun=_D("0.50")) == OK


def test_aliquota_certa_mas_conta_errada_diverge():
    assert _cls(v_cbs=_D("5.00")) == VALOR_DIVERGENTE         # 1000×0,9% = 9,00
    assert _cls(v_ibs_uf=_D("0.10")) == VALOR_DIVERGENTE      # 1000×0,1% = 1,00


# --------------------------------------------------------------------------- #
# Serviço (sqlite) + backfill
# --------------------------------------------------------------------------- #
_TABELAS = [Nota.__table__, NotaItem.__table__]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _nota(tenant, empresa, chave, crt="3", storage_key=None):
    return Nota(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa, chave_acesso=chave,
        tipo="NFe", fluxo="entrada", modelo="55", crt_emit=crt,
        nome_emit=f"EMIT {chave[:4]}", cnpj_emit=f"{chave[:8]}000199",
        data_emissao="2026-06-01", ano="2026", mes="06", storage_key=storage_key,
    )


def _item(tenant, nota, destaque: bool):
    kw = {}
    if destaque:
        kw = dict(v_bc_ibs_cbs=_D("1000"), p_ibs_uf=_D("0.10"), v_ibs_uf=_D("1.00"),
                  p_cbs=_D("0.90"), v_cbs=_D("9.00"))
    return NotaItem(
        id=uuid4(), tenant_id=tenant, nota_id=nota.id, numero_item=1,
        descricao="Produto", valor_produto=_D("1000"), **kw,
    )


async def test_verificar_agrega_e_ranqueia(sessao):
    tenant, empresa = uuid4(), uuid4()
    ok = _nota(tenant, empresa, "1" * 44)                 # normal com destaque
    sem = _nota(tenant, empresa, "2" * 44)                # normal SEM destaque
    simples = _nota(tenant, empresa, "3" * 44, crt="1")   # Simples sem destaque
    sessao.add_all([ok, sem, simples,
                    _item(tenant, ok, True), _item(tenant, sem, False),
                    _item(tenant, simples, False)])
    await sessao.flush()

    r = await IbsCbsService(sessao).verificar(empresa_id=empresa)

    assert r["total_itens"] == 3
    assert r["resumo"][OK]["itens"] == 1
    assert r["resumo"][SEM_DESTAQUE]["itens"] == 1
    assert r["resumo"][DISPENSADO]["itens"] == 1
    assert r["pct_conforme"] == 66.7                       # OK + DISPENSADO
    assert len(r["itens"]) == 1                            # só o problema real
    assert r["itens"][0]["status"] == SEM_DESTAQUE
    assert r["ranking_emitentes"][0]["cnpj"] == sem.cnpj_emit


class StorageFake:
    def __init__(self, dados):
        self.dados = dados

    def get(self, key):
        return self.dados[key]


async def test_reprocessar_preenche_notas_antigas(sessao):
    """Nota importada antes do módulo (campos zerados) ganha os valores do XML."""
    tenant, empresa = uuid4(), uuid4()
    chave = "4" * 44
    nota = _nota(tenant, empresa, chave, storage_key="xml/a.xml")
    sessao.add_all([nota, _item(tenant, nota, False)])     # campos IBS/CBS vazios
    await sessao.flush()

    storage = StorageFake({"xml/a.xml": _nfe(chave, _IBSCBS_OK)})
    r = await IbsCbsService(sessao).reprocessar(storage, empresa_id=empresa)
    assert r == {"notas_reprocessadas": 1, "falhas_leitura": 0}

    v = await IbsCbsService(sessao).verificar(empresa_id=empresa)
    assert v["resumo"][OK]["itens"] == 1                   # antes era SEM_DESTAQUE
