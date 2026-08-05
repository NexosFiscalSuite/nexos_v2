"""Frescor da base de matrizes (Fase 2 da automação).

Responde "quando alguém confirmou a base pela última vez?" — o carimbo que a
carta de ST imprime no aviso de legislação vigente ("base de matrizes
atualizada em DD/MM/AAAA") e que o radar de saúde vai detalhar por matriz.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)

_MATRIZES = (MatrizMva, MatrizEnquadramentoSt, MatrizProtocoloSt, MatrizAliquota, MatrizFcp)


async def ultima_atualizacao_matrizes(session: AsyncSession) -> datetime | None:
    """Verificação mais RECENTE entre todas as matrizes — quando a base foi
    tocada por um humano pela última vez. None = base vazia."""
    datas = []
    for modelo in _MATRIZES:
        d = await session.scalar(select(func.max(modelo.ultima_verificacao_em)))
        if d is not None:
            datas.append(d)
    return max(datas) if datas else None
