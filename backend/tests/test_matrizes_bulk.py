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
    assert linhas[0] == "ncm;cest;uf_destino;mva_original;base_legal;data_inicio_vigencia;data_fim_vigencia"


async def test_import_valida_upserta_e_relata_erros(sessao):
    # 1 linha boa, 1 com vírgula decimal (Excel-BR) e 1 inválida (UF faltando).
    conteudo = (
        b"ncm;cest;uf_destino;mva_original;base_legal;data_inicio_vigencia;data_fim_vigencia\n"
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


async def test_import_rejeita_vigencia_sobreposta(sessao):
    """ADR-0002: linha cuja vigência sobrepõe outra da mesma chave vira erro
    relatado (linha + motivo) e fica FORA do lote — nunca corrompe a matriz."""
    cab = b"ncm;cest;uf_destino;mva_original;base_legal;data_inicio_vigencia;data_fim_vigencia\n"
    r1 = await importar_csv(sessao, _MVA, cab + b"40111000;0100500;MG;42.00;Pneu;2024-01-01;\n")
    assert r1["inseridos"] == 1

    # Nova vigência SEM encerrar a antiga (aberta) → sobreposição → rejeitada.
    r2 = await importar_csv(sessao, _MVA, cab + b"40111000;0100500;MG;50.00;Pneu;2026-01-01;\n")
    assert r2["inseridos"] == 0
    assert len(r2["erros"]) == 1
    assert "sobrep" in r2["erros"][0]["erro"]

    # Fluxo correto NO MESMO arquivo: encerra a antiga e insere a nova.
    r3 = await importar_csv(sessao, _MVA, cab
        + b"40111000;0100500;MG;42.00;Pneu;2024-01-01;2025-12-31\n"
        + b"40111000;0100500;MG;50.00;Pneu 2026;2026-01-01;\n")
    assert r3["atualizados"] == 1
    assert r3["inseridos"] == 1
    assert r3["erros"] == []
