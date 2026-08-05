"""Frescor da base de matrizes (Fase 2 da automação).

Responde "quando alguém confirmou a base pela última vez?" — o carimbo que a
carta de ST imprime no aviso de legislação vigente ("base de matrizes
atualizada em DD/MM/AAAA") e o painel de Saúde detalha por matriz: quanto da
base VIGENTE foi verificado nos últimos 90 dias e o que está envelhecendo.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.propostas_models import (
    STATUS_PENDENTE,
    MatrizProposta,
)
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia

# Mesmas chaves do registry das matrizes (bulk/CRUD) — a tela traduz o rótulo.
_MATRIZES = (
    ("enquadramento", MatrizEnquadramentoSt),
    ("mva", MatrizMva),
    ("protocolos", MatrizProtocoloSt),
    ("aliquotas", MatrizAliquota),
    ("fcp", MatrizFcp),
)

JANELA_FRESCOR_DIAS = 90


async def ultima_atualizacao_matrizes(session: AsyncSession) -> datetime | None:
    """Verificação mais RECENTE entre todas as matrizes — quando a base foi
    tocada por um humano pela última vez. None = base vazia."""
    datas = []
    for _tipo, modelo in _MATRIZES:
        d = await session.scalar(select(func.max(modelo.ultima_verificacao_em)))
        if d is not None:
            datas.append(d)
    return max(datas) if datas else None


async def saude_matrizes(session: AsyncSession) -> dict:
    """Radar de frescor por matriz: linhas VIGENTES hoje, quantas foram
    verificadas na janela de 90 dias, a verificação mais antiga (o ponto
    fraco) e a mais recente. Só as vigentes contam — regra encerrada não
    envelhece ninguém."""
    agora = datetime.now(UTC)
    corte = agora - timedelta(days=JANELA_FRESCOR_DIAS)
    hoje = agora.date()

    matrizes = []
    total_vigentes = total_verificadas = 0
    for tipo, modelo in _MATRIZES:
        vigentes = await session.scalar(select(func.count()).select_from(
            filtrar_vigencia(select(modelo.id), modelo, hoje).subquery()
        )) or 0
        verificadas = await session.scalar(select(func.count()).select_from(
            filtrar_vigencia(
                select(modelo.id).where(modelo.ultima_verificacao_em >= corte),
                modelo, hoje,
            ).subquery()
        )) or 0
        mais_antiga = await session.scalar(
            filtrar_vigencia(select(func.min(modelo.ultima_verificacao_em)), modelo, hoje)
        )
        ultima = await session.scalar(select(func.max(modelo.ultima_verificacao_em)))
        matrizes.append({
            "tipo": tipo,
            "vigentes": vigentes,
            "verificadas_90d": verificadas,
            "pct_90d": round(verificadas / vigentes * 100) if vigentes else None,
            "verificacao_mais_antiga": mais_antiga.isoformat() if mais_antiga else None,
            "ultima_atualizacao": ultima.isoformat() if ultima else None,
        })
        total_vigentes += vigentes
        total_verificadas += verificadas

    pendentes = await session.scalar(
        select(func.count()).select_from(MatrizProposta)
        .where(MatrizProposta.status == STATUS_PENDENTE)
    ) or 0
    ultima_geral = await ultima_atualizacao_matrizes(session)
    return {
        "geral": {
            "vigentes": total_vigentes,
            "pct_verificado_90d": (
                round(total_verificadas / total_vigentes * 100) if total_vigentes else None
            ),
            "ultima_atualizacao": ultima_geral.isoformat() if ultima_geral else None,
            "propostas_pendentes": pendentes,
            "janela_dias": JANELA_FRESCOR_DIAS,
        },
        "matrizes": matrizes,
    }
