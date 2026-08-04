"""Persistência dos crawlers: snapshot da fonte + PROPOSTAS (nunca escrita direta).

Fase 1 da automação: o diff entre a fonte oficial e a matriz VIGENTE vira
`MatrizProposta` para a curadoria revisar. Regras do diff de enquadramento:

- chave (UF, NCM, CEST) sem linha vigente → proposta INSERIR (sugestão ST);
- linha do PRÓPRIO robô (base_legal auto) com segmento divergente → ATUALIZAR;
- linha curada MANUALMENTE nunca é tocada (a adesão estadual é decisão do
  analista — o universo do CONFAZ não a sobrepõe);
- proposta idêntica já pendente ou REJEITADA não volta à fila (supressão por
  hash): rejeitar uma sugestão vale para sempre, sem ruído mensal.
"""
from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import MatrizEnquadramentoSt
from app.modules.fiscal.infrastructure.propostas_models import (
    ACAO_ATUALIZAR,
    ACAO_INSERIR,
    STATUS_APROVADA,
    FonteSnapshot,
    MatrizProposta,
)
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia

from .base import CestRecord

BASE_LEGAL_AUTO = "Convênio ICMS 142/2018 (auto/CONFAZ)"


def hash_proposta(tipo: str, payload: dict) -> str:
    """Identidade da proposta: mesmo tipo + mesmo payload = mesma proposta."""
    canonico = json.dumps(
        {"tipo": tipo, **payload}, sort_keys=True, ensure_ascii=False, default=str
    )
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


async def registrar_snapshot(
    session: AsyncSession, *, fonte: str, url: str, conteudo: bytes,
    resumo: str | None = None,
) -> tuple[bool, int]:
    """Grava a captura da fonte SE o conteúdo mudou desde a última (hash).
    Retorna (mudou, snapshot_id) — sem mudança, aponta para o snapshot vigente."""
    digest = hashlib.sha256(conteudo).hexdigest()
    ultimo = (await session.execute(
        select(FonteSnapshot).where(FonteSnapshot.fonte == fonte)
        .order_by(FonteSnapshot.baixado_em.desc(), FonteSnapshot.id.desc()).limit(1)
    )).scalars().first()
    if ultimo is not None and ultimo.hash_conteudo == digest:
        return False, ultimo.id
    snap = FonteSnapshot(
        fonte=fonte, url=url, hash_conteudo=digest, resumo=resumo, conteudo=conteudo
    )
    session.add(snap)
    await session.flush()
    return True, snap.id


def _congelar(linha: MatrizEnquadramentoSt) -> dict:
    """O lado 'vigente' do diff que a tela de revisão mostra."""
    return {
        "regime": linha.regime,
        "segmento": linha.segmento,
        "base_legal": linha.base_legal,
        "data_inicio_vigencia": linha.data_inicio_vigencia.isoformat(),
        "data_fim_vigencia": (
            linha.data_fim_vigencia.isoformat() if linha.data_fim_vigencia else None
        ),
    }


async def propor_enquadramento(
    session: AsyncSession, registros: list[CestRecord], *,
    uf: str, vigencia_inicio: date, fonte: str, snapshot_id: int | None = None,
) -> dict:
    """Diff da relação NCM×CEST do CONFAZ contra a matriz vigente da UF →
    propostas na fila. Retorna o resumo do job (por UF)."""
    uf = uf.upper()

    # Linhas vigentes HOJE na UF (uma query) — o lado 'atual' do diff.
    stmt = filtrar_vigencia(
        select(MatrizEnquadramentoSt).where(MatrizEnquadramentoSt.uf_destino == uf),
        MatrizEnquadramentoSt,
        date.today(),
    )
    atuais = {(r.ncm, r.cest): r for r in (await session.execute(stmt)).scalars()}

    # Hashes já na fila (pendentes) ou vetados (rejeitadas): não re-propor.
    vistos = set((await session.execute(
        select(MatrizProposta.hash_proposta).where(
            MatrizProposta.tipo_matriz == "enquadramento",
            MatrizProposta.status != STATUS_APROVADA,
        )
    )).scalars())

    criadas = suprimidas = inalteradas = 0
    dedup: set[tuple[str, str]] = set()
    for r in registros:
        chave = (r.ncm, r.cest)
        if chave in dedup:                    # a fonte repete linhas
            continue
        dedup.add(chave)
        atual = atuais.get(chave)
        if atual is None:
            payload = {
                "uf_destino": uf, "ncm": r.ncm, "cest": r.cest, "regime": "ST",
                "segmento": r.segmento, "base_legal": BASE_LEGAL_AUTO,
                "data_inicio_vigencia": vigencia_inicio.isoformat(),
                "data_fim_vigencia": None,
            }
            acao, linha_id, congelada = ACAO_INSERIR, None, None
        elif atual.base_legal == BASE_LEGAL_AUTO and r.segmento and r.segmento != atual.segmento:
            payload = {
                "uf_destino": uf, "ncm": r.ncm, "cest": r.cest, "regime": atual.regime,
                "segmento": r.segmento, "base_legal": BASE_LEGAL_AUTO,
                "data_inicio_vigencia": atual.data_inicio_vigencia.isoformat(),
                "data_fim_vigencia": (
                    atual.data_fim_vigencia.isoformat() if atual.data_fim_vigencia else None
                ),
            }
            acao, linha_id, congelada = ACAO_ATUALIZAR, atual.id, _congelar(atual)
        else:
            inalteradas += 1                  # igual, ou curadoria manual (não toca)
            continue

        h = hash_proposta("enquadramento", payload)
        if h in vistos:
            suprimidas += 1
            continue
        vistos.add(h)
        session.add(MatrizProposta(
            tipo_matriz="enquadramento", acao=acao,
            chave_resumo=f"{uf} · NCM {r.ncm} · CEST {r.cest}",
            payload=payload, linha_atual_id=linha_id, linha_atual=congelada,
            fonte=fonte, fonte_snapshot_id=snapshot_id, hash_proposta=h,
        ))
        criadas += 1

    await session.flush()
    return {
        "uf": uf, "lidos": len(registros), "propostas": criadas,
        "suprimidas": suprimidas, "sem_mudanca": inalteradas,
    }
