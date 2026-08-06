"""Duas armadilhas da MVA por UF de origem, ambas silenciosas.

1. `chave_resumo` das propostas de MVA passou a começar pela ORIGEM
   ("SP → MG · NCM …") quando a matriz ganhou UF de origem. O filtro por UF do
   `aprovar_lote` casava só o prefixo, então um "aprovar tudo de MG" deixava de
   fora TODA proposta com origem — sem erro, sem aviso.
2. O snapshot do motor montava a chave com o NCM/CEST CRUS do banco, enquanto a
   busca procura por dígitos limpos. Linha gravada como "8544.49.00" existiria,
   apareceria certa na tela e nunca seria encontrada — cadastro que parece feito
   e não vale nada.
"""
from datetime import date
from decimal import Decimal

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.fiscal.application.propostas_service import PropostasService
from app.modules.fiscal.infrastructure.matrizes_loaders import montar_mva_snapshot
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.modules.fiscal.infrastructure.propostas_models import (
    ACAO_INSERIR,
    STATUS_APROVADA,
    MatrizProposta,
)

_INICIO = date(2026, 1, 1)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(
            Base.metadata.create_all,
            tables=[MatrizMva.__table__, MatrizProposta.__table__],
        )
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _proposta(chave: str, *, ncm="85444900", uf_origem="SP") -> MatrizProposta:
    return MatrizProposta(
        tipo_matriz="mva", acao=ACAO_INSERIR, chave_resumo=chave,
        payload={
            "ncm": ncm, "cest": "1200700", "uf_origem": uf_origem,
            "uf_destino": "MG", "mva_original": "42.00",
            "data_inicio_vigencia": _INICIO.isoformat(), "data_fim_vigencia": None,
            "base_legal": "RICMS/MG Anexo VII",
        },
        fonte="sefaz-mg-anexo-vii", hash_proposta=chave,
    )


async def test_aprovar_lote_por_uf_alcanca_proposta_com_origem(sessao):
    """O 'aprovar tudo de MG' tem que pegar as duas formas de chave_resumo."""
    sessao.add_all([
        _proposta("SP → MG · NCM 85444900 · CEST 1200700"),          # formato novo
        _proposta("MG · NCM 84248219 · CEST 0102900", ncm="84248219",
                  uf_origem="*"),                                     # formato antigo
        _proposta("SP → RJ · NCM 85444900 · CEST 1200700"),          # outro destino
    ])
    await sessao.flush()

    r = await PropostasService(sessao).aprovar_lote(revisor="teste", tipo="mva", uf="MG")

    assert r["aprovadas"] == 2, "a proposta com origem no prefixo ficava de fora"
    assert r["falhas"] == []
    # A de outro destino continua pendente — o filtro não virou peneira furada.
    restantes = (await sessao.scalars(
        select(MatrizProposta).where(MatrizProposta.status != STATUS_APROVADA)
    )).all()
    assert [p.chave_resumo for p in restantes] == [
        "SP → RJ · NCM 85444900 · CEST 1200700"
    ]


def test_snapshot_normaliza_a_chave_vinda_do_banco():
    """Linha gravada com pontuação tem de ser encontrada pela busca limpa."""
    class _Linha:
        id = 1
        ncm = "8544.49.00"
        cest = "12.007.00"
        uf_origem = "sp"
        uf_destino = "mg"
        mva_original = Decimal("42.00")
        base_legal = "RICMS/MG Anexo VII"

    snap = montar_mva_snapshot([_Linha()])
    achado = snap.buscar("85444900", "1200700", "SP", "MG", date(2026, 6, 15))

    assert achado is not None, "linha existe no banco e o motor não a enxergava"
    assert achado.mva_original == Decimal("42.00")
    assert achado.uf_origem_casada == "SP"


def test_snapshot_continua_achando_o_que_ja_estava_limpo():
    """Não-regressão: o caminho normal (dados já normalizados) não muda."""
    class _Linha:
        id = 2
        ncm = "85444900"
        cest = "1200700"
        uf_origem = "*"
        uf_destino = "MG"
        mva_original = Decimal("35.00")
        base_legal = None

    snap = montar_mva_snapshot([_Linha()])
    achado = snap.buscar("85444900", "1200700", "RJ", "MG", date(2026, 6, 15))

    assert achado is not None
    assert achado.uf_origem_casada == "*"
