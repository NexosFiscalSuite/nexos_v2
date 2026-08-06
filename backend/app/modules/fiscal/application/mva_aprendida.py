"""MVA aprendida das próprias notas — proposta na fila, nunca linha na matriz.

Hoje só MG tem MVA de fonte oficial automatizada; nas outras UFs a margem é
digitada à mão, produto por produto. Mas boa parte das NF-e JÁ traz a margem
que o fornecedor usou (`pMVAST`). Quando vários fornecedores INDEPENDENTES
declaram o mesmo número para o mesmo produto e o mesmo par de estados, isso é
um indício forte — bom o bastante para virar uma SUGESTÃO ao curador, jamais
para entrar sozinho na matriz.

A armadilha que desenha este módulo
-----------------------------------
`pMVAST` no XML nem sempre é a MVA ORIGINAL (a que a matriz guarda). Em
operação interestadual com emitente do regime normal, o que vem declarado é a
MVA AJUSTADA — a original corrigida pela diferença entre a alíquota
interestadual e a interna (ver `domain/st/mva.py::calcular_mva`). Tomar a
ajustada como original cadastraria margem errada em escala, exatamente o
oposto do que se quer consertar.

Por isso o v1 aprende SOMENTE onde o declarado É a original por lei — as duas
travas do próprio motor:

- **operação interna** (`uf_emit == uf_dest`): o ajuste é conceitualmente
  impossível (trava 4 de `calcular_mva`);
- **emitente do Simples Nacional** (CRT 1 ou 4): não ajusta, por força do
  Convênio ICMS 142/2018 (trava 1).

Interestadual com emitente do regime normal fica FORA: daria para inverter a
fórmula do ajuste, mas isso exige ter CERTEZA de que o emitente ajustou (e com
quais alíquotas) — incerteza que viraria número errado. Fica para uma fase 2,
com o motor confirmando o ajuste, não com palpite.

Regras do consenso (todas obrigatórias para propor)
---------------------------------------------------
1. `min_fornecedores` CNPJs de emitente DISTINTOS declarando o mesmo valor
   (tolerância de 0,01 ponto). Volume não conta: um fornecedor que manda 50
   notas continua valendo 1 — a força do sinal é a independência.
2. Sem valor concorrente relevante: se dois valores diferentes têm 2+
   fornecedores cada, é ambiguidade → não propõe (fail-closed, regra 2 do
   CLAUDE.md; incerteza não vira palpite).
3. Sem linha na matriz de MVA cobrindo a chave no período — curadoria já feita
   nunca é desafiada por dado aprendido.

Só notas de ENTRADA alimentam o aprendizado: a declaração precisa vir de um
TERCEIRO (o fornecedor). Aprender das saídas do próprio cliente seria
circular — o número teria saído daqui.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from math import ceil
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.crawlers.propor import hash_proposta
from app.modules.fiscal.infrastructure.matrizes_models import MatrizMva
from app.modules.fiscal.infrastructure.models import Nota, NotaItem
from app.modules.fiscal.infrastructure.propostas_models import (
    ACAO_INSERIR,
    STATUS_APROVADA,
    MatrizProposta,
)
from app.shared.domain.uf import CURINGA_UF
from app.shared.domain.value_objects import only_digits

#: Fonte PRÓPRIA e distinta das dos crawlers. É de propósito: a carga inicial
#: (`crawlers/workers.py::_carga_inicial`) chama `aprovar_lote(fonte=...)` e
#: aprova em massa tudo o que veio daquela fonte. Compartilhar a fonte com um
#: crawler faria a carga inicial aprovar MVA APRENDIDA sem nenhum curador ver.
FONTE_APRENDIDA = "notas-do-escritorio"

#: Quantos fornecedores distintos precisam convergir. Parâmetro (não constante
#: mágica): escritório com carteira pequena pode querer 2, um grande, 5.
MIN_FORNECEDORES = 3

#: Dois valores dentro desta distância são "o mesmo número" (arredondamento do
#: emitente). Ponto percentual, não fração.
TOLERANCIA_PONTOS = Decimal("0.01")

#: A partir de quantos fornecedores um valor CONCORRENTE já estraga o consenso.
APOIO_RELEVANTE = 2

#: Quantos CNPJs vão na evidência (o resto vira contagem).
AMOSTRA_CNPJ = 10

#: modBCST 4 = base por Margem de Valor Agregado (o único que declara pMVAST).
MOD_BC_ST_MVA = 4

#: CRT do emitente que NÃO ajusta a MVA (Simples Nacional e MEI).
CRT_SIMPLES = ("1", "4")

STATUS_PROPOR = "PROPOR"
STATUS_AMBIGUO = "AMBIGUO"
STATUS_SEM_CONSENSO = "SEM_CONSENSO"
STATUS_JA_COBERTO = "JA_COBERTO"


def _candidatos_ncm(ncm: str) -> list[str]:
    """NCM do mais específico ao mais geral (8→6→4) — o mesmo fallback que o
    motor usa para achar a MVA. Sem ele, uma linha curada em 4 dígitos passaria
    despercebida e o robô proporia uma margem concorrente para 8."""
    n = only_digits(ncm)
    vistos: list[str] = []
    for c in (n, n[:6], n[:4]):
        if c and c not in vistos:
            vistos.append(c)
    return vistos


def _primeiro_do_mes(iso: str | None) -> date:
    """Data de início de vigência sugerida: 1º dia do mês da nota mais antiga
    do grupo. É derivação MECÂNICA da data que já está na nota (o mesmo que o
    crawler de MG faz quando o anexo não publica a data por item) — não é
    afirmação de quando a norma passou a valer; quem sabe isso é o curador."""
    try:
        d = date.fromisoformat((iso or "")[:10])
    except ValueError:
        d = date.today()
    return d.replace(day=1)


@dataclass(slots=True)
class _Valor:
    """Um valor de MVA declarado e quem o declarou, dentro de uma chave."""

    mva: Decimal
    fornecedores: set[str] = field(default_factory=set)
    notas: int = 0
    itens: int = 0
    valor: float = 0.0
    emissao_min: str = ""
    emissao_max: str = ""

    def somar(self, cnpj: str, linha) -> None:
        self.fornecedores.add(cnpj)
        self.notas += int(linha["notas"] or 0)
        self.itens += int(linha["itens"] or 0)
        self.valor += float(linha["valor"] or 0)
        self._periodo(linha["emissao_min"] or "", linha["emissao_max"] or "")

    def _periodo(self, emin: str, emax: str) -> None:
        if emin:
            self.emissao_min = min(self.emissao_min, emin) if self.emissao_min else emin
        if emax:
            self.emissao_max = max(self.emissao_max, emax)

    def resumo(self, escolhido: bool) -> dict:
        return {
            "mva": str(self.mva),
            "fornecedores": len(self.fornecedores),
            "notas": self.notas,
            "itens": self.itens,
            "valor": round(self.valor, 2),
            "escolhido": escolhido,
        }


def _agrupar_por_valor(valores: list[_Valor], tolerancia: Decimal) -> list[_Valor]:
    """Junta valores a menos de `tolerancia` de distância — 41,99 e 42,00 são o
    mesmo número arredondado de dois jeitos. O representante do grupo é o valor
    com MAIS fornecedores; no empate, o MENOR (margem menor = ST menor: o
    palpite conservador é o que não infla cobrança)."""
    ordenados = sorted(valores, key=lambda v: v.mva)
    grupos: list[list[_Valor]] = []
    for v in ordenados:
        if grupos and v.mva - grupos[-1][-1].mva <= tolerancia:
            grupos[-1].append(v)
        else:
            grupos.append([v])

    fundidos: list[_Valor] = []
    for grupo in grupos:
        lider = max(grupo, key=lambda v: (len(v.fornecedores), -v.mva))
        alvo = _Valor(mva=lider.mva)
        for v in grupo:
            alvo.fornecedores |= v.fornecedores
            alvo.notas += v.notas
            alvo.itens += v.itens
            alvo.valor += v.valor
            alvo._periodo(v.emissao_min, v.emissao_max)
        fundidos.append(alvo)
    return fundidos


async def _linhas_elegiveis(
    session: AsyncSession, empresa_id, uf, ano, mes
) -> list[dict]:
    """Uma consulta: itens com margem declarada, por (chave × fornecedor × valor).

    O filtro é a regra de elegibilidade inteira — o que sai daqui já é MVA
    ORIGINAL por lei (interna ou emitente do Simples)."""
    n, it = Nota, NotaItem
    stmt = (
        select(
            it.ncm.label("ncm"),
            it.cest.label("cest"),
            n.uf_emit.label("uf_origem"),
            n.uf_dest.label("uf_destino"),
            n.cnpj_emit.label("cnpj"),
            it.p_mva_st.label("mva"),
            func.count(it.id).label("itens"),
            func.count(func.distinct(it.nota_id)).label("notas"),
            func.coalesce(func.sum(it.valor_produto), 0).label("valor"),
            func.min(n.data_emissao).label("emissao_min"),
            func.max(n.data_emissao).label("emissao_max"),
            func.min(it.descricao).label("descricao"),
        )
        .join(n, it.nota_id == n.id)
        .where(
            # Só ENTRADA: a margem tem de ser declaração de um terceiro.
            n.fluxo == "entrada",
            n.status == "ativa",
            it.mod_bc_st == MOD_BC_ST_MVA,
            it.p_mva_st > 0,
            it.ncm.isnot(None), it.ncm != "",
            n.uf_dest.isnot(None), n.uf_dest != "",
            n.uf_emit.isnot(None), n.uf_emit != "",
            n.cnpj_emit.isnot(None), n.cnpj_emit != "",
            # O CORAÇÃO da regra: interna (ajuste impossível) OU emitente do
            # Simples (não ajusta). Fora disso o pMVAST pode ser a AJUSTADA.
            or_(n.uf_emit == n.uf_dest, n.crt_emit.in_(CRT_SIMPLES)),
        )
        .group_by(it.ncm, it.cest, n.uf_emit, n.uf_dest, n.cnpj_emit, it.p_mva_st)
    )
    if empresa_id:
        stmt = stmt.where(n.empresa_id == empresa_id)
    if uf:
        stmt = stmt.where(n.uf_dest == uf.upper())
    if ano:
        stmt = stmt.where(n.ano == ano)
    if mes:
        stmt = stmt.where(n.mes == mes)
    return [dict(r) for r in (await session.execute(stmt)).mappings().all()]


async def _mapa_mva_vigente(session: AsyncSession, ufs: set[str]) -> dict:
    """(UF destino, NCM, CEST) → [(início, fim, UF origem)] das linhas da matriz."""
    if not ufs:
        return {}
    rows = (await session.execute(
        select(MatrizMva).where(MatrizMva.uf_destino.in_(ufs))
    )).scalars()
    mapa: dict[tuple[str, str, str], list[tuple[date, date | None, str]]] = {}
    for r in rows:
        mapa.setdefault((r.uf_destino, r.ncm, r.cest), []).append(
            (r.data_inicio_vigencia, r.data_fim_vigencia, (r.uf_origem or "").strip().upper())
        )
    return mapa


def _ja_coberto(mapa: dict, *, uf_destino: str, ncm: str, cest: str,
                uf_origem: str, desde: date) -> bool:
    """Existe linha na matriz valendo para a chave de `desde` em diante?

    Espelha a busca do motor (`_MvaSnapshot.buscar`): NCM 8→6→4, origem EXATA
    ou curinga `*`, CEST igual — e, quando o item veio SEM CEST, qualquer CEST
    do mesmo NCM (é o fallback que o motor faz). Linha encerrada ANTES de
    `desde` não conta: é história, não curadoria vigente. A janela começa na
    vigência que seria proposta, então proposta que passaria aqui também não
    esbarra na trava de sobreposição do ADR-0002 na hora de aprovar."""
    for c in _candidatos_ncm(ncm):
        chaves = (
            [(uf_destino, c, cest)] if cest
            else [k for k in mapa if k[0] == uf_destino and k[1] == c]
        )
        for chave in chaves:
            for _inicio, fim, origem in mapa.get(chave, ()):
                if (fim is None or fim >= desde) and origem in (uf_origem, CURINGA_UF):
                    return True
    return False


def _evidencia(
    *, escolhido: _Valor, distribuicao: list[_Valor], min_fornecedores: int,
    interna: bool, vigencia: date,
) -> dict:
    """O "por que estamos sugerindo isto" que o curador lê na fila.

    Dado aprendido não tem norma — sem a contagem de fornecedores, o período e
    os CNPJs, aprovar seria assinar um número no escuro."""
    cnpjs = sorted(escolhido.fornecedores)
    return {
        "origem": FONTE_APRENDIDA,
        "metodo": "pMVAST declarado nas NF-e de entrada",
        "por_que_e_original": (
            "operação interna (UF do emitente = UF do destinatário): a MVA "
            "ajustada não existe nesse caso"
            if interna else
            "emitente do Simples Nacional (CRT 1/4): não ajusta a MVA "
            "(Convênio ICMS 142/2018)"
        ),
        "mva": str(escolhido.mva),
        "fornecedores": len(cnpjs),
        "fornecedores_minimo": min_fornecedores,
        "notas": escolhido.notas,
        "itens": escolhido.itens,
        "valor_itens": round(escolhido.valor, 2),
        "periodo": {
            "primeira_emissao": escolhido.emissao_min or None,
            "ultima_emissao": escolhido.emissao_max or None,
        },
        "vigencia_sugerida": vigencia.isoformat(),
        "vigencia_criterio": "1º dia do mês da nota mais antiga do grupo",
        "distribuicao": [
            v.resumo(v.mva == escolhido.mva)
            for v in sorted(distribuicao, key=lambda v: len(v.fornecedores), reverse=True)
        ],
        "cnpjs_amostra": cnpjs[:AMOSTRA_CNPJ],
        "cnpjs_total": len(cnpjs),
        "sem_base_legal": (
            "Número aprendido das notas, sem norma que o publique. Preencha a "
            "base legal ao aprovar — é ela que sai nas cartas."
        ),
    }


async def levantar_mva_aprendida(
    session: AsyncSession,
    *,
    empresa_id: UUID | None = None,
    uf: str | None = None,
    ano: str | None = None,
    mes: str | None = None,
    min_fornecedores: int = MIN_FORNECEDORES,
    tolerancia: Decimal = TOLERANCIA_PONTOS,
) -> tuple[list[dict], dict]:
    """Núcleo compartilhado pela prévia e pela geração: candidatos + resumo.

    Devolve só os grupos que PASSAM em todas as regras (já com payload,
    evidência e hash prontos) e um resumo contando também os que caíram —
    por ambiguidade, por falta de consenso ou por já haver curadoria."""
    min_fornecedores = max(1, int(min_fornecedores))
    linhas = await _linhas_elegiveis(session, empresa_id, uf, ano, mes)

    # (ncm, cest, origem, destino) → valor declarado → quem declarou.
    grupos: dict[tuple[str, str, str, str], dict[Decimal, _Valor]] = {}
    descricoes: dict[tuple[str, str, str, str], str] = {}
    itens_elegiveis = notas_elegiveis = 0
    for linha in linhas:
        chave = (
            only_digits(linha["ncm"] or ""),
            only_digits(linha["cest"] or ""),
            (linha["uf_origem"] or "").strip().upper(),
            (linha["uf_destino"] or "").strip().upper(),
        )
        if not chave[0] or not chave[2] or not chave[3]:
            continue
        mva = Decimal(str(linha["mva"]))
        valores = grupos.setdefault(chave, {})
        valores.setdefault(mva, _Valor(mva=mva)).somar(linha["cnpj"], linha)
        descricoes.setdefault(chave, (linha["descricao"] or "")[:120])
        itens_elegiveis += int(linha["itens"] or 0)
        notas_elegiveis += int(linha["notas"] or 0)

    mapa_matriz = await _mapa_mva_vigente(session, {c[3] for c in grupos})
    ja_na_fila = set((await session.execute(
        select(MatrizProposta.hash_proposta).where(
            MatrizProposta.tipo_matriz == "mva",
            MatrizProposta.status != STATUS_APROVADA,
        )
    )).scalars())

    candidatos: list[dict] = []
    contagem = {STATUS_PROPOR: 0, STATUS_AMBIGUO: 0,
                STATUS_SEM_CONSENSO: 0, STATUS_JA_COBERTO: 0}
    for chave, valores in grupos.items():
        ncm, cest, uf_origem, uf_destino = chave
        distribuicao = _agrupar_por_valor(list(valores.values()), tolerancia)
        escolhido = max(distribuicao, key=lambda v: (len(v.fornecedores), -v.mva))
        vigencia = _primeiro_do_mes(escolhido.emissao_min)

        if _ja_coberto(mapa_matriz, uf_destino=uf_destino, ncm=ncm, cest=cest,
                       uf_origem=uf_origem, desde=vigencia):
            contagem[STATUS_JA_COBERTO] += 1
            continue
        relevantes = [v for v in distribuicao if len(v.fornecedores) >= APOIO_RELEVANTE]
        if len(relevantes) > 1:
            # Dois números com apoio real: os fornecedores discordam entre si.
            # Fail-closed — o sistema não escolhe o vencedor de uma disputa.
            contagem[STATUS_AMBIGUO] += 1
            continue
        if len(escolhido.fornecedores) < min_fornecedores:
            contagem[STATUS_SEM_CONSENSO] += 1
            continue

        payload = {
            "ncm": ncm,
            "cest": cest,
            "uf_origem": uf_origem,
            "uf_destino": uf_destino,
            "mva_original": str(escolhido.mva),
            # VAZIO de propósito: `base_legal` sai nas CARTAS. Escrever
            # "aprendido das notas" ali seria citar como norma o que não é.
            "base_legal": None,
            "data_inicio_vigencia": vigencia.isoformat(),
            "data_fim_vigencia": None,
        }
        interna = uf_origem == uf_destino
        candidatos.append({
            "ncm": ncm,
            "cest": cest,
            "uf_origem": uf_origem,
            "uf_destino": uf_destino,
            "descricao": descricoes.get(chave, ""),
            "mva_original": str(escolhido.mva),
            "fornecedores": len(escolhido.fornecedores),
            "notas": escolhido.notas,
            "itens": escolhido.itens,
            "valor": round(escolhido.valor, 2),
            "data_inicio_vigencia": vigencia.isoformat(),
            "primeira_emissao": escolhido.emissao_min or None,
            "ultima_emissao": escolhido.emissao_max or None,
            "elegibilidade": "interna" if interna else "simples",
            "chave_resumo": (
                f"{uf_origem} → {uf_destino} · NCM {ncm} · CEST {cest or '—'}"
            )[:200],
            "payload": payload,
            "hash_proposta": hash_proposta("mva", payload),
            "evidencia": _evidencia(
                escolhido=escolhido, distribuicao=distribuicao,
                min_fornecedores=min_fornecedores, interna=interna, vigencia=vigencia,
            ),
        })
        contagem[STATUS_PROPOR] += 1

    for c in candidatos:
        c["ja_na_fila"] = c["hash_proposta"] in ja_na_fila
    # Impacto: primeiro o que mais pesa em dinheiro, depois em itens — a mesma
    # ordem das outras filas de curadoria (cobertura, lacunas de MVA).
    candidatos.sort(key=lambda c: (c["valor"], c["itens"]), reverse=True)

    resumo = {
        "fonte": FONTE_APRENDIDA,
        "min_fornecedores": min_fornecedores,
        "tolerancia": str(tolerancia),
        "grupos_avaliados": len(grupos),
        "itens_elegiveis": itens_elegiveis,
        "notas_elegiveis": notas_elegiveis,
        "propor": contagem[STATUS_PROPOR],
        "ambiguos": contagem[STATUS_AMBIGUO],
        "sem_consenso": contagem[STATUS_SEM_CONSENSO],
        "ja_cobertos": contagem[STATUS_JA_COBERTO],
        "ja_na_fila": sum(1 for c in candidatos if c["ja_na_fila"]),
        "valor": round(sum(c["valor"] for c in candidatos), 2),
    }
    return candidatos, resumo


async def previa_mva_aprendida(
    session: AsyncSession,
    *,
    empresa_id: UUID | None = None,
    uf: str | None = None,
    ano: str | None = None,
    mes: str | None = None,
    min_fornecedores: int = MIN_FORNECEDORES,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """O que SERIA proposto — sem gravar nada. Serve a tela antes do botão."""
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    candidatos, resumo = await levantar_mva_aprendida(
        session, empresa_id=empresa_id, uf=uf, ano=ano, mes=mes,
        min_fornecedores=min_fornecedores,
    )
    total = len(candidatos)
    inicio = (page - 1) * page_size
    return {
        "resumo": resumo,
        "propostas": candidatos[inicio:inicio + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": ceil(total / page_size),
    }


async def gerar_propostas_mva_aprendida(
    session: AsyncSession,
    *,
    empresa_id: UUID | None = None,
    uf: str | None = None,
    ano: str | None = None,
    mes: str | None = None,
    min_fornecedores: int = MIN_FORNECEDORES,
) -> dict:
    """Grava os candidatos na FILA de revisão (nada entra na matriz).

    Proposta idêntica já pendente — ou já rejeitada — não volta: a supressão
    por hash da fila vale igual para o dado aprendido. Rejeitar uma sugestão
    dessas vale para sempre, sem ruído na próxima rodada."""
    candidatos, resumo = await levantar_mva_aprendida(
        session, empresa_id=empresa_id, uf=uf, ano=ano, mes=mes,
        min_fornecedores=min_fornecedores,
    )
    criadas = suprimidas = 0
    vistos: set[str] = set()
    for c in candidatos:
        if c["ja_na_fila"] or c["hash_proposta"] in vistos:
            suprimidas += 1
            continue
        vistos.add(c["hash_proposta"])
        session.add(MatrizProposta(
            tipo_matriz="mva",
            acao=ACAO_INSERIR,
            chave_resumo=c["chave_resumo"],
            payload=c["payload"],
            fonte=FONTE_APRENDIDA,
            hash_proposta=c["hash_proposta"],
            evidencia=c["evidencia"],
        ))
        criadas += 1
    await session.flush()
    return {
        **resumo,
        "criadas": criadas,
        "suprimidas": suprimidas,
        "descartadas_ambiguidade": resumo["ambiguos"],
        "puladas_ja_na_matriz": resumo["ja_cobertos"],
    }
