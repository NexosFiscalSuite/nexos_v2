"""Prova viva do ADR-0002: a mesma chave (NCM+CEST+UF) devolve taxas diferentes
conforme a DATA da operação, e a busca respeita o fallback de NCM (8→6→4).

Usa SQLite em memória (sync) — exercita o filtro de vigência e a ordenação reais
sem depender de Postgres. Os loaders async + RLS entram na integração (Fase 3).
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.database import Base
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia


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
            ato_legal="RICMS/MG (até 2025)",
        ),
        MatrizMva(
            ncm="22030000", cest="0300100", uf_destino="MG", mva_original=Decimal("55.00"),
            data_inicio_vigencia=date(2026, 1, 1), data_fim_vigencia=None,
            ato_legal="RICMS/MG (a partir de 2026)",
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
