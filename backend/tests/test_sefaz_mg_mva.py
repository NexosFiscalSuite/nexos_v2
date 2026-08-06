"""MVA de MG (Fase 5): parser do Anexo VII (puro, sem rede) e o diff→proposta
com as regras fail-closed — item sem margem fica fora, fonte ambígua fica
fora, curadoria manual nunca é tocada, mudança vira NOVA_VIGENCIA."""
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.propostas_service import PropostasService
from app.modules.fiscal.crawlers.propor import (
    BASE_LEGAL_AUTO_MVA,
    propor_mva,
    propor_protocolos_mg,
)
from app.modules.fiscal.crawlers.sefaz_mg_mva import (
    MvaRecord,
    SefazMgMvaExtractor,
    resolver_origens,
)
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.propostas_models import MatrizProposta
from app.shared.domain.uf import CURINGA_UF

# Amostra no formato real do Anexo VII (Parte 2): célula de layout vazia à
# frente, cabeçalho, item com 2 NCM, item SEM margem ('-') e uma tabela sem a
# célula de layout (larguras variam entre capítulos).
_HTML = """
<html><body>
<table><tr><td>menu de layout</td></tr></table>
<p>Âmbito de Aplicação da Substituição Tributária:</p>
<p>16.1 Interno e nas seguintes unidades da Federação: São Paulo
 (Protocolo ICMS 32/09) e Rondônia (Protocolo ICMS 32/09).</p>
<p>16.2 Interno.</p>
<table>
 <tr><td></td><td>ITEM</td><td>CEST</td><td>NBM/SH</td><td>DESCRIÇÃO</td><td>ÂMBITO DE APLICAÇÃO</td><td>MVA (%)</td></tr>
 <tr><td></td><td>1.0</td><td>01.001.00</td><td>3815.12.10 3815.12.90</td><td>Catalisadores em colmeia cerâmica</td><td>1.1</td><td>71,78</td></tr>
 <tr><td></td><td>2.0</td><td>01.002.00</td><td>3917</td><td>Tubos e seus acessórios</td><td>1.1</td><td>-</td></tr>
</table>
<table>
 <tr><td>1.0</td><td>16.001.00</td><td>4011.10.00</td><td>Pneus novos de automóveis</td><td>16.1 (Exceção: Rondônia)</td><td>42</td></tr>
</table>
</body></html>
"""


def test_parse_ancora_no_cest_e_descarta_sem_margem():
    # latin-1 (encoding real da SEFAZ-MG) e utf-8 dão o mesmo resultado.
    for raw in (_HTML.encode("latin-1"), _HTML.encode("utf-8")):
        regs = SefazMgMvaExtractor().parse(raw)
        assert [(r.cest, r.ncm, str(r.mva)) for r in regs] == [
            ("0100100", "38151210", "71.78"),
            ("0100100", "38151290", "71.78"),
            ("1600100", "40111000", "42"),
        ]
    regs = SefazMgMvaExtractor().parse(_HTML.encode("latin-1"))
    assert regs[0].descricao.startswith("Catalisadores em colmeia cerâmica")
    assert "Rondônia" in regs[2].ambito
    # Código do âmbito e exceções por item, parseados da célula.
    assert regs[2].ambitos == ("16.1",) and regs[2].excecoes == ("RO",)


def test_parse_ambitos_legenda_oficial():
    """A legenda 'Âmbito de Aplicação' vira código → [(UF, acordo)] — a fonte
    da matriz de Protocolos com a base legal item a item."""
    amb = SefazMgMvaExtractor().parse_ambitos(_HTML.encode("latin-1"))
    assert amb["16.1"] == [("SP", "Protocolo ICMS 32/09"), ("RO", "Protocolo ICMS 32/09")]
    assert amb["16.2"] == []            # só interno: nenhum par interestadual


def test_parse_internos_marca_os_ambitos_que_valem_dentro_de_mg():
    """'Interno e nas seguintes UF' e 'Interno.' são ambos internos — é isso
    que dá origem à linha de MVA da operação MG→MG."""
    internos = SefazMgMvaExtractor().parse_internos(_HTML.encode("latin-1"))
    assert internos == frozenset({"16.1", "16.2"})


def test_resolver_origens_traduz_o_ambito_em_uf_de_origem():
    """O âmbito diz EM QUE OPERAÇÕES a margem publicada vale: interna (MG) e
    entradas das UFs com acordo, menos as exceções do item. Código de âmbito
    que a legenda não define não vira palpite — cai no curinga."""
    raw = _HTML.encode("latin-1")
    ex = SefazMgMvaExtractor()
    regs = resolver_origens(ex.parse(raw), ex.parse_ambitos(raw), ex.parse_internos(raw))
    por_cest = {r.cest: r for r in regs}

    # 16.1 = interno + SP + RO; o item traz "Exceção: Rondônia" → RO sai.
    assert por_cest["1600100"].ufs_origem == ("MG", "SP")
    # Âmbito 1.1 não está na legenda desta amostra: sem origem resolvida.
    assert por_cest["0100100"].ufs_origem == ()
    assert por_cest["0100100"].origens() == (CURINGA_UF,)


# ── Diff → propostas ─────────────────────────────────────────────────────────
PISO = date(2026, 6, 1)
MUDANCA = date(2026, 8, 1)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            MatrizMva.__table__, MatrizProtocoloSt.__table__, MatrizProposta.__table__,
        ])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def _propor(s: AsyncSession, regs: list[MvaRecord]) -> dict:
    return await propor_mva(
        s, regs, uf="MG", vigencia_inicio=PISO, vigencia_mudanca=MUDANCA, fonte="teste",
    )


@pytest.mark.asyncio
async def test_par_novo_vira_inserir_com_piso(sessao):
    r = await _propor(sessao, [MvaRecord("1600100", "40111000", Decimal("42"))])
    assert r["propostas"] == 1

    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")
    linha = (await sessao.execute(select(MatrizMva))).scalars().one()
    assert linha.mva_original == Decimal("42.00")
    assert linha.data_inicio_vigencia == PISO
    assert linha.base_legal.startswith(BASE_LEGAL_AUTO_MVA)


@pytest.mark.asyncio
async def test_uma_proposta_por_uf_de_origem_do_ambito(sessao):
    """Cada origem do âmbito vira uma linha própria de MVA (mesmo padrão dos
    protocolos) — MAIS a linha de regra geral (curinga) com a mesma margem,
    para o fornecedor de estado fora do acordo."""
    regs = [MvaRecord("1600100", "40111000", Decimal("42"),
                      ambitos=("16.1",), ufs_origem=("MG", "SP"))]
    r = await _propor(sessao, regs)
    assert r["propostas"] == 3 and r["com_origem"] == 2
    assert r["curingas_gerais"] == 1 and r["curingas_ambiguas"] == 0

    props = (await sessao.execute(
        select(MatrizProposta).order_by(MatrizProposta.id)
    )).scalars().all()
    assert {p.payload["uf_origem"] for p in props} == {"MG", "SP", CURINGA_UF}
    assert all(p.payload["uf_destino"] == "MG" for p in props)

    # As três aprovam sem conflito de vigência: uf_origem está na CHAVE_VIGENCIA.
    for p in props:
        await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")
    linhas = (await sessao.execute(select(MatrizMva))).scalars().all()
    assert {(x.uf_origem, x.uf_destino) for x in linhas} == {
        ("MG", "MG"), ("SP", "MG"), (CURINGA_UF, "MG"),
    }
    # Todas com a MESMA margem publicada — a curinga não inventa número.
    assert {x.mva_original for x in linhas} == {Decimal("42.00")}

    # Rodada seguinte: já curado, nada volta para a fila (idempotente).
    r2 = await _propor(sessao, regs)
    assert r2["propostas"] == 0 and r2["sem_mudanca"] == 3


@pytest.mark.asyncio
async def test_regra_geral_cobre_fornecedor_de_fora_do_ambito(sessao):
    """A regressão de 06/08: item com âmbito curto (SP) ficava SEM margem para
    nota vinda de outro estado e o ST saía a menos. Agora sai também a linha
    curinga com a margem publicada — a específica continua vencendo no motor."""
    regs = [MvaRecord("1600100", "40111000", Decimal("42"),
                      ambitos=("16.1",), ufs_origem=("SP",))]
    r = await _propor(sessao, regs)
    assert r["curingas_gerais"] == 1

    props = (await sessao.execute(select(MatrizProposta))).scalars().all()
    por_origem = {p.payload["uf_origem"]: p for p in props}
    geral = por_origem[CURINGA_UF]
    assert geral.payload["mva_original"] == "42"
    assert geral.chave_resumo.startswith("qualquer origem (regra geral) → MG ·")
    # Base legal do anexo, sem citar o âmbito (a geral vale FORA dele).
    assert geral.payload["base_legal"].startswith(BASE_LEGAL_AUTO_MVA)
    assert "âmbito" not in geral.payload["base_legal"]
    # Hash diferente do da linha específica: não colide nem é suprimida.
    assert geral.hash_proposta != por_origem["SP"].hash_proposta


@pytest.mark.asyncio
async def test_par_com_margens_divergentes_nao_ganha_regra_geral(sessao):
    """Trava da regra geral: o mesmo NCM+CEST com duas margens publicadas em
    âmbitos diferentes não tem 'a margem geral' — eleger uma seria palpite.
    Fail-closed: nenhuma curinga, e o caso é CONTADO para o curador."""
    regs = [
        MvaRecord("1600100", "40111000", Decimal("42"),
                  ambitos=("16.1",), ufs_origem=("SP",)),
        MvaRecord("1600100", "40111000", Decimal("53"),
                  ambitos=("16.3",), ufs_origem=("RJ",)),
    ]
    r = await _propor(sessao, regs)
    assert r["curingas_gerais"] == 0 and r["curingas_ambiguas"] == 1
    assert r["propostas"] == 2 and r["ambiguos"] == 0

    origens = {
        p.payload["uf_origem"]
        for p in (await sessao.execute(select(MatrizProposta))).scalars()
    }
    assert origens == {"SP", "RJ"}, "não pode existir linha de qualquer origem"


@pytest.mark.asyncio
async def test_curinga_do_anexo_nao_e_duplicada_pela_regra_geral(sessao):
    """Par que já tem linha sem origem (âmbito ilegível) não ganha uma segunda
    curinga — senão a mesma chave brigaria consigo mesma na aprovação."""
    regs = [
        MvaRecord("1600100", "40111000", Decimal("42"), ufs_origem=("SP",)),
        MvaRecord("1600100", "40111000", Decimal("42")),          # sem âmbito legível
    ]
    r = await _propor(sessao, regs)
    assert r["curingas_gerais"] == 0 and r["propostas"] == 2

    props = (await sessao.execute(select(MatrizProposta))).scalars().all()
    assert sorted(p.payload["uf_origem"] for p in props) == ["*", "SP"]
    for p in props:
        await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")


@pytest.mark.asyncio
async def test_margens_diferentes_por_origem_deixam_de_ser_ambiguas(sessao):
    """Antes da origem na chave, duas margens do mesmo par eram conflito e o
    item ficava SEM MVA nenhuma. Com a origem, são duas regras legítimas."""
    r = await _propor(sessao, [
        MvaRecord("1600100", "40111000", Decimal("42"), ufs_origem=("MG",)),
        MvaRecord("1600100", "40111000", Decimal("45"), ufs_origem=("SP",)),
    ])
    # Duas margens no mesmo par: nenhuma regra geral (não há "a" margem).
    assert r["ambiguos"] == 0 and r["propostas"] == 2
    assert r["curingas_gerais"] == 0 and r["curingas_ambiguas"] == 1

    # …mas o conflito DENTRO da mesma origem continua fail-closed.
    r2 = await _propor(sessao, [
        MvaRecord("1600200", "40112000", Decimal("42"), ufs_origem=("SP",)),
        MvaRecord("1600200", "40112000", Decimal("45"), ufs_origem=("SP",)),
    ])
    assert r2["ambiguos"] == 1 and r2["propostas"] == 0


@pytest.mark.asyncio
async def test_mudanca_em_linha_auto_vira_nova_vigencia(sessao):
    sessao.add(MatrizMva(
        ncm="40111000", cest="1600100", uf_destino="MG",
        mva_original=Decimal("40.00"), base_legal=BASE_LEGAL_AUTO_MVA,
        data_inicio_vigencia=PISO,
    ))
    await sessao.flush()
    r = await _propor(sessao, [MvaRecord("1600100", "40111000", Decimal("42"))])
    assert r["propostas"] == 1

    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    assert p.acao == "NOVA_VIGENCIA" and p.linha_atual["mva_original"] == "40.00"

    await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")
    linhas = (await sessao.execute(
        select(MatrizMva).order_by(MatrizMva.data_inicio_vigencia)
    )).scalars().all()
    # ADR-0002: a antiga encerra na véspera; a nova vale desde a detecção.
    assert linhas[0].data_fim_vigencia == date(2026, 7, 31)
    assert (linhas[1].mva_original, linhas[1].data_inicio_vigencia) == (Decimal("42.00"), MUDANCA)


@pytest.mark.asyncio
async def test_curadoria_manual_nunca_e_tocada(sessao):
    """MVA 35% de tintas cadastrada na mão (regra 5 do CLAUDE.md): o robô vendo
    outra margem na fonte NÃO propõe nada sobre linha manual."""
    sessao.add(MatrizMva(
        ncm="32081000", cest="2400100", uf_destino="MG",
        mva_original=Decimal("35.00"), base_legal="Decisão do João (ago/2026)",
        data_inicio_vigencia=PISO,
    ))
    await sessao.flush()
    r = await _propor(sessao, [MvaRecord("2400100", "32081000", Decimal("48"))])
    assert r["propostas"] == 0 and r["sem_mudanca"] == 1


@pytest.mark.asyncio
async def test_protocolos_do_ambito_viram_propostas_escopadas(sessao):
    """A legenda do âmbito vira acordo UF→MG POR NCM (nunca par inteiro);
    a exceção do item exclui a UF; aprovar dois escopos de NCM do MESMO
    acordo não conflita (chave de vigência inclui o NCM)."""
    ambitos = {"16.1": [("SP", "Protocolo ICMS 32/09"), ("RO", "Protocolo ICMS 32/09")]}
    regs = [
        MvaRecord("1600100", "40111000", Decimal("42"),
                  ambitos=("16.1",), excecoes=("RO",)),
        MvaRecord("1600200", "40112000", Decimal("45"), ambitos=("16.1",)),
    ]
    r = await propor_protocolos_mg(
        sessao, regs, ambitos, vigencia_inicio=PISO, fonte="teste",
    )
    # Item 1: só SP (RO é exceção). Item 2: SP e RO → 3 alvos no total.
    assert r["alvos"] == 3 and r["propostas"] == 3

    svc = PropostasService(sessao)
    pendentes = (await sessao.execute(
        select(MatrizProposta).where(MatrizProposta.tipo_matriz == "protocolos")
        .order_by(MatrizProposta.id)
    )).scalars().all()
    assert all("Protocolo ICMS 32/09" in p.payload["base_legal"] for p in pendentes)
    assert all("âmbito 16.1" in p.payload["base_legal"] for p in pendentes)

    # Dois escopos de NCM do MESMO acordo SP→MG aprovam sem conflito.
    for p in pendentes:
        await svc.aprovar(p.id, revisor="ana@sol.com")
    linhas = (await sessao.execute(select(MatrizProtocoloSt))).scalars().all()
    assert len(linhas) == 3
    assert {(x.uf_origem, x.ncm) for x in linhas} == {
        ("SP", "40111000"), ("SP", "40112000"), ("RO", "40112000"),
    }
    assert all(x.situacao == "ATIVO" and x.uf_destino == "MG" for x in linhas)

    # Re-propor: tudo já curado — nada novo na fila.
    r2 = await propor_protocolos_mg(
        sessao, regs, ambitos, vigencia_inicio=PISO, fonte="teste",
    )
    assert r2["propostas"] == 0 and r2["ja_curados"] == 3


@pytest.mark.asyncio
async def test_fonte_ambigua_fica_fora(sessao):
    """Mesmo par com MVAs distintas na própria fonte: fail-closed, sem proposta."""
    r = await _propor(sessao, [
        MvaRecord("1600100", "40111000", Decimal("42"), ambito="16.1"),
        MvaRecord("1600100", "40111000", Decimal("45"), ambito="16.3"),
    ])
    assert r["propostas"] == 0 and r["ambiguos"] == 1

    # E a supressão por hash segue valendo para o que É proposto.
    await _propor(sessao, [MvaRecord("0100100", "38151210", Decimal("71.78"))])
    r3 = await _propor(sessao, [MvaRecord("0100100", "38151210", Decimal("71.78"))])
    assert r3["propostas"] == 0 and r3["suprimidas"] == 1
