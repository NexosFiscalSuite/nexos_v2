"""Round-trip do módulo Bulk de Matrizes (CSV): export template → import → upsert."""
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.api.matrizes_bulk import MATRIZES
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.shared.bulk_csv import exportar_csv, importar_csv

_MVA = MATRIZES["mva"]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[MatrizMva.__table__])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s


async def test_export_vazia_devolve_so_o_cabecalho_template(sessao):
    csv = await exportar_csv(sessao, _MVA)
    linhas = csv.strip().splitlines()
    assert len(linhas) == 1
    assert linhas[0] == "ncm;cest;uf_destino;mva_original;ato_legal;data_inicio_vigencia;data_fim_vigencia"


async def test_import_valida_upserta_e_relata_erros(sessao):
    # 1 linha boa, 1 com vírgula decimal (Excel-BR) e 1 inválida (UF faltando).
    conteudo = (
        b"ncm;cest;uf_destino;mva_original;ato_legal;data_inicio_vigencia;data_fim_vigencia\n"
        b"40111000;0100500;MG;42,00;Pneu;2026-01-01;\n"
        b"87082919;0107500;MG;71.78;Autopeca;2026-01-01;\n"
        b"99999999;0000000;;10.00;SemUF;2026-01-01;\n"          # UF vazia → erro
    )

    r = await importar_csv(sessao, _MVA, conteudo)
    assert r["inseridos"] == 2
    assert r["atualizados"] == 0
    assert len(r["erros"]) == 1
    assert r["erros"][0]["linha"] == 4                          # 3ª linha de dados

    # Idempotência: reimportar as mesmas válidas só atualiza.
    r2 = await importar_csv(sessao, _MVA, conteudo)
    assert r2["inseridos"] == 0
    assert r2["atualizados"] == 2

    # E a vírgula virou ponto (42,00 → 42.00) na persistência.
    export = await exportar_csv(sessao, _MVA)
    assert "40111000;0100500;MG;42.00" in export
