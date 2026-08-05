"""Reconferência semestral de alíquotas e FCP (Fase 4 da automação).

Alíquota modal e FCP mudam pouco — mas quando mudam (AL 19%→20,5%, PR 19,5%
em 2024, RJ 20% em 2024), alguém precisa notar. A cada ciclo (semestre), as
linhas VIGENTES das UFs alvo que não foram verificadas dentro do ciclo viram
proposta REVALIDAR na fila: aprovar = "continua valendo" (renova o carimbo);
mudou? o curador rejeita e ajusta pelo CRUD com vigência nova.

O hash da proposta inclui o CICLO: rejeitar/pendurar vale só para o ciclo
corrente — no semestre seguinte a pergunta volta, como deve ser.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.crawlers.propor import hash_proposta
from app.modules.fiscal.infrastructure.matrizes_models import MatrizAliquota, MatrizFcp
from app.modules.fiscal.infrastructure.propostas_models import (
    ACAO_REVALIDAR,
    STATUS_APROVADA,
    MatrizProposta,
)
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia


def _payload_aliquota(linha: MatrizAliquota) -> dict:
    return {
        "uf_destino": linha.uf_destino,
        "aliq_modal": str(linha.aliq_modal),
        "aliq_fcp_integrado": str(linha.aliq_fcp_integrado),
        "base_legal": linha.base_legal,
        "data_inicio_vigencia": linha.data_inicio_vigencia.isoformat(),
        "data_fim_vigencia": (
            linha.data_fim_vigencia.isoformat() if linha.data_fim_vigencia else None
        ),
    }


def _payload_fcp(linha: MatrizFcp) -> dict:
    return {
        "uf_destino": linha.uf_destino,
        "ncm": linha.ncm,
        "aliq_fcp_st": str(linha.aliq_fcp_st),
        "aliq_fcp_interno": str(linha.aliq_fcp_interno),
        "base_legal": linha.base_legal,
        "data_inicio_vigencia": linha.data_inicio_vigencia.isoformat(),
        "data_fim_vigencia": (
            linha.data_fim_vigencia.isoformat() if linha.data_fim_vigencia else None
        ),
    }


async def propor_reconferencia(
    session: AsyncSession, ufs: list[str], *, ciclo: str, inicio_ciclo: datetime,
) -> dict:
    """Gera as propostas REVALIDAR do ciclo para as UFs alvo. Pula linha já
    verificada dentro do ciclo (fresca) e proposta idêntica pendente ou
    rejeitada NESTE ciclo (hash inclui o ciclo)."""
    vistos = set((await session.execute(
        select(MatrizProposta.hash_proposta).where(
            MatrizProposta.tipo_matriz.in_(("aliquotas", "fcp")),
            MatrizProposta.status != STATUS_APROVADA,
        )
    )).scalars())

    hoje = date.today()
    criadas = frescas = 0
    for uf in ufs:
        alvos: list[tuple[str, object, dict, str]] = []

        aliquota = (await session.execute(
            filtrar_vigencia(
                select(MatrizAliquota).where(MatrizAliquota.uf_destino == uf),
                MatrizAliquota, hoje,
            ).order_by(MatrizAliquota.data_inicio_vigencia.desc()).limit(1)
        )).scalars().first()
        if aliquota is not None:
            alvos.append((
                "aliquotas", aliquota, _payload_aliquota(aliquota),
                f"{uf} · Alíquota modal {aliquota.aliq_modal}%",
            ))

        fcps = (await session.execute(
            filtrar_vigencia(
                select(MatrizFcp).where(MatrizFcp.uf_destino == uf), MatrizFcp, hoje,
            )
        )).scalars().all()
        for f in fcps:
            alvos.append((
                "fcp", f, _payload_fcp(f),
                f"{uf} · FCP {f.ncm} ({f.aliq_fcp_st}%)",
            ))

        for tipo, linha, payload, chave in alvos:
            verificada = linha.ultima_verificacao_em
            # sqlite devolve naive; Postgres, aware — normaliza para comparar.
            if verificada is not None and verificada.tzinfo is None:
                verificada = verificada.replace(tzinfo=UTC)
            if verificada is not None and verificada >= inicio_ciclo:
                frescas += 1                      # já conferida neste ciclo
                continue
            h = hash_proposta(tipo, {**payload, "_ciclo": ciclo})
            if h in vistos:
                continue                          # pendente/rejeitada no ciclo
            vistos.add(h)
            session.add(MatrizProposta(
                tipo_matriz=tipo, acao=ACAO_REVALIDAR, chave_resumo=chave,
                payload=payload, linha_atual_id=linha.id, linha_atual=payload,
                fonte=f"Reconferência semestral {ciclo}", hash_proposta=h,
            ))
            criadas += 1

    await session.flush()
    return {"ciclo": ciclo, "ufs": ufs, "propostas": criadas, "frescas": frescas}
