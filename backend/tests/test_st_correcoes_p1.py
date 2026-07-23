"""Parte 1 do roadmap do motor de ST (jul/2026) — regressão das 4 correções:

1. modBCST ausente (fornecedor nem tratou como ST) não trava mais: a matriz
   decide a base (MVA cadastrada → MVA; senão → valor da operação); pauta e
   listas (0/1/2/3/5) ganham código reprocessável.
2. Protocolo tri-state: par nunca avaliado → NAO_AUDITAVEL com código (em vez
   de mandar o cliente pagar antecipação indevida); situação e NCM respeitados.
3. Entrada com CST 60/CSOSN 500 (ST retido na cadeia) sai OK registrando o
   retido; parser extrai vBCSTRet/pST/vICMSSTRet/vICMSSubstituto/vFCPSTRet.
4. Nota sem data de emissão vira diagnóstico por item, nunca crash do lote.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.st_audit_service import StAuditService
from app.modules.fiscal.domain.parser import parse_xml
from app.modules.fiscal.domain.st import (
    Crt,
    EnquadramentoEmMemoria,
    FcpEmMemoria,
    ItemFiscal,
    MvaEmMemoria,
    Operacao,
    ProtocoloEmMemoria,
    StatusAuditoria,
    StAuditEngine,
)
from app.modules.fiscal.infrastructure.matrizes_loaders import (
    MatrizesLoader,
    _ProtocoloSnapshot,
)
from app.modules.fiscal.infrastructure.matrizes_models import MatrizProtocoloSt
from app.modules.fiscal.infrastructure.models import AuditoriaIcmsSt, Nota, NotaItem

_D = Decimal
DATA = date(2026, 6, 1)


def _engine(**kw) -> StAuditEngine:
    return StAuditEngine(
        mva_repo=kw.get("mva", MvaEmMemoria()),
        enquadramento_repo=kw.get("enq", EnquadramentoEmMemoria()),
        fcp_repo=kw.get("fcp", FcpEmMemoria()),
        protocolo_repo=kw.get("protocolo", ProtocoloEmMemoria()),
    )


def _item(**kw) -> ItemFiscal:
    base = dict(
        numero_item=1, ncm="85122011", cest="0100100", cfop="6404", orig="0",
        cst="10", mod_bc_st=4, v_prod=_D("1000"), q_com=_D("1"),
        v_icms=_D("120"), v_bc=_D("1000"), p_icms=_D("12"),
    )
    base.update(kw)
    return ItemFiscal(**base)


# ── 1. modBCST ausente ────────────────────────────────────────────────────── #
def test_modbcst_ausente_com_mva_na_matriz_audita_como_base_mva():
    """Fornecedor não tratou o item como ST (sem grupo ICMSST → modBCST=None):
    a MVA cadastrada define a base — mesma conta do caso canônico modBCST=4."""
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = _engine().auditar_item(_item(mod_bc_st=None), op)     # XML sem ST nenhum

    assert r.status == StatusAuditoria.DIVERGENTE             # devia ter retido
    assert r.memoria.base_st_calculada == _D("1502.44")       # base por MVA ajustada
    assert "ERRO_104_VALOR_ST_DIVERGENTE" in r.codigos_erro


def test_modbcst_ausente_sem_mva_usa_valor_da_operacao():
    """Sem MVA cadastrada para o NCM: base = valor da operação (modBCST 6
    implícito) — nada de travar em 'fora do núcleo'."""
    op = Operacao(uf_emit="MG", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    item = _item(ncm="99999999", cest="", mod_bc_st=None,
                 v_icms=_D("180"), p_icms=_D("18"))
    r = _engine().auditar_item(item, op)

    assert r.status == StatusAuditoria.DIVERGENTE
    assert r.memoria.base_st_calculada == _D("1000.00")       # valor da operação
    assert r.memoria.icms_st_calculado == _D("0.00")          # 180 débito − 180 dedução
    assert "ERRO_102_BC_ST_DIVERGENTE" in r.codigos_erro      # base não destacada


def test_modbcst_pauta_vira_pendencia_com_codigo_reprocessavel():
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = _engine().auditar_item(_item(mod_bc_st=5), op)        # pauta

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == ["ERRO_MODBCST_NAO_SUPORTADO"]   # filtrável e reprocessável
    assert "pauta" in (r.observacao or "").lower()


# ── 2. Protocolo tri-state ────────────────────────────────────────────────── #
def test_protocolo_snapshot_tristate():
    nunca = _ProtocoloSnapshot(curado=False, ncms_ativos=frozenset())
    assert nunca.tem_protocolo("SP", "MG", DATA, "85122011") is None

    par_inteiro = _ProtocoloSnapshot(curado=True, ncms_ativos=frozenset({"*"}))
    assert par_inteiro.tem_protocolo("SP", "MG", DATA, "85122011") is True

    por_ncm = _ProtocoloSnapshot(curado=True, ncms_ativos=frozenset({"851220"}))
    assert por_ncm.tem_protocolo("SP", "MG", DATA, "85122011") is True   # 8→6→4
    assert por_ncm.tem_protocolo("SP", "MG", DATA, "40111000") is False  # outro NCM

    denunciado = _ProtocoloSnapshot(curado=True, ncms_ativos=frozenset())
    assert denunciado.tem_protocolo("SP", "MG", DATA, "85122011") is False


def test_par_nunca_avaliado_trava_em_vez_de_apontar_antecipacao():
    """O erro grave que a Parte 1 corrige: par sem NENHUM registro na matriz
    mandava o CLIENTE recolher antecipação. Agora trava com código próprio."""
    snapshot = _ProtocoloSnapshot(curado=False, ncms_ativos=frozenset())
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = _engine(protocolo=snapshot).auditar_item(_item(), op)

    assert r.status == StatusAuditoria.NAO_AUDITAVEL
    assert r.codigos_erro == ["ERRO_PROTOCOLO_NAO_AVALIADO"]
    assert "ERRO_111_ST_ANTECIPACAO_DESTINATARIO" not in r.codigos_erro


def test_par_curado_sem_acordo_segue_como_antecipacao():
    snapshot = _ProtocoloSnapshot(curado=True, ncms_ativos=frozenset())
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
    r = _engine(protocolo=snapshot).auditar_item(
        _item(v_bc_st=_D("0"), v_icms_st=_D("0")), op
    )
    assert "ERRO_111_ST_ANTECIPACAO_DESTINATARIO" in r.codigos_erro


# ── 3. Entrada com ST retido (CST 60/500) ─────────────────────────────────── #
def test_entrada_cst60_sai_ok_registrando_o_retido():
    op = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA, saida=False)
    item = _item(cst="60", mod_bc_st=None,
                 v_bc_st_ret=_D("1500"), v_icms_st_ret=_D("120.50"))
    r = _engine().auditar_item(item, op)

    assert r.status == StatusAuditoria.OK
    assert "ST retido" in (r.observacao or "")
    assert "120.50" in (r.observacao or "")

    # CSOSN 500 idem (Simples revenda).
    r2 = _engine().auditar_item(_item(cst=None, csosn="500", mod_bc_st=None), op)
    assert r2.status == StatusAuditoria.OK


def test_parser_extrai_st_retido():
    xml = f"""<nfeProc><NFe><infNFe Id="NFe{'6' * 44}">
      <ide><mod>55</mod><serie>1</serie><nNF>77</nNF><dhEmi>2026-06-01T10:00:00-03:00</dhEmi></ide>
      <emit><CNPJ>11111111000111</CNPJ><xNome>F</xNome><CRT>3</CRT>
        <enderEmit><UF>MG</UF></enderEmit></emit>
      <dest><CNPJ>22222222000122</CNPJ><xNome>C</xNome><enderDest><UF>MG</UF></enderDest></dest>
      <det nItem="1">
        <prod><cProd>P1</cProd><xProd>Produto</xProd><NCM>40111000</NCM><CFOP>1403</CFOP>
          <uCom>UN</uCom><qCom>1</qCom><vUnCom>100.00</vUnCom><vProd>100.00</vProd></prod>
        <imposto><ICMS><ICMS60><orig>0</orig><CST>60</CST>
          <vBCSTRet>150.00</vBCSTRet><pST>19.50</pST>
          <vICMSSubstituto>12.00</vICMSSubstituto><vICMSSTRet>29.25</vICMSSTRet>
          <vFCPSTRet>3.00</vFCPSTRet></ICMS60></ICMS></imposto>
      </det>
      <total><ICMSTot><vNF>100.00</vNF></ICMSTot></total>
    </infNFe></NFe></nfeProc>""".encode()

    item = parse_xml(xml)["itens"][0]
    assert item["cst"] == "60"
    assert item["v_bc_st_ret"] == 150.0
    assert item["p_st_ret"] == 19.5
    assert item["v_icms_substituto"] == 12.0
    assert item["v_icms_st_ret"] == 29.25
    assert item["v_fcp_st_ret"] == 3.0


def test_schema_protocolo_aceita_sem_acordo_e_ncm():
    """O registro explícito de ausência de acordo (botão "Não há acordo") e o
    escopo por NCM entram pelo schema — antes toda linha nascia ATIVO."""
    import pytest

    from app.modules.fiscal.api.matrizes_schemas import MatrizProtocoloCreate

    d = MatrizProtocoloCreate(
        uf_origem="go", uf_destino="mg",
        numero_acordo="SEM ACORDO (registro do escritório)",
        situacao="sem_acordo", ncm="4011.70.00",
        data_inicio_vigencia=date(2000, 1, 1),
    ).normalizado()
    assert d["situacao"] == "SEM_ACORDO"
    assert d["uf_origem"] == "GO" and d["ncm"] == "40117000"

    with pytest.raises(ValueError):
        MatrizProtocoloCreate(
            uf_origem="GO", uf_destino="MG", numero_acordo="X 1/2020",
            situacao="QUALQUER", data_inicio_vigencia=date(2000, 1, 1),
        )


# ── 4. Data de emissão inválida não derruba o lote (+ loader do protocolo) ── #
_TABELAS = [Nota.__table__, NotaItem.__table__, AuditoriaIcmsSt.__table__,
            MatrizProtocoloSt.__table__]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def test_nota_sem_data_vira_diagnostico_por_item(sessao):
    tenant, empresa = uuid4(), uuid4()
    nota = Nota(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa, chave_acesso="9" * 44,
        tipo="NFe", fluxo="entrada", modelo="55", numero="1", crt_emit="3",
        nome_emit="X", cnpj_emit="11111111000111", uf_emit="SP", uf_dest="MG",
        data_emissao="", ano="2026", mes="06",
    )
    sessao.add(nota)
    sessao.add(NotaItem(id=uuid4(), tenant_id=tenant, nota_id=nota.id,
                        numero_item=1, descricao="P", cst="00",
                        valor_produto=_D("100")))
    await sessao.flush()

    registros = await StAuditService(sessao).auditar_nota(empresa, nota.id)

    assert len(registros) == 1
    assert registros[0].status == "NAO_AUDITAVEL"
    assert registros[0].codigo_erro == "ERRO_DATA_EMISSAO_INVALIDA"
    persistido = await sessao.scalar(select(AuditoriaIcmsSt))
    assert persistido is not None and "data de emiss" in persistido.observacao


async def test_loader_protocolo_sem_acordo_cura_o_par(sessao):
    """Linha SEM_ACORDO: o par vira CURADO sem virar acordo — o motor decide
    antecipação em vez de travar em 'não avaliado'."""
    loader = MatrizesLoader(sessao)

    # Par nunca avaliado → None (trava com código próprio no motor).
    snap = await loader._protocolo("GO", "MG", date(2026, 6, 1))
    assert snap.tem_protocolo("GO", "MG", date(2026, 6, 1), "40117000") is None

    sessao.add(MatrizProtocoloSt(
        uf_origem="GO", uf_destino="MG",
        numero_acordo="SEM ACORDO (registro do escritório)", situacao="SEM_ACORDO",
        data_inicio_vigencia=date(2000, 1, 1),
    ))
    await sessao.flush()

    snap2 = await loader._protocolo("GO", "MG", date(2026, 6, 1))
    assert snap2.curado is True
    assert snap2.tem_protocolo("GO", "MG", date(2026, 6, 1), "40117000") is False
