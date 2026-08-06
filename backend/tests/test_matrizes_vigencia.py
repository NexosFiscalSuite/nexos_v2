"""Prova viva do ADR-0002: a mesma chave (NCM+CEST+UF) devolve taxas diferentes
conforme a DATA da operação, e a busca respeita o fallback de NCM (8→6→4).

Usa SQLite em memória (sync) — exercita o filtro de vigência e a ordenação reais
sem depender de Postgres. Os loaders async + RLS entram na integração (Fase 3).
"""
from datetime import date
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.database import Base
from app.modules.fiscal.domain.st import Crt, Operacao
from app.modules.fiscal.infrastructure.matrizes_loaders import MatrizesLoader
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.vigencia import (
    filtrar_vigencia,
    sobreposicao_existente,
)


@pytest.fixture
def sessao():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[MatrizMva.__table__])
    with Session(engine) as s:
        yield s


def _mva_vigente(s: Session, ncm: str, cest: str, uf: str, data: date) -> MatrizMva | None:
    """Reproduz a busca do MvaRepository: fallback 8→6→4 + vigência na data."""
    stmt = filtrar_vigencia(
        select(MatrizMva).where(
            MatrizMva.uf_destino == uf,
            MatrizMva.cest == cest,
            MatrizMva.ncm.in_([ncm, ncm[:6], ncm[:4]]),
        ),
        MatrizMva,
        data,
    ).order_by(func.length(MatrizMva.ncm).desc(), MatrizMva.data_inicio_vigencia.desc()).limit(1)
    return s.execute(stmt).scalar_one_or_none()


def test_mesma_chave_taxas_diferentes_por_data(sessao):
    """O coração do ADR-0002: cerveja MG com MVA 40% até 2025 e 55% a partir de 2026."""
    sessao.add_all([
        MatrizMva(
            ncm="22030000", cest="0300100", uf_destino="MG", mva_original=Decimal("40.00"),
            data_inicio_vigencia=date(2023, 1, 1), data_fim_vigencia=date(2025, 12, 31),
            base_legal="RICMS/MG (até 2025)",
        ),
        MatrizMva(
            ncm="22030000", cest="0300100", uf_destino="MG", mva_original=Decimal("55.00"),
            data_inicio_vigencia=date(2026, 1, 1), data_fim_vigencia=None,
            base_legal="RICMS/MG (a partir de 2026)",
        ),
    ])
    sessao.commit()

    r_2025 = _mva_vigente(sessao, "22030000", "0300100", "MG", date(2025, 6, 1))
    r_2026 = _mva_vigente(sessao, "22030000", "0300100", "MG", date(2026, 6, 1))

    assert r_2025.mva_original == Decimal("40.00")
    assert r_2026.mva_original == Decimal("55.00")
    assert r_2025.mva_original != r_2026.mva_original   # a vigência fez efeito


def test_fora_de_qualquer_vigencia_retorna_nada(sessao):
    sessao.add(MatrizMva(
        ncm="22030000", cest="0300100", uf_destino="MG", mva_original=Decimal("40.00"),
        data_inicio_vigencia=date(2023, 1, 1), data_fim_vigencia=date(2025, 12, 31),
    ))
    sessao.commit()
    # Nota de 2022: nenhuma regra vigente ainda.
    assert _mva_vigente(sessao, "22030000", "0300100", "MG", date(2022, 1, 1)) is None


def test_fallback_ncm_8_6_4(sessao):
    """Regra geral por 4 dígitos + específica por 8; a busca pega a mais específica."""
    sessao.add_all([
        MatrizMva(
            ncm="8512", cest="0100100", uf_destino="MG", mva_original=Decimal("30.00"),
            data_inicio_vigencia=date(2024, 1, 1),
        ),
        MatrizMva(
            ncm="85122011", cest="0100100", uf_destino="MG", mva_original=Decimal("42.00"),
            data_inicio_vigencia=date(2024, 1, 1),
        ),
    ])
    sessao.commit()

    # NCM cheio com regra específica -> pega os 8 dígitos (42%).
    especifico = _mva_vigente(sessao, "85122011", "0100100", "MG", date(2025, 1, 1))
    assert especifico.mva_original == Decimal("42.00")

    # NCM sem específica -> cai na regra geral de 4 dígitos (30%).
    geral = _mva_vigente(sessao, "85129999", "0100100", "MG", date(2025, 1, 1))
    assert geral.mva_original == Decimal("30.00")


# ── Loader async: alíquota modal com vigência (caminho de produção) ──────────
@pytest_asyncio.fixture
async def sessao_async():
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


async def test_loader_aliquota_respeita_vigencia(sessao_async):
    """O snapshot hidratado devolve a alíquota VIGENTE NA DATA da operação —
    AL 19% em março/2026 e 20,5% em maio/2026 — e rastreia a linha usada."""
    sessao_async.add_all([
        MatrizAliquota(
            uf_destino="AL", aliq_modal=Decimal("19.00"), aliq_fcp_integrado=Decimal("1.00"),
            data_inicio_vigencia=date(2024, 1, 1), data_fim_vigencia=date(2026, 3, 31),
        ),
        MatrizAliquota(
            uf_destino="AL", aliq_modal=Decimal("20.50"), aliq_fcp_integrado=Decimal("1.00"),
            data_inicio_vigencia=date(2026, 4, 1), data_fim_vigencia=None,
        ),
    ])
    await sessao_async.flush()

    loader = MatrizesLoader(sessao_async)
    op_antes = Operacao(uf_emit="SP", uf_dest="AL", crt=Crt.NORMAL, data=date(2026, 3, 1))
    op_depois = Operacao(uf_emit="SP", uf_dest="AL", crt=Crt.NORMAL, data=date(2026, 5, 1))

    antes = (await loader.hidratar([], op_antes)).aliquota.buscar(
        "85122011", "AL", op_antes.data
    )
    depois = (await loader.hidratar([], op_depois)).aliquota.buscar(
        "85122011", "AL", op_depois.data
    )

    assert antes.modal == Decimal("19.00")
    assert antes.efetiva == Decimal("20.00")            # modal + FCP integrado
    assert depois.modal == Decimal("20.50")
    assert antes.matriz_id != depois.matriz_id          # linhas distintas rastreadas

    # UF sem linha vigente: snapshot vazio → motor classifica como não auditável.
    op_2022 = Operacao(uf_emit="SP", uf_dest="AL", crt=Crt.NORMAL, data=date(2022, 1, 1))
    assert (await loader.hidratar([], op_2022)).aliquota.buscar(
        "85122011", "AL", op_2022.data
    ) is None


async def test_sobreposicao_de_vigencia_e_erro_de_carga(sessao_async):
    """ADR-0002 (regra 4): duas linhas vigentes na mesma data para a mesma chave
    é erro de carga — mudança de taxa = encerrar a antiga e inserir uma nova."""
    linha = MatrizAliquota(
        uf_destino="MG", aliq_modal=Decimal("18.00"),
        aliq_fcp_integrado=Decimal("0"), data_inicio_vigencia=date(2024, 1, 1),
    )
    sessao_async.add(linha)
    await sessao_async.flush()

    # A chave de identidade da alíquota inclui o NCM ('GERAL' = regra do estado):
    # duas linhas só conflitam se forem do MESMO produto na mesma UF.
    nova = {"uf_destino": "MG", "ncm": "GERAL", "data_inicio_vigencia": date(2026, 1, 1),
            "data_fim_vigencia": None}

    # Vigência aberta existente × nova aberta a partir de 2026 → conflito.
    conflito = await sobreposicao_existente(sessao_async, MatrizAliquota, nova)
    assert conflito is not None and conflito.id == linha.id

    # UF diferente nunca conflita (chave de identidade distinta).
    assert await sobreposicao_existente(
        sessao_async, MatrizAliquota, {**nova, "uf_destino": "SP"}
    ) is None

    # Nem NCM diferente: a alíquota própria do produto (cesta básica a 12% num
    # estado de 18%) convive com a regra geral do estado na mesma vigência.
    assert await sobreposicao_existente(
        sessao_async, MatrizAliquota, {**nova, "ncm": "19053100"}
    ) is None

    # Fluxo correto: encerra a antiga → a nova passa a ser válida.
    linha.data_fim_vigencia = date(2025, 12, 31)
    await sessao_async.flush()
    assert await sobreposicao_existente(sessao_async, MatrizAliquota, nova) is None

    # Editar a própria linha não conflita consigo mesma (excluir_id).
    assert await sobreposicao_existente(
        sessao_async, MatrizAliquota,
        {"uf_destino": "MG", "ncm": "GERAL", "data_inicio_vigencia": date(2024, 1, 1),
         "data_fim_vigencia": date(2025, 12, 31)},
        excluir_id=linha.id,
    ) is None


async def test_mva_da_mesma_data_convive_com_origens_diferentes(sessao_async):
    """A MVA varia com o estado REMETENTE: o mesmo pneu entrando em MG tem uma
    MVA vindo de SP e outra pela regra geral. Como uf_origem faz parte da chave
    de identidade, as duas linhas valem ao mesmo tempo — não é erro de carga."""
    geral = MatrizMva(
        ncm="40111000", cest="0100500", uf_origem="*", uf_destino="MG",
        mva_original=Decimal("42.00"), data_inicio_vigencia=date(2026, 1, 1),
    )
    sessao_async.add(geral)
    await sessao_async.flush()

    base = {"ncm": "40111000", "cest": "0100500", "uf_destino": "MG",
            "data_inicio_vigencia": date(2026, 1, 1), "data_fim_vigencia": None}

    # Origem específica × regra geral: chaves distintas, sem conflito.
    assert await sobreposicao_existente(
        sessao_async, MatrizMva, {**base, "uf_origem": "SP"}
    ) is None
    # A origem interna (MG→MG) também é uma regra à parte.
    assert await sobreposicao_existente(
        sessao_async, MatrizMva, {**base, "uf_origem": "MG"}
    ) is None

    # MESMA origem com vigência sobreposta continua sendo erro de carga.
    conflito = await sobreposicao_existente(
        sessao_async, MatrizMva, {**base, "uf_origem": "*"}
    )
    assert conflito is not None and conflito.id == geral.id

    # E, gravada a de SP, ela passa a conflitar consigo mesma (mas não com a geral).
    sessao_async.add(MatrizMva(
        ncm="40111000", cest="0100500", uf_origem="SP", uf_destino="MG",
        mva_original=Decimal("53.00"), data_inicio_vigencia=date(2026, 1, 1),
    ))
    await sessao_async.flush()
    conflito_sp = await sobreposicao_existente(
        sessao_async, MatrizMva, {**base, "uf_origem": "SP"}
    )
    assert conflito_sp is not None and conflito_sp.uf_origem == "SP"
