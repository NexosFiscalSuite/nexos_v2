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
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizEnquadramentoSt,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.propostas_models import (
    ACAO_ATUALIZAR,
    ACAO_INSERIR,
    ACAO_NOVA_VIGENCIA,
    STATUS_APROVADA,
    FonteSnapshot,
    MatrizProposta,
)
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia
from app.shared.domain.uf import CURINGA_UF

from .base import CestRecord
from .sefaz_mg_mva import MvaRecord

BASE_LEGAL_AUTO = "Convênio ICMS 142/2018 (auto/CONFAZ)"
# Prefixo: a base legal por linha ganha o âmbito/acordo (estilo dos portais
# de consulta) — o prefixo identifica "linha do robô" (startswith).
BASE_LEGAL_AUTO_MVA = "RICMS/MG 2023, Anexo VII"


def _base_legal_mva(r: MvaRecord, uf_origem: str = CURINGA_UF) -> str:
    sufixo = f", âmbito {r.ambitos[0]}" if r.ambitos else ", Parte 2"
    origem = "" if uf_origem == CURINGA_UF else f" · origem {uf_origem}"
    return f"{BASE_LEGAL_AUTO_MVA}{sufixo}{origem} (auto/SEFAZ-MG)"[:120]


def _origem_legivel(uf_origem: str) -> str:
    return "qualquer origem" if uf_origem == CURINGA_UF else uf_origem


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


def _congelar_mva(linha: MatrizMva) -> dict:
    return {
        "mva_original": str(linha.mva_original),
        "base_legal": linha.base_legal,
        "data_inicio_vigencia": linha.data_inicio_vigencia.isoformat(),
        "data_fim_vigencia": (
            linha.data_fim_vigencia.isoformat() if linha.data_fim_vigencia else None
        ),
    }


async def propor_mva(
    session: AsyncSession, registros: list[MvaRecord], *,
    uf: str, vigencia_inicio: date, vigencia_mudanca: date,
    fonte: str, snapshot_id: int | None = None,
) -> dict:
    """Diff das MVAs do anexo contra a matriz vigente da UF → propostas.

    A chave é (NCM, CEST, **UF de origem**, UF de destino): a mesma da
    `MatrizMva.CHAVE_VIGENCIA`. A origem sai de `MvaRecord.origens()` — o
    âmbito do anexo resolvido pela legenda (`resolver_origens`); linha sem
    âmbito legível vira uma proposta com CURINGA_UF ("qualquer origem"),
    o comportamento anterior a esta fase.

    Regras (espelham o enquadramento): chave sem linha → INSERIR com a
    vigência-piso; linha do PRÓPRIO robô com MVA diferente → NOVA_VIGENCIA a
    partir de `vigencia_mudanca` (1º do mês da detecção — o anexo não publica
    a data exata da mudança por item; o curador rejeita e lança na mão se
    souber a data legal); curadoria manual NUNCA é tocada; chave com MVAs
    CONFLITANTES na própria fonte fica de fora (ambíguo, fail-closed).
    Rejeição suprime re-proposta por hash — e como o `uf_origem` entra no
    payload, o hash mudou nesta fase: rejeições antigas (origem-cegas) não
    suprimem as propostas novas, que são outra afirmação (margem X para a
    origem Y). É uma re-oferta única, e nada entra sem aprovação."""
    uf = uf.upper()

    stmt = filtrar_vigencia(
        select(MatrizMva).where(MatrizMva.uf_destino == uf), MatrizMva, date.today()
    )
    atuais = {
        (r.ncm, r.cest, r.uf_origem): r for r in (await session.execute(stmt)).scalars()
    }

    vistos = set((await session.execute(
        select(MatrizProposta.hash_proposta).where(
            MatrizProposta.tipo_matriz == "mva",
            MatrizProposta.status != STATUS_APROVADA,
        )
    )).scalars())

    # Dedup da fonte com detecção de conflito: mesma chave com MVAs distintas
    # (capítulos/âmbitos diferentes) é ambígua — não vira proposta. Com a
    # origem na chave, duas margens de ORIGENS diferentes deixam de brigar:
    # deixam de ser "conflito" e viram duas linhas legítimas.
    por_chave: dict[tuple[str, str, str], set[Decimal]] = {}
    exemplo: dict[tuple[str, str, str], MvaRecord] = {}
    for r in registros:
        for uf_origem in r.origens():
            chave = (r.ncm, r.cest, uf_origem)
            por_chave.setdefault(chave, set()).add(r.mva)
            exemplo.setdefault(chave, r)

    criadas = suprimidas = inalteradas = ambiguos = 0
    for chave, mvas in por_chave.items():
        if len(mvas) > 1:
            ambiguos += 1
            continue
        r = exemplo[chave]
        uf_origem = chave[2]
        atual = atuais.get(chave)
        eh_auto = bool(atual is not None and (atual.base_legal or "").startswith(BASE_LEGAL_AUTO_MVA))
        base = {
            "ncm": r.ncm, "cest": r.cest,
            "uf_origem": uf_origem, "uf_destino": uf,
            "mva_original": str(r.mva), "base_legal": _base_legal_mva(r, uf_origem),
            "data_fim_vigencia": None,
        }
        if atual is None:
            payload = {**base, "data_inicio_vigencia": vigencia_inicio.isoformat()}
            acao, linha_id, congelada = ACAO_INSERIR, None, None
        elif eh_auto and atual.mva_original != r.mva:
            payload = {**base, "data_inicio_vigencia": vigencia_mudanca.isoformat()}
            acao, linha_id, congelada = ACAO_NOVA_VIGENCIA, atual.id, _congelar_mva(atual)
        else:
            inalteradas += 1                     # igual, ou curadoria manual
            continue

        h = hash_proposta("mva", payload)
        if h in vistos:
            suprimidas += 1
            continue
        vistos.add(h)
        session.add(MatrizProposta(
            tipo_matriz="mva", acao=acao,
            chave_resumo=(
                f"{_origem_legivel(uf_origem)} → {uf} · NCM {r.ncm} · CEST {r.cest}"
            )[:200],
            payload=payload, linha_atual_id=linha_id, linha_atual=congelada,
            fonte=fonte, fonte_snapshot_id=snapshot_id, hash_proposta=h,
        ))
        criadas += 1

    await session.flush()
    return {
        "uf": uf, "lidos": len(registros), "pares": len(por_chave),
        "com_origem": sum(1 for c in por_chave if c[2] != CURINGA_UF),
        "propostas": criadas, "suprimidas": suprimidas,
        "sem_mudanca": inalteradas, "ambiguos": ambiguos,
    }


async def propor_protocolos_mg(
    session: AsyncSession, registros: list[MvaRecord],
    ambitos: dict[str, list[tuple[str, str]]], *,
    vigencia_inicio: date, fonte: str, snapshot_id: int | None = None,
) -> dict:
    """Protocolos/Convênios extraídos da legenda de 'Âmbito de Aplicação' do
    Anexo VII (MG): para cada item, cada UF do âmbito vira proposta de acordo
    UF→MG **escopado pelo NCM do item** — nunca par inteiro (fail-closed: o
    acordo vale para aquele produto, não para tudo). A base legal por linha
    sai no estilo dos portais: acordo + âmbito. Exceções do item (ex.:
    'Exceção: Rondônia') excluem a UF. Linha já existente na matriz para
    (par, acordo, NCM) — de qualquer origem — não é re-proposta."""
    uf_destino = "MG"

    # (uf_origem, acordo, ncm) já vigentes hoje para o destino (uma query).
    stmt = filtrar_vigencia(
        select(MatrizProtocoloSt).where(MatrizProtocoloSt.uf_destino == uf_destino),
        MatrizProtocoloSt, date.today(),
    )
    existentes = {
        (r.uf_origem, r.numero_acordo, r.ncm)
        for r in (await session.execute(stmt)).scalars()
    }

    vistos = set((await session.execute(
        select(MatrizProposta.hash_proposta).where(
            MatrizProposta.tipo_matriz == "protocolos",
            MatrizProposta.status != STATUS_APROVADA,
        )
    )).scalars())

    # Alvos únicos: cada (UF origem, acordo, NCM) com o âmbito de referência.
    alvos: dict[tuple[str, str, str], str] = {}
    for r in registros:
        for codigo in r.ambitos:
            for uf_origem, acordo in ambitos.get(codigo, []):
                if uf_origem in r.excecoes or uf_origem == uf_destino:
                    continue
                alvos.setdefault((uf_origem, acordo, r.ncm), codigo)

    criadas = suprimidas = ja_curados = 0
    for (uf_origem, acordo, ncm), codigo in alvos.items():
        if (uf_origem, acordo, ncm) in existentes:
            ja_curados += 1
            continue
        payload = {
            "uf_origem": uf_origem, "uf_destino": uf_destino, "ncm": ncm,
            "numero_acordo": acordo, "situacao": "ATIVO",
            "base_legal": f"{acordo} — RICMS/MG 2023, Anexo VII, âmbito {codigo} (auto)"[:120],
            "data_inicio_vigencia": vigencia_inicio.isoformat(),
            "data_fim_vigencia": None,
        }
        h = hash_proposta("protocolos", payload)
        if h in vistos:
            suprimidas += 1
            continue
        vistos.add(h)
        session.add(MatrizProposta(
            tipo_matriz="protocolos", acao=ACAO_INSERIR,
            chave_resumo=f"{uf_origem} · {uf_destino} · {acordo} · NCM {ncm}",
            payload=payload, fonte=fonte, fonte_snapshot_id=snapshot_id,
            hash_proposta=h,
        ))
        criadas += 1

    await session.flush()
    return {
        "alvos": len(alvos), "propostas": criadas,
        "suprimidas": suprimidas, "ja_curados": ja_curados,
    }
