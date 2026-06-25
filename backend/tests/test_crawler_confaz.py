"""Testa o parser do CONFAZ (puro, sem rede) e o upsert idempotente (SQLite)."""
from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.crawlers.base import CestRecord
from app.modules.fiscal.crawlers.confaz_cest import ConfazCestExtractor
from app.modules.fiscal.crawlers.upsert import upsert_enquadramento
from app.modules.fiscal.infrastructure.matrizes_models import MatrizEnquadramentoSt


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[MatrizEnquadramentoSt.__table__])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s

# Amostra real-ish (CEST;NCM;DESCRICAO;SEGMENTO), com ruído proposital:
# cabeçalho, máscara, CEST inválido e linha repetida.
_CSV = (
    "CEST;NCM;DESCRICAO;SEGMENTO\n"
    "01.005.00;4011.10.00;Pneus novos;Autopeças\n"
    "0300100;22030000;Cerveja;Bebidas\n"
    "99999;1234;linha-lixo (CEST curto)\n"
    "01.005.00;4011.10.00;Pneus novos;Autopeças\n"   # duplicada
)


def test_parse_confaz_normaliza_e_descarta_lixo():
    regs = ConfazCestExtractor().parse(_CSV.encode("utf-8"))
    # Dedup acontece no upsert; o parser mantém as 3 linhas válidas (lixo fora).
    cests = [r.cest for r in regs]
    assert cests == ["0100500", "0300100", "0100500"]
    assert regs[0] == CestRecord("0100500", "40111000", "Pneus novos", "Autopeças")


@pytest.mark.asyncio
async def test_upsert_enquadramento_idempotente(sessao):
    regs = ConfazCestExtractor().parse(_CSV.encode("utf-8"))
    vig = date(2026, 6, 1)

    r1 = await upsert_enquadramento(sessao, regs, uf="mg", vigencia_inicio=vig)
    assert r1 == {"uf": "MG", "lidos": 3, "inseridos": 2, "atualizados": 0}  # dedup → 2 únicos

    # 2ª rodada: nada novo, tudo atualizado (idempotência).
    r2 = await upsert_enquadramento(sessao, regs, uf="MG", vigencia_inicio=vig)
    assert r2["inseridos"] == 0
    assert r2["atualizados"] == 2

    linhas = (await sessao.execute(
        MatrizEnquadramentoSt.__table__.select().where(MatrizEnquadramentoSt.uf_destino == "MG")
    )).all()
    assert len(linhas) == 2
