"""Radar de saúde das matrizes (Fase 2): frescor calculado SÓ sobre as linhas
vigentes — regra encerrada não envelhece ninguém — e propostas pendentes no
resumo geral."""
from datetime import date, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.matrizes_saude import saude_matrizes
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.propostas_models import MatrizProposta


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[
            MatrizMva.__table__, MatrizEnquadramentoSt.__table__,
            MatrizProtocoloSt.__table__, MatrizAliquota.__table__,
            MatrizFcp.__table__, MatrizProposta.__table__,
        ])
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


@pytest.mark.asyncio
async def test_frescor_por_matriz_e_resumo_geral(sessao):
    sessao.add_all([
        # Enquadramento vigente, verificado AGORA (default do cadastro) → 100%.
        MatrizEnquadramentoSt(
            uf_destino="MG", ncm="40111000", cest="0100500", regime="ST",
            data_inicio_vigencia=date(2026, 6, 1),
        ),
        # MVA vigente com verificação VELHA (jan/2025) → 0% na janela de 90d.
        MatrizMva(
            ncm="40111000", cest="0100500", uf_destino="MG",
            mva_original=Decimal("40.00"), data_inicio_vigencia=date(2026, 6, 1),
            ultima_verificacao_em=datetime(2025, 1, 1),
        ),
        # Alíquota ENCERRADA: fora do radar (não conta como vigente).
        MatrizAliquota(
            uf_destino="MG", aliq_modal=Decimal("18.00"),
            data_inicio_vigencia=date(2020, 1, 1), data_fim_vigencia=date(2021, 1, 1),
            ultima_verificacao_em=datetime(2020, 6, 1),
        ),
    ])
    sessao.add(MatrizProposta(
        tipo_matriz="enquadramento", acao="INSERIR", chave_resumo="MG · NCM x",
        payload={}, fonte="teste", hash_proposta="h1",
    ))
    await sessao.flush()

    s = await saude_matrizes(sessao)
    por = {m["tipo"]: m for m in s["matrizes"]}

    assert por["enquadramento"]["vigentes"] == 1
    assert por["enquadramento"]["pct_90d"] == 100
    assert por["mva"]["pct_90d"] == 0
    assert por["mva"]["verificacao_mais_antiga"].startswith("2025-01-01")
    assert por["aliquotas"]["vigentes"] == 0 and por["aliquotas"]["pct_90d"] is None

    geral = s["geral"]
    assert geral["vigentes"] == 2
    assert geral["pct_verificado_90d"] == 50       # 1 fresca de 2 vigentes
    assert geral["propostas_pendentes"] == 1
    assert geral["ultima_atualizacao"] is not None

    # Base toda com sigla canônica: o radar de UF não acusa ninguém.
    assert s["ufs_invalidas"]["total"] == 0
    assert s["ufs_invalidas"]["amostra"] == []
    assert all(m["ufs_invalidas"] == 0 for m in s["matrizes"])


@pytest.mark.asyncio
async def test_uf_fora_do_padrao_e_sugestao_de_correcao(sessao):
    """Linha antiga com UF em texto livre é INVISÍVEL para o motor (a busca
    compara com a sigla de 2 letras do XML). O radar tem de achá-la e, quando
    dá para resolver sozinho, sugerir a sigla.

    No Postgres as colunas são VARCHAR(2), então o legado real é caixa errada
    ("mg") e sigla inexistente ("XX"); o nome por extenso está aqui como
    defesa (outro backend, coluna alargada, carga fora do ORM) — a sugestão
    sai igual porque quem resolve é o `normalizar_uf`.
    """
    sessao.add_all([
        MatrizEnquadramentoSt(          # nome por extenso → sugere MG
            uf_destino="Minas Gerais", ncm="40111000", cest="0100500", regime="ST",
            data_inicio_vigencia=date(2026, 6, 1),
        ),
        MatrizFcp(                      # minúscula → sugere SP
            uf_destino="sp", ncm="GERAL", aliq_fcp_st=Decimal("2.00"),
            data_inicio_vigencia=date(2026, 6, 1),
        ),
        MatrizProtocoloSt(              # lixo → sem sugestão possível
            uf_origem="XX", uf_destino="MG", numero_acordo="Protocolo ICMS 41/2008",
            situacao="ATIVO", data_inicio_vigencia=date(2026, 6, 1),
        ),
        MatrizMva(                      # os DOIS campos tortos na MESMA linha
            ncm="40111000", cest="0100500", uf_origem="rj", uf_destino="mg",
            mva_original=Decimal("40.00"), data_inicio_vigencia=date(2026, 6, 1),
        ),
    ])
    await sessao.flush()

    ufs = (await saude_matrizes(sessao))["ufs_invalidas"]

    # Contagem é de LINHAS (a MVA torta dos dois lados conta uma vez).
    assert ufs["por_matriz"] == {
        "enquadramento": 1, "mva": 1, "protocolos": 1, "aliquotas": 0, "fcp": 1,
    }
    assert ufs["total"] == 4

    por_chave = {(i["matriz"], i["campo"]): i for i in ufs["amostra"]}
    assert por_chave[("enquadramento", "uf_destino")]["valor"] == "Minas Gerais"
    assert por_chave[("enquadramento", "uf_destino")]["sugestao"] == "MG"
    assert por_chave[("fcp", "uf_destino")]["sugestao"] == "SP"
    assert por_chave[("protocolos", "uf_origem")]["sugestao"] is None
    # A amostra é por CAMPO: a linha de MVA aparece duas vezes, com o mesmo id.
    assert por_chave[("mva", "uf_origem")]["sugestao"] == "RJ"
    assert por_chave[("mva", "uf_destino")]["sugestao"] == "MG"
    assert (por_chave[("mva", "uf_origem")]["id"]
            == por_chave[("mva", "uf_destino")]["id"])


@pytest.mark.asyncio
async def test_curinga_da_mva_e_ncm_geral_nao_sao_acusados(sessao):
    """Falso positivo aqui destrói a confiança no radar: `uf_origem = "*"` é a
    regra legítima de "qualquer origem" e `ncm = 'GERAL'` (FCP/Alíquota) nem UF
    é — nenhum dos dois pode virar acusação. Já o "*" na ORIGEM do protocolo é
    inválido: lá a busca compara a origem por igualdade."""
    sessao.add_all([
        MatrizMva(
            ncm="40111000", cest="0100500", uf_origem="*", uf_destino="MG",
            mva_original=Decimal("40.00"), data_inicio_vigencia=date(2026, 6, 1),
        ),
        MatrizFcp(
            uf_destino="MG", ncm="GERAL", aliq_fcp_st=Decimal("2.00"),
            data_inicio_vigencia=date(2026, 6, 1),
        ),
        MatrizAliquota(
            uf_destino="MG", ncm="GERAL", aliq_modal=Decimal("18.00"),
            data_inicio_vigencia=date(2026, 6, 1),
        ),
        MatrizProtocoloSt(
            uf_origem="*", uf_destino="MG", numero_acordo="Protocolo ICMS 41/2008",
            situacao="ATIVO", data_inicio_vigencia=date(2026, 6, 1),
        ),
    ])
    await sessao.flush()

    ufs = (await saude_matrizes(sessao))["ufs_invalidas"]

    assert ufs["por_matriz"]["mva"] == 0
    assert ufs["por_matriz"]["fcp"] == 0
    assert ufs["por_matriz"]["aliquotas"] == 0
    assert ufs["por_matriz"]["protocolos"] == 1
    assert [i["campo"] for i in ufs["amostra"]] == ["uf_origem"]


@pytest.mark.asyncio
async def test_linha_encerrada_com_uf_torta_fica_fora_do_radar(sessao):
    """Regra encerrada não é aplicada por ninguém — acusá-la só faria barulho."""
    sessao.add(MatrizEnquadramentoSt(
        uf_destino="Minas Gerais", ncm="40111000", cest="0100500", regime="ST",
        data_inicio_vigencia=date(2020, 1, 1), data_fim_vigencia=date(2021, 1, 1),
    ))
    await sessao.flush()

    ufs = (await saude_matrizes(sessao))["ufs_invalidas"]
    assert ufs["total"] == 0 and ufs["amostra"] == []
