"""Fase 1 da automação: o robô PROPÕE, o curador aprova — nada entra direto.

Cobre o diff→proposta (INSERIR/ATUALIZAR, curadoria manual intocada,
supressão por hash de pendente e de rejeitada), a aplicação com as regras de
vigência do ADR-0002 e o snapshot da fonte com detecção de mudança por hash.
"""
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.core.exceptions import ConflictError
from app.modules.fiscal.application.propostas_service import PropostasService
from app.modules.fiscal.crawlers.base import CestRecord
from app.modules.fiscal.crawlers.propor import (
    BASE_LEGAL_AUTO,
    propor_enquadramento,
    registrar_snapshot,
)
from app.modules.fiscal.infrastructure.matrizes_models import MatrizEnquadramentoSt
from app.modules.fiscal.infrastructure.propostas_models import (
    FonteSnapshot,
    MatrizProposta,
)

VIG = date(2026, 6, 1)
REGS = [
    CestRecord("0100500", "40111000", "Pneus novos", "Autopeças"),
    CestRecord("0300100", "22030000", "Cerveja", "Cervejas"),
]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            MatrizEnquadramentoSt.__table__,
            MatrizProposta.__table__,
            FonteSnapshot.__table__,
        ])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def _propor(s: AsyncSession, regs=REGS, uf="MG") -> dict:
    return await propor_enquadramento(s, regs, uf=uf, vigencia_inicio=VIG, fonte="teste")


@pytest.mark.asyncio
async def test_universo_novo_vira_proposta_e_nada_entra_na_matriz(sessao):
    r = await _propor(sessao)
    assert r["propostas"] == 2
    # A matriz continua VAZIA — o robô não escreve direto (Fase 1).
    assert (await sessao.execute(select(MatrizEnquadramentoSt))).scalars().all() == []


@pytest.mark.asyncio
async def test_pendente_e_rejeitada_suprimem_reproposta(sessao):
    await _propor(sessao)
    r2 = await _propor(sessao)
    assert r2["propostas"] == 0 and r2["suprimidas"] == 2      # pendentes seguram

    pendentes = (await sessao.execute(
        select(MatrizProposta).order_by(MatrizProposta.id)
    )).scalars().all()
    svc = PropostasService(sessao)
    await svc.rejeitar(pendentes[0].id, revisor="ana@sol.com", motivo="MG não adota")
    await svc.aprovar(pendentes[1].id, revisor="ana@sol.com")

    r3 = await _propor(sessao)
    # A rejeitada NÃO volta à fila; a aprovada agora existe igual na matriz.
    assert r3["propostas"] == 0 and r3["suprimidas"] == 1 and r3["sem_mudanca"] == 1


@pytest.mark.asyncio
async def test_aprovar_grava_na_matriz_com_revisor(sessao):
    await _propor(sessao, regs=[REGS[0]])
    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    aprovada = await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")
    assert aprovada.status == "APROVADA"
    assert aprovada.revisado_por == "ana@sol.com" and aprovada.revisado_em is not None

    linha = (await sessao.execute(select(MatrizEnquadramentoSt))).scalars().one()
    assert (linha.uf_destino, linha.ncm, linha.regime) == ("MG", "40111000", "ST")
    assert linha.data_inicio_vigencia == VIG
    assert linha.base_legal == BASE_LEGAL_AUTO


@pytest.mark.asyncio
async def test_curadoria_manual_nunca_e_tocada(sessao):
    """O analista marcou TN de propósito (adesão estadual): o universo do
    CONFAZ não sobrepõe a decisão — nenhuma proposta é gerada."""
    sessao.add(MatrizEnquadramentoSt(
        uf_destino="MG", ncm="40111000", cest="0100500", regime="TN",
        base_legal="Decisão do analista", data_inicio_vigencia=VIG,
    ))
    await sessao.flush()
    r = await _propor(sessao, regs=[REGS[0]])
    assert r["propostas"] == 0 and r["sem_mudanca"] == 1


@pytest.mark.asyncio
async def test_linha_auto_com_segmento_novo_vira_atualizar(sessao):
    sessao.add(MatrizEnquadramentoSt(
        uf_destino="MG", ncm="40111000", cest="0100500", regime="ST",
        segmento="Antigo", base_legal=BASE_LEGAL_AUTO, data_inicio_vigencia=VIG,
    ))
    await sessao.flush()
    r = await _propor(sessao, regs=[REGS[0]])
    assert r["propostas"] == 1

    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    assert p.acao == "ATUALIZAR" and p.linha_atual["segmento"] == "Antigo"

    await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")
    linha = (await sessao.execute(select(MatrizEnquadramentoSt))).scalars().one()
    assert linha.segmento == "Autopeças"


@pytest.mark.asyncio
async def test_conflito_de_vigencia_nao_aprova_e_mantem_pendente(sessao):
    await _propor(sessao, regs=[REGS[0]])
    # Entre a proposta e a revisão, o analista cadastrou a chave na mão.
    sessao.add(MatrizEnquadramentoSt(
        uf_destino="MG", ncm="40111000", cest="0100500", regime="ST",
        base_legal="Manual", data_inicio_vigencia=date(2026, 1, 1),
    ))
    await sessao.flush()
    p = (await sessao.execute(select(MatrizProposta))).scalars().one()
    with pytest.raises(ConflictError):
        await PropostasService(sessao).aprovar(p.id, revisor="ana@sol.com")
    assert p.status == "PENDENTE"        # segue na fila para rejeição consciente


@pytest.mark.asyncio
async def test_aprovar_lote_reporta_falhas_sem_derrubar(sessao):
    await _propor(sessao)                # 2 propostas MG
    # Uma vai conflitar: a chave do pneu foi cadastrada manualmente depois.
    sessao.add(MatrizEnquadramentoSt(
        uf_destino="MG", ncm="40111000", cest="0100500", regime="ST",
        base_legal="Manual", data_inicio_vigencia=date(2026, 1, 1),
    ))
    await sessao.flush()
    r = await PropostasService(sessao).aprovar_lote(revisor="ana@sol.com", uf="MG")
    assert r["aprovadas"] == 1 and len(r["falhas"]) == 1
    assert "sobrepõe" in r["falhas"][0]["erro"]


@pytest.mark.asyncio
async def test_snapshot_detecta_mudanca_por_hash(sessao):
    m1, id1 = await registrar_snapshot(sessao, fonte="confaz", url="u", conteudo=b"v1")
    m2, id2 = await registrar_snapshot(sessao, fonte="confaz", url="u", conteudo=b"v1")
    m3, id3 = await registrar_snapshot(sessao, fonte="confaz", url="u", conteudo=b"v2")
    assert (m1, m2, m3) == (True, False, True)
    assert id1 == id2 and id2 != id3
    # Sem mudança não há linha nova — a tabela não cresce à toa.
    assert len((await sessao.execute(select(FonteSnapshot))).scalars().all()) == 2
