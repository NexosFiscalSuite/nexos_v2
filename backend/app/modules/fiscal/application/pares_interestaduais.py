"""Fila de pares interestaduais (Fase 3 da automação).

Cruza o que a carteira MOVIMENTA entre UFs (notas importadas, sob RLS) com a
curadoria da matriz de Protocolos (global). Par com notas e SEM nenhuma linha
na matriz trava o motor interestadual (ERRO_PROTOCOLO_NAO_AVALIADO) — a fila
ordena por dinheiro em jogo para a curadoria atacar o que mais destrava.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import MatrizProtocoloSt
from app.modules.fiscal.infrastructure.models import Nota
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia


async def pares_interestaduais(session: AsyncSession, limite: int = 50) -> dict:
    """Pares UF origem→destino das notas ativas de mercadoria × curadoria de
    protocolo. `curado` = existe QUALQUER linha do par (mesmo SEM_ACORDO —
    o registro explícito também é curadoria); `acordos_ativos` = acordos
    ATIVOS vigentes hoje."""
    valor = func.coalesce(func.sum(Nota.valor_total), 0)
    stmt = (
        select(Nota.uf_emit, Nota.uf_dest, func.count(Nota.id), valor)
        .where(
            Nota.status == "ativa",
            Nota.fluxo.in_(("entrada", "saida")),   # CT-e/serviço fora: ST é mercadoria
            Nota.uf_emit.is_not(None),
            Nota.uf_dest.is_not(None),
            Nota.uf_emit != Nota.uf_dest,
        )
        .group_by(Nota.uf_emit, Nota.uf_dest)
        .order_by(valor.desc())
        .limit(limite)
    )
    movimento = (await session.execute(stmt)).all()

    curados = {
        (o, d) for o, d in (await session.execute(
            select(MatrizProtocoloSt.uf_origem, MatrizProtocoloSt.uf_destino).distinct()
        )).all()
    }
    ativos = {
        (o, d): n for o, d, n in (await session.execute(
            filtrar_vigencia(
                select(
                    MatrizProtocoloSt.uf_origem, MatrizProtocoloSt.uf_destino,
                    func.count(),
                )
                .where(MatrizProtocoloSt.situacao == "ATIVO")
                .group_by(MatrizProtocoloSt.uf_origem, MatrizProtocoloSt.uf_destino),
                MatrizProtocoloSt,
                date.today(),
            )
        )).all()
    }

    pares = [{
        "uf_origem": o, "uf_destino": d,
        "notas": n, "valor": float(v or 0),
        "curado": (o, d) in curados,
        "acordos_ativos": ativos.get((o, d), 0),
    } for o, d, n, v in movimento]
    return {
        "pares": pares,
        "nao_avaliados": sum(1 for p in pares if not p["curado"]),
    }
