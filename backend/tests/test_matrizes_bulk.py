"""Round-trip do módulo Bulk de Matrizes (CSV): export template → import → upsert."""
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.api.matrizes_bulk import MATRIZES
from app.modules.fiscal.infrastructure.matrizes_models import MatrizAliquota, MatrizMva
from app.shared.bulk_csv import exportar_csv, importar_csv

_MVA = MATRIZES["mva"]
_ALIQ = MATRIZES["aliquotas"]

# A MVA depende do par origem→destino: o cabeçalho do template ganhou uf_origem.
_CAB = ("ncm;cest;uf_origem;uf_destino;mva_original;base_legal;"
        "data_inicio_vigencia;data_fim_vigencia")


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
    assert linhas[0] == _CAB


async def test_import_valida_upserta_e_relata_erros(sessao):
    # 1 linha boa, 1 com vírgula decimal (Excel-BR) e 1 inválida (UF faltando).
    conteudo = (
        _CAB.encode() + b"\n"
        b"40111000;0100500;*;MG;42,00;Pneu;2026-01-01;\n"
        b"87082919;0107500;SP;MG;71.78;Autopeca;2026-01-01;\n"
        b"99999999;0000000;*;;10.00;SemUF;2026-01-01;\n"        # UF destino vazia → erro
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
    assert "40111000;0100500;*;MG;42.00" in export


async def test_planilha_antiga_sem_a_coluna_de_origem_continua_importando(sessao):
    """Quem já tem o CSV do formato anterior (só UF de destino) não precisa
    refazer nada: sem a coluna, a linha vale para QUALQUER origem ('*')."""
    antigo = (
        b"ncm;cest;uf_destino;mva_original;base_legal;data_inicio_vigencia;data_fim_vigencia\n"
        b"40111000;0100500;MG;42.00;Pneu;2026-01-01;\n"
    )
    r = await importar_csv(sessao, _MVA, antigo)
    assert r["inseridos"] == 1 and r["erros"] == []

    linha = (await sessao.execute(select(MatrizMva))).scalars().one()
    assert linha.uf_origem == "*"

    # Coluna presente porém em branco → mesmo resultado.
    await importar_csv(sessao, _MVA, _CAB.encode() + b"\n"
                       + b"87082919;0107500;;MG;71.78;Autopeca;2026-01-01;\n")
    origens = (await sessao.execute(select(MatrizMva.uf_origem))).scalars().all()
    assert set(origens) == {"*"}


async def test_uf_por_extenso_na_planilha_vira_sigla(sessao):
    """Planilha do mundo real traz "Minas Gerais"/"sp" — grava MG/SP, senão a
    linha existiria no banco e o motor jamais a encontraria."""
    r = await importar_csv(sessao, _MVA, _CAB.encode() + b"\n"
        + "40111000;0100500;são paulo;Minas Gerais;42.00;Pneu;2026-01-01;\n".encode()
        + b"87082919;0107500;XX;MG;71.78;UF invalida;2026-01-01;\n")     # → erro
    assert r["inseridos"] == 1
    assert len(r["erros"]) == 1 and "UF" in r["erros"][0]["erro"]

    linha = (await sessao.execute(select(MatrizMva))).scalars().one()
    assert (linha.uf_origem, linha.uf_destino) == ("SP", "MG")


async def test_origens_diferentes_convivem_no_mesmo_destino(sessao):
    """A MVA muda conforme o estado remetente: MG←SP e a regra geral MG←* são
    linhas DISTINTAS, não um upsert em cima da outra."""
    r = await importar_csv(sessao, _MVA, _CAB.encode() + b"\n"
        + b"40111000;0100500;*;MG;42.00;Regra geral;2026-01-01;\n"
        + b"40111000;0100500;SP;MG;53.00;Protocolo SP-MG;2026-01-01;\n"
        + b"40111000;0100500;MG;MG;35.00;Interna MG;2026-01-01;\n")
    assert r["inseridos"] == 3 and r["erros"] == []

    por_origem = {
        o: m for o, m in (await sessao.execute(
            select(MatrizMva.uf_origem, MatrizMva.mva_original)
        )).all()
    }
    assert por_origem == {"*": Decimal("42.00"), "SP": Decimal("53.00"),
                          "MG": Decimal("35.00")}


async def test_import_rejeita_vigencia_sobreposta(sessao):
    """ADR-0002: linha cuja vigência sobrepõe outra da mesma chave vira erro
    relatado (linha + motivo) e fica FORA do lote — nunca corrompe a matriz."""
    cab = _CAB.encode() + b"\n"
    r1 = await importar_csv(sessao, _MVA, cab + b"40111000;0100500;*;MG;42.00;Pneu;2024-01-01;\n")
    assert r1["inseridos"] == 1

    # Nova vigência SEM encerrar a antiga (aberta) → sobreposição → rejeitada.
    r2 = await importar_csv(sessao, _MVA, cab + b"40111000;0100500;*;MG;50.00;Pneu;2026-01-01;\n")
    assert r2["inseridos"] == 0
    assert len(r2["erros"]) == 1
    assert "sobrep" in r2["erros"][0]["erro"]

    # MESMA vigência, origem DIFERENTE: chave distinta, entra sem conflito.
    r_sp = await importar_csv(sessao, _MVA, cab + b"40111000;0100500;SP;MG;50.00;Pneu SP;2026-01-01;\n")
    assert r_sp["inseridos"] == 1 and r_sp["erros"] == []

    # Fluxo correto NO MESMO arquivo: encerra a antiga e insere a nova.
    r3 = await importar_csv(sessao, _MVA, cab
        + b"40111000;0100500;*;MG;42.00;Pneu;2024-01-01;2025-12-31\n"
        + b"40111000;0100500;*;MG;50.00;Pneu 2026;2026-01-01;\n")
    assert r3["atualizados"] == 1
    assert r3["inseridos"] == 1
    assert r3["erros"] == []


# ── Alíquotas: a do estado ("GERAL") × a do produto (por NCM) ────────────────
_CAB_ALIQ = ("uf_destino;ncm;aliq_modal;aliq_fcp_integrado;p_red_bc_st;"
             "base_legal;data_inicio_vigencia;data_fim_vigencia")


@pytest_asyncio.fixture
async def sessao_aliq():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[MatrizAliquota.__table__])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


async def _aliquotas(sessao):
    """{ncm: (modal, redução)} — o retrato da matriz depois do import."""
    return {
        n: (m, p) for n, m, p in (await sessao.execute(select(
            MatrizAliquota.ncm, MatrizAliquota.aliq_modal, MatrizAliquota.p_red_bc_st
        ))).all()
    }


async def test_template_de_aliquotas_traz_ncm_e_reducao(sessao_aliq):
    csv = await exportar_csv(sessao_aliq, _ALIQ)
    assert csv.strip().splitlines() == [_CAB_ALIQ]


async def test_aliquota_do_estado_e_do_produto_convivem(sessao_aliq):
    """Remédio a 12% em MG não anula os 18% do estado: são duas linhas, mesma
    UF e mesma vigência. Sem o NCM na chave, uma sobrescreveria a outra."""
    r = await importar_csv(sessao_aliq, _ALIQ, _CAB_ALIQ.encode() + b"\n"
        + b"MG;GERAL;18.00;0;0;RICMS/MG art. 42;2026-01-01;\n"
        + b"MG;30049099;12.00;0;0;Medicamento;2026-01-01;\n"
        + b"MG;1006.30.21;12,00;0;0;Arroz (cesta basica);2026-01-01;\n")
    assert r["inseridos"] == 3 and r["erros"] == []

    # NCM formatado virou dígitos e a vírgula decimal virou ponto.
    assert await _aliquotas(sessao_aliq) == {
        "GERAL": (Decimal("18.00"), Decimal("0.00")),
        "30049099": (Decimal("12.00"), Decimal("0.00")),
        "10063021": (Decimal("12.00"), Decimal("0.00")),
    }


async def test_import_por_ncm_nao_sobrescreve_a_linha_do_estado(sessao_aliq):
    """O risco da chave de upsert: subir a planilha só com o NCM específico não
    pode mexer na alíquota GERAL — senão TODA a UF passaria a calcular com a
    alíquota do medicamento."""
    await importar_csv(sessao_aliq, _ALIQ, _CAB_ALIQ.encode() + b"\n"
                       + b"MG;GERAL;18.00;0;0;RICMS/MG;2026-01-01;\n")

    r = await importar_csv(sessao_aliq, _ALIQ, _CAB_ALIQ.encode() + b"\n"
                           + b"MG;30049099;12.00;0;33.33;Medicamento;2026-01-01;\n")
    assert r["inseridos"] == 1 and r["atualizados"] == 0 and r["erros"] == []

    assert await _aliquotas(sessao_aliq) == {
        "GERAL": (Decimal("18.00"), Decimal("0.00")),        # intocada
        "30049099": (Decimal("12.00"), Decimal("33.33")),
    }

    # Reimportar o MESMO NCM atualiza a linha dele — e só ela.
    r2 = await importar_csv(sessao_aliq, _ALIQ, _CAB_ALIQ.encode() + b"\n"
                            + b"MG;30049099;12.00;0;30.00;Medicamento (rev.);2026-01-01;\n")
    assert r2["inseridos"] == 0 and r2["atualizados"] == 1
    assert (await _aliquotas(sessao_aliq))["GERAL"] == (Decimal("18.00"), Decimal("0.00"))


async def test_planilha_antiga_sem_a_coluna_ncm_entra_como_geral(sessao_aliq):
    """Quem já exportou a matriz no formato anterior (só UF) sobe o arquivo do
    mesmo jeito: a linha vira a alíquota do estado."""
    antigo = (b"uf_destino;aliq_modal;aliq_fcp_integrado;base_legal;"
              b"data_inicio_vigencia;data_fim_vigencia\n"
              b"MG;18.00;0;RICMS/MG;2026-01-01;\n"
              b"SP;18.00;0;RICMS/SP;2026-01-01;\n")
    r = await importar_csv(sessao_aliq, _ALIQ, antigo)
    assert r["inseridos"] == 2 and r["erros"] == []

    linhas = (await sessao_aliq.execute(select(MatrizAliquota))).scalars().all()
    assert {x.ncm for x in linhas} == {"GERAL"}
    assert {x.p_red_bc_st for x in linhas} == {Decimal("0.00")}

    # Coluna presente porém em branco → mesmo resultado (nada de NCM vazio).
    await importar_csv(sessao_aliq, _ALIQ, _CAB_ALIQ.encode() + b"\n"
                       + b"RJ;;20.00;2.00;;FECP;2026-01-01;\n")
    ncms = (await sessao_aliq.execute(select(MatrizAliquota.ncm))).scalars().all()
    assert set(ncms) == {"GERAL"}


async def test_duas_vigencias_do_mesmo_ncm_acusam_conflito(sessao_aliq):
    """ADR-0002 continua valendo DENTRO do NCM: mudou a alíquota do produto,
    encerre a vigência antiga antes de abrir a nova."""
    cab = _CAB_ALIQ.encode() + b"\n"
    r1 = await importar_csv(sessao_aliq, _ALIQ, cab
                            + b"MG;30049099;12.00;0;0;Medicamento;2024-01-01;\n")
    assert r1["inseridos"] == 1

    r2 = await importar_csv(sessao_aliq, _ALIQ, cab
                            + b"MG;30049099;18.00;0;0;Medicamento;2026-01-01;\n")
    assert r2["inseridos"] == 0
    assert len(r2["erros"]) == 1 and "sobrep" in r2["erros"][0]["erro"]

    # A linha do ESTADO na mesma UF e data não é conflito: outra família.
    r3 = await importar_csv(sessao_aliq, _ALIQ, cab
                            + b"MG;GERAL;18.00;0;0;RICMS/MG;2026-01-01;\n")
    assert r3["inseridos"] == 1 and r3["erros"] == []


async def test_reducao_de_base_no_geral_e_recusada(sessao_aliq):
    """Redução de base é de um produto. Aceitá-la no GERAL derrubaria a base do
    ST do estado inteiro em silêncio — a linha vira erro relatado e fica fora."""
    r = await importar_csv(sessao_aliq, _ALIQ, _CAB_ALIQ.encode() + b"\n"
        + b"MG;GERAL;18.00;0;38.89;Reducao indevida;2026-01-01;\n"
        + b"MG;;18.00;0;38.89;Reducao indevida (ncm vazio);2026-01-01;\n"
        + b"MG;22030000;18.00;0;38.89;Cerveja (reducao legitima);2026-01-01;\n")
    assert r["inseridos"] == 1
    assert len(r["erros"]) == 2
    assert all("informe o NCM" in e["erro"] for e in r["erros"])

    assert await _aliquotas(sessao_aliq) == {"22030000": (Decimal("18.00"), Decimal("38.89"))}
