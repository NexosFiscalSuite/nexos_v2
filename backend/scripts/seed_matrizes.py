"""Carga inicial (seed) das matrizes fiscais com os NCMs do "Cérebro Tributário"
e dos laboratórios. Vigência aberta a partir de 2024-01-01 (cobre os testes).

`linhas_seed()` devolve instâncias NOVAS a cada chamada (reutilizável por teste e
CLI, sem reaproveitar objetos entre sessões).

Uso (popular um Postgres real):
    ./.venv/Scripts/python.exe scripts/seed_matrizes.py
"""
from __future__ import annotations

import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import func, select  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.modules.fiscal.infrastructure.matrizes_models import (  # noqa: E402
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)

_INICIO = date(2024, 1, 1)   # vigência genérica no passado
_FIM = None                  # aberta


def linhas_seed() -> list:
    """Instâncias novas das matrizes (NCMs do Vault + laboratórios)."""
    mva = [
        # (ncm, cest, uf, mva, ato_legal)
        ("87082919", "0107500", "MG", "71.78", "Autopeça (lab #2)"),
        ("40111000", "0100500", "MG", "42.00", "Pneu (lab #1)"),
        ("40111000", "1600100", "MG", "42.00", "Pneu — CEST segmento 16 (saída)"),
        ("22084000", "0202200", "MG", "50.00", "Cachaça (lab #5)"),
        ("85122011", "0100100", "MG", "40.00", "Iluminação (exemplo Vault)"),
    ]
    enquadramento = [
        # (uf, ncm, cest, regime, segmento)
        ("MG", "87082919", "0107500", "ST", "Autopeças"),
        ("MG", "40111000", "0100500", "ST", "Pneumáticos"),
        ("MG", "40111000", "1600100", "ST", "Pneumáticos (segmento 16)"),
        ("MG", "22084000", "0202200", "ST", "Bebidas alcoólicas"),
        ("MG", "85122011", "0100100", "ST", "Material elétrico"),
    ]
    fcp = [
        # (uf, ncm, fcp_interno, fcp_st, ato_legal)
        ("MG", "22084000", "2.00", "2.00", "FCP bebidas MG (lab #5)"),
    ]
    protocolo = [
        # (uf_origem, uf_destino, acordo) — ativa a ST do REMETENTE na interestadual.
        ("SP", "MG", "Protocolo ICMS 41/2008 (autopeças)"),
    ]
    linhas: list = []
    for ncm, cest, uf, val, ato in mva:
        linhas.append(MatrizMva(
            ncm=ncm, cest=cest, uf_destino=uf, mva_original=Decimal(val),
            ato_legal=ato, data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    for uf, ncm, cest, regime, seg in enquadramento:
        linhas.append(MatrizEnquadramentoSt(
            uf_destino=uf, ncm=ncm, cest=cest, regime=regime, segmento=seg,
            data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    for uf, ncm, interno, st, ato in fcp:
        linhas.append(MatrizFcp(
            uf_destino=uf, ncm=ncm, aliq_fcp_interno=Decimal(interno),
            aliq_fcp_st=Decimal(st), ato_legal=ato,
            data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    for uf_o, uf_d, acordo in protocolo:
        linhas.append(MatrizProtocoloSt(
            uf_origem=uf_o, uf_destino=uf_d, numero_acordo=acordo,
            data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    return linhas


async def aplicar_seed(session: AsyncSession) -> int:
    """Insere o seed se a matriz de MVA estiver vazia (idempotente). Retorna o nº inserido."""
    ja_tem = await session.scalar(select(func.count()).select_from(MatrizMva))
    if ja_tem:
        return 0
    linhas = linhas_seed()
    session.add_all(linhas)
    await session.flush()
    return len(linhas)


async def _main() -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.core.config import get_settings

    engine = create_async_engine(get_settings().database_url)
    async with async_sessionmaker(engine)() as s, s.begin():
        inseridas = await aplicar_seed(s)
    print(f"Seed aplicado: {inseridas} linha(s)." if inseridas else "Matrizes já populadas; nada a fazer.")


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
