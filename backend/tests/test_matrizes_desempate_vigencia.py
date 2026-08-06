"""Desempate DETERMINÍSTICO das vigências sobrepostas nos snapshots do loader.

Os snapshots montam dicionários chave→valor, então "quem escreve por último
vence". Sem ORDER BY explícito, quem escreve por último é a ordem que o banco
resolveu devolver — indefinida: a MESMA nota podia ser auditada com regras
diferentes em execuções diferentes.

A UNIQUE e o `sobreposicao_existente` barram a sobreposição pela API, mas dado
que entrou por outro caminho (carga antiga, import, migração) pode estar lá.
A regra passou a ser única e explícita: vence a `data_inicio_vigencia` MAIS
RECENTE e, no empate, o maior `id`.

Cada teste insere a linha NOVA primeiro e a ANTIGA depois — a ordem hostil, em
que "a última que o laço escreveu" seria justamente a errada. Sem o ORDER BY,
parte destes testes fica vermelha no SQLite e parte passa por acidente (o
planejador às vezes varre pelo índice UNIQUE, que já é ordenado por data) —
o acidente é exatamente o problema: a garantia tem de vir do ORDER BY.
"""
from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.domain.st import Crt, Operacao
from app.modules.fiscal.domain.st.enums import Regime
from app.modules.fiscal.domain.st.model import ItemFiscal
from app.modules.fiscal.infrastructure.matrizes_loaders import (
    MatrizesLoader,
    _desempate_vigencia,
)
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)

NCM = "40111000"
CEST = "0100500"
DATA = date(2026, 7, 1)
OP = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=DATA)
ITEM = ItemFiscal(numero_item=1, ncm=NCM, cest=CEST, cfop="6404", orig="0")


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tabelas = [
        MatrizMva.__table__, MatrizEnquadramentoSt.__table__, MatrizFcp.__table__,
        MatrizProtocoloSt.__table__, MatrizAliquota.__table__,
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=tabelas)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def test_mva_sobreposta_vence_a_vigencia_mais_recente(sessao):
    nova = MatrizMva(
        ncm=NCM, cest=CEST, uf_origem="SP", uf_destino="MG",
        mva_original=Decimal("55.00"), data_inicio_vigencia=date(2026, 1, 1),
    )
    antiga = MatrizMva(
        ncm=NCM, cest=CEST, uf_origem="SP", uf_destino="MG",
        mva_original=Decimal("40.00"), data_inicio_vigencia=date(2023, 1, 1),
    )
    sessao.add_all([nova, antiga])          # ordem hostil: a nova entra antes
    await sessao.flush()

    achado = (await MatrizesLoader(sessao).hidratar([ITEM], OP)).mva.buscar(
        NCM, CEST, "SP", "MG", DATA
    )
    assert achado.mva_original == Decimal("55.00")
    assert achado.matriz_id == nova.id


async def test_aliquota_sobreposta_vence_a_vigencia_mais_recente(sessao):
    nova = MatrizAliquota(
        uf_destino="MG", ncm="GERAL", aliq_modal=Decimal("20.50"),
        data_inicio_vigencia=date(2026, 4, 1),
    )
    antiga = MatrizAliquota(
        uf_destino="MG", ncm="GERAL", aliq_modal=Decimal("18.00"),
        data_inicio_vigencia=date(2024, 1, 1),
    )
    sessao.add_all([nova, antiga])
    await sessao.flush()

    achado = (await MatrizesLoader(sessao).hidratar([ITEM], OP)).aliquota.buscar(
        NCM, "MG", DATA
    )
    assert achado.modal == Decimal("20.50")
    assert achado.matriz_id == nova.id


async def test_enquadramento_sobreposto_vence_a_vigencia_mais_recente(sessao):
    sessao.add_all([
        MatrizEnquadramentoSt(
            uf_destino="MG", ncm=NCM, cest=CEST, regime="ST",
            data_inicio_vigencia=date(2026, 1, 1),
        ),
        MatrizEnquadramentoSt(
            uf_destino="MG", ncm=NCM, cest=CEST, regime="TN",
            data_inicio_vigencia=date(2023, 1, 1),
        ),
    ])
    await sessao.flush()

    snap = (await MatrizesLoader(sessao).hidratar([ITEM], OP)).enquadramento
    assert snap.regime(NCM, CEST, "SP", "MG", DATA) == Regime.ST


async def test_fcp_sobreposto_vence_a_vigencia_mais_recente(sessao):
    sessao.add_all([
        MatrizFcp(
            uf_destino="MG", ncm="GERAL", aliq_fcp_st=Decimal("2.00"),
            data_inicio_vigencia=date(2026, 1, 1),
        ),
        MatrizFcp(
            uf_destino="MG", ncm="GERAL", aliq_fcp_st=Decimal("1.00"),
            data_inicio_vigencia=date(2023, 1, 1),
        ),
    ])
    await sessao.flush()

    snap = (await MatrizesLoader(sessao).hidratar([ITEM], OP)).fcp
    assert snap.aliquota_st(NCM, "MG", DATA) == Decimal("2.00")


async def test_sem_sobreposicao_o_desempate_nao_muda_nada(sessao):
    """Correção de determinismo, não mudança de regra: com as vigências
    encerradas na ordem certa (o cadastro correto), a resposta é a mesma de
    antes — a linha vigente NA DATA, e só ela."""
    sessao.add_all([
        MatrizMva(
            ncm=NCM, cest=CEST, uf_origem="SP", uf_destino="MG",
            mva_original=Decimal("55.00"), data_inicio_vigencia=date(2026, 1, 1),
        ),
        MatrizMva(
            ncm=NCM, cest=CEST, uf_origem="SP", uf_destino="MG",
            mva_original=Decimal("40.00"), data_inicio_vigencia=date(2023, 1, 1),
            data_fim_vigencia=date(2025, 12, 31),
        ),
    ])
    await sessao.flush()
    loader = MatrizesLoader(sessao)

    em_2026 = (await loader.hidratar([ITEM], OP)).mva.buscar(NCM, CEST, "SP", "MG", DATA)
    op_2024 = Operacao(uf_emit="SP", uf_dest="MG", crt=Crt.NORMAL, data=date(2024, 6, 1))
    em_2024 = (await loader.hidratar([ITEM], op_2024)).mva.buscar(
        NCM, CEST, "SP", "MG", op_2024.data
    )

    assert em_2026.mva_original == Decimal("55.00")
    assert em_2024.mva_original == Decimal("40.00")


async def test_empate_de_data_desempata_pelo_id(sessao):
    """Duas linhas começando no MESMO dia (a UNIQUE das matrizes barra isso, o
    Protocolo não tem UNIQUE): a leitura ainda precisa de uma ordem única —
    a última é sempre a de maior id, nunca "depende do banco"."""
    primeira = MatrizProtocoloSt(
        uf_origem="SP", uf_destino="MG", numero_acordo="Protocolo ICMS 41/2008",
        situacao="ATIVO", data_inicio_vigencia=date(2026, 1, 1),
    )
    segunda = MatrizProtocoloSt(
        uf_origem="SP", uf_destino="MG", numero_acordo="Protocolo ICMS 41/2008",
        situacao="ATIVO", data_inicio_vigencia=date(2026, 1, 1),
    )
    anterior = MatrizProtocoloSt(
        uf_origem="SP", uf_destino="MG", numero_acordo="Protocolo ICMS 41/2008",
        situacao="ATIVO", data_inicio_vigencia=date(2023, 1, 1),
    )
    sessao.add_all([primeira, segunda, anterior])
    await sessao.flush()

    stmt = _desempate_vigencia(select(MatrizProtocoloSt), MatrizProtocoloSt)
    ids = [r.id for r in (await sessao.execute(stmt)).scalars().all()]
    assert ids == [anterior.id, primeira.id, segunda.id]
