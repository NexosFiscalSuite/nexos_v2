"""Persistência idempotente do resultado dos crawlers nas matrizes.

A relação NCM×CEST do CONFAZ define quais produtos SÃO sujeitos à ST — alimenta
a matriz de Enquadramento (mesma do CRUD da UI). Por UF, pois a adesão é
estadual: o job recebe a UF do nicho do escritório. É idempotente (vigência-aware):
pré-carrega o que já existe e só insere/atualiza o necessário (sem N+1).

ATENÇÃO FISCAL: a lista do CONFAZ é o UNIVERSO nacional de CEST; a adesão real
por estado é um subconjunto. Tratamos o resultado como SUGESTÃO (regime ST) que
o analista revisa/ajusta na tela — auto-alimentação, não verdade absoluta.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import MatrizEnquadramentoSt

from .base import CestRecord


async def upsert_enquadramento(
    session: AsyncSession,
    registros: list[CestRecord],
    *,
    uf: str,
    vigencia_inicio: date,
    regime: str = "ST",
    ato_legal: str = "Convênio ICMS 142/2018 (auto/CONFAZ)",
) -> dict:
    """Upsert dos NCM×CEST na matriz de Enquadramento. Chave de unicidade:
    (uf_destino, ncm, cest, data_inicio_vigencia). Retorna o resumo do job."""
    uf = uf.upper()

    # Pré-carrega a vigência atual da UF numa query (evita N+1 no lote grande).
    existentes = {
        (e.ncm, e.cest): e
        for e in (
            await session.execute(
                select(MatrizEnquadramentoSt).where(
                    MatrizEnquadramentoSt.uf_destino == uf,
                    MatrizEnquadramentoSt.data_inicio_vigencia == vigencia_inicio,
                )
            )
        ).scalars()
    }

    inseridos = atualizados = 0
    vistos: set[tuple[str, str]] = set()
    for r in registros:
        chave = (r.ncm, r.cest)
        if chave in vistos:          # a planilha repete linhas; dedup no lote
            continue
        vistos.add(chave)
        atual = existentes.get(chave)
        if atual is not None:
            atual.regime = regime
            atual.segmento = r.segmento or atual.segmento
            atual.ato_legal = ato_legal
            atualizados += 1
        else:
            session.add(MatrizEnquadramentoSt(
                uf_destino=uf, ncm=r.ncm, cest=r.cest, regime=regime,
                segmento=r.segmento, ato_legal=ato_legal,
                data_inicio_vigencia=vigencia_inicio, data_fim_vigencia=None,
            ))
            inseridos += 1
    return {"uf": uf, "lidos": len(registros), "inseridos": inseridos, "atualizados": atualizados}
