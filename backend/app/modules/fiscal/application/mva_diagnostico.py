"""Por que o motor achou (ou NÃO achou) a MVA de uma chave concreta.

Quando falta MVA, o motor só sabia dizer "não há MVA cadastrada para
NCM/CEST/UF na data". Isso não diagnostica nada: não diz o que EXISTE na
matriz nem por que a linha existente não casou — e o analista fica adivinhando
entre as duas causas mais comuns:

1. **Vigência.** Toda linha vinda da carga do Anexo VII começa na
   vigência-piso do crawler (`crawler_vigencia_inicio`). Nota emitida ANTES
   dessa data não enxerga nenhuma delas (ADR-0002: vale a regra da data de
   emissão) — a matriz está cheia e o motor continua sem margem.
2. **UF de origem.** A MVA é quebrada por UF de origem (âmbito do acordo). Se
   o fornecedor está num estado fora do âmbito, não existe linha para o par —
   nem a curinga `"*"`.

Este diagnóstico distingue as duas sozinho e mostra TODAS as linhas do NCM no
destino (inclusive as não vigentes), cada uma com o motivo de não ter casado.

**A busca é a MESMA do motor**: reusa `stmt_mva_do_motor` +
`montar_mva_snapshot` + `_MvaSnapshot.buscar` do loader. Um diagnóstico que
discorda do motor é pior do que não ter diagnóstico.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import DomainError
from app.modules.fiscal.infrastructure.matrizes_loaders import (
    _candidatos_ncm,
    _uf,
    montar_mva_snapshot,
    stmt_mva_do_motor,
)
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.shared.domain.uf import CURINGA_UF, normalizar_uf
from app.shared.domain.value_objects import only_digits

#: Teto defensivo da lista de candidatas (uma chave real tem dezenas de linhas).
LIMITE_CANDIDATAS = 500


def _br(d: date | None) -> str:
    """Data no formato que o João lê na tela."""
    return d.strftime("%d/%m/%Y") if d else "—"


def _pct(valor) -> str:
    return f"{Decimal(valor):.2f}"


def _origem_legivel(uf: str) -> str:
    return "qualquer origem (*)" if uf == CURINGA_UF else uf


def _alvo(ncm: str, cest: str) -> str:
    return f"NCM {ncm}" + (f" · CEST {cest}" if cest else "")


def _linha(r: MatrizMva) -> dict:
    return {
        "id": r.id,
        "ncm": r.ncm,
        "cest": r.cest,
        "uf_origem": _uf(r.uf_origem),
        "uf_destino": r.uf_destino,
        "mva_original": _pct(r.mva_original),
        "data_inicio_vigencia": r.data_inicio_vigencia.isoformat(),
        "data_fim_vigencia": (
            r.data_fim_vigencia.isoformat() if r.data_fim_vigencia else None
        ),
        "base_legal": r.base_legal,
    }


def _vigente(r: MatrizMva, data: date) -> bool:
    """Mesma regra do `filtrar_vigencia` (ADR-0002), avaliada em memória."""
    return r.data_inicio_vigencia <= data and (
        r.data_fim_vigencia is None or r.data_fim_vigencia >= data
    )


def _motivo(
    r: MatrizMva, *, cest: str, orig: str, data: date,
    aplicada_id: int | None, ncm_casado: str, origem_casada: str,
) -> tuple[bool, str]:
    """(casou, motivo) da linha — na MESMA ordem em que a busca elimina."""
    if aplicada_id is not None and r.id == aplicada_id:
        return True, "é a linha que o motor aplicou"
    if r.data_inicio_vigencia > data:
        return False, (
            f"vigência começa em {_br(r.data_inicio_vigencia)}, "
            f"depois da emissão ({_br(data)})"
        )
    if r.data_fim_vigencia is not None and r.data_fim_vigencia < data:
        return False, (
            f"vigência terminou em {_br(r.data_fim_vigencia)}, "
            f"antes da emissão ({_br(data)})"
        )
    if cest and r.cest != cest:
        return False, (
            f"a linha é do CEST {r.cest or '—'} e o item veio com CEST {cest}"
        )
    origem_linha = _uf(r.uf_origem)
    if origem_linha not in (orig, CURINGA_UF):
        if orig == CURINGA_UF:
            return False, (
                f"a consulta não informou a UF de origem (só a regra curinga '*' "
                f"entra) e esta linha vale só para {origem_linha}"
            )
        return False, f"a linha vale só para a origem {origem_linha} e a nota saiu de {orig}"
    if aplicada_id is not None:
        return False, (
            f"vigente e compatível, mas perdeu a precedência para a linha "
            f"#{aplicada_id} (NCM {ncm_casado} · origem {_origem_legivel(origem_casada)}) "
            "— o NCM mais específico vem primeiro e, dentro dele, a origem exata "
            "vence o curinga"
        )
    return False, (
        "vigente e compatível, mas o item veio sem CEST e o NCM tem MVAs "
        "diferentes — o motor trava por segurança em vez de escolher uma"
    )


def _mvas_do_grupo_ambiguo(dados: dict, ncm: str, orig: str, dest: str) -> list[str]:
    """As MVAs em conflito no caminho "XML sem CEST" — mesmo laço do `buscar`."""
    origens = (orig,) if orig == CURINGA_UF else (orig, CURINGA_UF)
    for c in _candidatos_ncm(ncm):
        for o in origens:
            pares = [
                v for (n, _ce, uo, ud), v in dados.items()
                if n == c and uo == o and ud == dest
            ]
            if pares:
                return sorted({_pct(p[0]) for p in pares})
    return []


async def diagnosticar_mva(
    session: AsyncSession, *,
    ncm: str,
    uf_destino: str,
    cest: str | None = None,
    uf_origem: str | None = None,
    data: date | None = None,
) -> dict:
    """Explica, para uma chave concreta, o resultado da busca de MVA do motor.

    `uf_origem` vazia é tratada como o curinga `"*"`: sem saber o remetente, só
    a regra que vale para qualquer origem pode ser considerada — é exatamente o
    que o motor faria.
    """
    ncm_l = only_digits(ncm)
    if not ncm_l:
        raise DomainError("Informe o NCM (só dígitos) para diagnosticar a MVA.")
    dest = normalizar_uf(uf_destino)
    if dest is None:
        raise DomainError(f"UF de destino inválida: {uf_destino!r}.")
    orig = CURINGA_UF
    if (uf_origem or "").strip():
        orig = normalizar_uf(uf_origem, permitir_curinga=True) or ""
        if not orig:
            raise DomainError(f"UF de origem inválida: {uf_origem!r}.")
    cest_l = only_digits(cest or "")
    dia = data or date.today()
    consulta = {
        "ncm": ncm_l, "cest": cest_l, "uf_origem": orig,
        "uf_destino": dest, "data": dia.isoformat(),
    }
    niveis = _candidatos_ncm(ncm_l)

    # 1. A busca do MOTOR, letra por letra (mesma query, mesmo snapshot).
    motor_rows = (
        await session.execute(stmt_mva_do_motor(orig, dest, niveis, dia))
    ).scalars().all()
    snapshot = montar_mva_snapshot(motor_rows)
    info = snapshot.buscar(ncm_l, cest_l, orig, dest, dia)

    # 2. TODAS as linhas do NCM naquele destino — sem filtro de vigência nem de
    #    origem. É esta lista que mostra "existem 12 linhas, todas começando em
    #    01/06/2026".
    todas = (await session.execute(
        select(MatrizMva)
        .where(MatrizMva.uf_destino == dest, MatrizMva.ncm.in_(niveis))
        .order_by(
            func.length(MatrizMva.ncm).desc(), MatrizMva.ncm, MatrizMva.cest,
            MatrizMva.uf_origem, MatrizMva.data_inicio_vigencia, MatrizMva.id,
        )
        .limit(LIMITE_CANDIDATAS)
    )).scalars().all()

    aplicada_id = info.matriz_id if info is not None else None
    por_id = {r.id: r for r in todas}
    aplicada = _linha(por_id[aplicada_id]) if aplicada_id in por_id else None

    candidatas = []
    for r in todas:
        casou, motivo = _motivo(
            r, cest=cest_l, orig=orig, data=dia, aplicada_id=aplicada_id,
            ncm_casado=info.ncm_casado if info else "",
            origem_casada=info.uf_origem_casada if info else "",
        )
        candidatas.append({**_linha(r), "casou": casou, "motivo": motivo})
    # A linha aplicada primeiro: é a resposta, não um detalhe no meio da lista.
    candidatas.sort(key=lambda c: not c["casou"])

    veredicto, explicacao, acao = _veredicto(
        info=info, todas=todas, snapshot=snapshot,
        ncm=ncm_l, cest=cest_l, orig=orig, dest=dest, dia=dia, niveis=niveis,
    )
    return {
        "consulta": consulta,
        "veredicto": veredicto,
        "explicacao": explicacao,
        "acao_sugerida": acao,
        "aplicada": aplicada,
        "candidatas": candidatas,
    }


def _veredicto(*, info, todas, snapshot, ncm, cest, orig, dest, dia, niveis):
    """(veredicto, explicação, ação) — texto para LEIGO, sem jargão seco."""
    alvo = _alvo(ncm, cest)

    if info is not None:
        return (
            "ENCONTRADA",
            f"MVA de {_pct(info.mva_original)}% aplicada: o motor casou o {alvo} "
            f"pela linha #{info.matriz_id} (NCM {info.ncm_casado}, "
            f"{_origem_legivel(info.uf_origem_casada)} → {dest}) vigente em {_br(dia)}.",
            "Nada a corrigir na busca. Se o valor calculado ainda parece errado, "
            "confira a margem cadastrada nessa linha e a base legal dela.",
        )

    if not todas:
        escada = " / ".join(niveis)
        return (
            "SEM_LINHA_NENHUMA",
            f"Não existe NENHUMA linha de MVA para {dest} no {alvo} — o motor "
            f"procurou também pelos NCM mais gerais ({escada}) e em qualquer data, "
            "e a matriz está vazia para esse produto.",
            f"Cadastre a MVA de {_origem_legivel(orig)} → {dest} em Matrizes "
            "Fiscais › MVA, ou rode a carga do Anexo VII se o produto for de MG. "
            "Sem margem cadastrada o cálculo sai pelo valor da operação, sem MVA.",
        )

    vigentes = [r for r in todas if _vigente(r, dia)]
    if not vigentes:
        futuras = [r for r in todas if r.data_inicio_vigencia > dia]
        if futuras:
            inicio = min(r.data_inicio_vigencia for r in futuras)
            extra = ""
            encerradas = [
                r for r in todas
                if r.data_fim_vigencia is not None and r.data_fim_vigencia < dia
            ]
            if encerradas:
                fim = max(r.data_fim_vigencia for r in encerradas)
                extra = (
                    f" (outras {len(encerradas)} linha(s) já tinham encerrado "
                    f"em {_br(fim)})"
                )
            return (
                "FORA_DA_VIGENCIA",
                f"A matriz TEM {len(todas)} linha(s) de MVA para {dest} no {alvo}, "
                f"mas elas só passam a valer em {_br(inicio)} — a nota é de "
                f"{_br(dia)}, anterior a isso, então o motor não enxerga nenhuma "
                f"delas e calcula sem margem{extra}.",
                f"Se a margem já valia em {_br(dia)}, recue a data de início da "
                "vigência dessas linhas (ou cadastre a vigência do período "
                "anterior). A carga automática do Anexo VII usa uma data-piso, "
                "então notas emitidas antes dela ficam descobertas.",
            )
        fim = max(
            (r.data_fim_vigencia for r in todas if r.data_fim_vigencia is not None),
            default=None,
        )
        return (
            "FORA_DA_VIGENCIA",
            f"As {len(todas)} linha(s) de MVA de {dest} para o {alvo} tiveram a "
            f"vigência encerrada em {_br(fim)}, antes da emissão ({_br(dia)}) — "
            "não há regra valendo na data da nota.",
            "Cadastre a linha do período novo (ADR-0002: regra que muda vira "
            "linha nova, a antiga fica com a vigência encerrada).",
        )

    relevantes = [r for r in vigentes if not cest or r.cest == cest]
    if cest and not relevantes:
        cests = sorted({r.cest or "—" for r in vigentes})
        return (
            "CEST_NAO_BATE",
            f"Há {len(vigentes)} linha(s) de MVA vigentes do NCM {ncm} em {dest}, "
            f"mas todas com outro CEST ({', '.join(cests)}) — o item da nota veio "
            f"com CEST {cest}, e a busca casa NCM e CEST juntos.",
            f"Confira o CEST do item no XML. Se o correto for {cest}, cadastre a "
            "linha de MVA com esse CEST; se o item foi classificado errado, o "
            "acerto é no cadastro do produto.",
        )

    origens = sorted({_uf(r.uf_origem) for r in relevantes})
    if orig not in origens and CURINGA_UF not in origens:
        lista = ", ".join(_origem_legivel(o) for o in origens)
        if orig == CURINGA_UF:
            return (
                "ORIGEM_NAO_COBERTA",
                f"A consulta não informou a UF de origem, então só valeria uma "
                f"regra curinga (*) — e ela não existe para o {alvo} em {dest}. "
                f"As {len(relevantes)} linha(s) vigentes são de origens "
                f"específicas: {lista}.",
                "Informe a UF do fornecedor para o diagnóstico responder pelo par "
                "certo, ou cadastre uma linha com origem '*' se a margem valer "
                "para qualquer remetente.",
            )
        return (
            "ORIGEM_NAO_COBERTA",
            f"Existem {len(relevantes)} linha(s) de MVA vigentes para o {alvo} em "
            f"{dest}, mas nenhuma cobre {orig}: as origens cadastradas são {lista} "
            "e não há regra curinga (*) valendo para qualquer remetente.",
            f"Cadastre a MVA de {orig} → {dest} para esse produto. O âmbito do "
            f"acordo pode realmente não alcançar {orig} — nesse caso o certo é "
            "registrar a decisão na curadoria, não aproveitar a margem de outro "
            "estado.",
        )

    mvas = _mvas_do_grupo_ambiguo(snapshot.dados, ncm, orig, dest)
    valores = ", ".join(f"{m}%" for m in mvas) or "valores diferentes"
    return (
        "AMBIGUA",
        f"O item veio SEM CEST e o NCM {ncm} tem mais de uma margem vigente em "
        f"{dest} ({valores}) — o motor não escolhe no palpite e trava a conta.",
        "Informe o CEST do item (é ele que separa as margens) ou revise a matriz "
        "para que o NCM tenha uma margem única no par consultado.",
    )
