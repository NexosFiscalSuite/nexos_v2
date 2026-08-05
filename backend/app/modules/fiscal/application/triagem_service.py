"""Triagem das divergências de ST (roadmap do motor, item 1).

A auditoria diz O QUE está errado; a triagem registra o que o escritório FEZ
com isso: COBRADA (carta ao fornecedor), JUSTIFICADA (base normativa aceita —
baixa do apontamento) ou ACEITA (o cliente assume/recolhe). Vive em tabela
própria porque a auditoria é recalculada a cada reprocessamento — a decisão
do analista sobrevive, ancorada em (nota_id, numero_item).
"""
from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.modules.fiscal.infrastructure.models import TRIAGENS, DivergenciaTriagem

EM_ABERTO = "EM_ABERTO"


async def definir_triagem(
    session: AsyncSession, *,
    tenant_id: UUID, empresa_id: UUID,
    itens: list[tuple[UUID, int]], status: str,
    observacao: str | None = None, por: str | None = None,
    apenas_em_aberto: bool = False,
) -> dict:
    """Define a triagem de um LOTE de itens (nota_id, numero_item).

    `status` EM_ABERTO limpa a triagem (volta ao padrão); `apenas_em_aberto`
    (usado pela carta automática) preserva decisão já tomada pelo analista.
    """
    if status != EM_ABERTO and status not in TRIAGENS:
        raise DomainError(
            f"Triagem inválida: {status} (use {EM_ABERTO}, {', '.join(TRIAGENS)})."
        )
    pares = list(dict.fromkeys(itens))
    if not pares:
        return {"definidos": 0, "mantidos": 0, "limpos": 0}

    t = DivergenciaTriagem
    rows = (await session.execute(
        select(t).where(
            t.empresa_id == empresa_id,
            or_(*[and_(t.nota_id == nid, t.numero_item == ni) for nid, ni in pares]),
        )
    )).scalars().all()
    por_par = {(r.nota_id, r.numero_item): r for r in rows}

    obs = (observacao or "").strip()[:300] or None
    agora = datetime.now(UTC)
    definidos = mantidos = limpos = 0
    for nid, ni in pares:
        atual = por_par.get((nid, ni))
        if status == EM_ABERTO:
            if atual is not None:
                await session.delete(atual)
                limpos += 1
            continue
        if atual is not None:
            if apenas_em_aberto:
                mantidos += 1          # o analista já decidiu — a carta não sobrepõe
                continue
            atual.status = status
            atual.observacao = obs
            atual.definido_por = por
            atual.definido_em = agora
        else:
            session.add(DivergenciaTriagem(
                tenant_id=tenant_id, empresa_id=empresa_id,
                nota_id=nid, numero_item=ni, status=status,
                observacao=obs, definido_por=por, definido_em=agora,
            ))
        definidos += 1
    await session.flush()
    return {"definidos": definidos, "mantidos": mantidos, "limpos": limpos}
