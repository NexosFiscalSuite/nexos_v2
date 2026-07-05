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
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)

_INICIO = date(2024, 1, 1)   # vigência genérica no passado
_FIM = None                  # aberta

# Alíquotas modais + FCP integrado por UF — valores conferidos em 12/06/2026.
# ⚠️ O histórico ANTERIOR a _INICIO não foi curado: para auditar notas mais
# antigas, encerre a linha baseline e insira a vigência correta (via CRUD/CSV).
_ALIQUOTAS_BASELINE: dict[str, tuple[str, str]] = {
    "AC": ("19", "0"), "AM": ("20", "0"), "AP": ("18", "0"),
    "BA": ("20.5", "0"), "CE": ("20", "0"), "DF": ("20", "0"), "ES": ("17", "0"),
    "GO": ("19", "0"), "MA": ("23", "0"), "MG": ("18", "0"), "MS": ("17", "0"),
    "MT": ("17", "0"), "PA": ("19", "0"), "PB": ("20", "0"), "PE": ("20.5", "0"),
    "PI": ("22.5", "0"), "PR": ("19.5", "0"), "RJ": ("20", "2"), "RN": ("20", "0"),
    "RO": ("19.5", "0"), "RR": ("20", "0"), "RS": ("17", "0"), "SC": ("17", "0"),
    "SE": ("19", "1"), "SP": ("18", "0"), "TO": ("20", "0"),
}


def linhas_aliquotas() -> list:
    """Alíquotas das 27 UFs. AL tem dupla vigência (Lei 9.776/2025):
    19% até 31/03/2026 e 20,5% a partir de 01/04/2026 — a prova viva do ADR-0002."""
    linhas = [
        MatrizAliquota(
            uf_destino=uf, aliq_modal=Decimal(modal), aliq_fcp_integrado=Decimal(fcp),
            base_legal="Baseline 12/06/2026",
            data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        )
        for uf, (modal, fcp) in sorted(_ALIQUOTAS_BASELINE.items())
    ]
    linhas.append(MatrizAliquota(
        uf_destino="AL", aliq_modal=Decimal("19"), aliq_fcp_integrado=Decimal("1"),
        base_legal="Modal AL até 31/03/2026",
        data_inicio_vigencia=_INICIO, data_fim_vigencia=date(2026, 3, 31),
    ))
    linhas.append(MatrizAliquota(
        uf_destino="AL", aliq_modal=Decimal("20.5"), aliq_fcp_integrado=Decimal("1"),
        base_legal="Lei 9.776/2025 (AL)",
        data_inicio_vigencia=date(2026, 4, 1), data_fim_vigencia=_FIM,
    ))
    return linhas


def linhas_seed() -> list:
    """Instâncias novas das matrizes (NCMs do Vault + laboratórios)."""
    mva = [
        # (ncm, cest, uf, mva, base_legal)
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
        # (uf, ncm, fcp_interno, fcp_st, base_legal)
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
            base_legal=ato, data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    for uf, ncm, cest, regime, seg in enquadramento:
        linhas.append(MatrizEnquadramentoSt(
            uf_destino=uf, ncm=ncm, cest=cest, regime=regime, segmento=seg,
            data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    for uf, ncm, interno, st, ato in fcp:
        linhas.append(MatrizFcp(
            uf_destino=uf, ncm=ncm, aliq_fcp_interno=Decimal(interno),
            aliq_fcp_st=Decimal(st), base_legal=ato,
            data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    for uf_o, uf_d, acordo in protocolo:
        linhas.append(MatrizProtocoloSt(
            uf_origem=uf_o, uf_destino=uf_d, numero_acordo=acordo,
            data_inicio_vigencia=_INICIO, data_fim_vigencia=_FIM,
        ))
    return linhas


async def aplicar_seed(session: AsyncSession) -> int:
    """Insere o seed por família se ela estiver vazia (idempotente, inclusive em
    bancos que já receberam o seed antigo sem alíquotas). Retorna o nº inserido."""
    inseridas = 0
    if not await session.scalar(select(func.count()).select_from(MatrizMva)):
        linhas = linhas_seed()
        session.add_all(linhas)
        inseridas += len(linhas)
    if not await session.scalar(select(func.count()).select_from(MatrizAliquota)):
        linhas = linhas_aliquotas()
        session.add_all(linhas)
        inseridas += len(linhas)
    if inseridas:
        await session.flush()
    return inseridas


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
