"""Frescor da base de matrizes (Fase 2 da automação).

Responde "quando alguém confirmou a base pela última vez?" — o carimbo que a
carta de ST imprime no aviso de legislação vigente ("base de matrizes
atualizada em DD/MM/AAAA") e o painel de Saúde detalha por matriz: quanto da
base VIGENTE foi verificado nos últimos 90 dias e o que está envelhecendo.

O painel também varre as UFs FORA DO PADRÃO (ver `_ufs_invalidas`): linhas
antigas, gravadas quando o campo era texto livre, que o motor nunca encontra.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, or_, select
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
from app.shared.domain.uf import CURINGA_UF, UFS, normalizar_uf

# Mesmas chaves do registry das matrizes (bulk/CRUD) — a tela traduz o rótulo.
_MATRIZES = (
    ("enquadramento", MatrizEnquadramentoSt),
    ("mva", MatrizMva),
    ("protocolos", MatrizProtocoloSt),
    ("aliquotas", MatrizAliquota),
    ("fcp", MatrizFcp),
)

JANELA_FRESCOR_DIAS = 90

#: Campos de UF de cada matriz e se o curinga "*" é legítimo naquele campo.
#: Só a ORIGEM da MVA aceita o curinga ("vale para qualquer remetente"): na
#: matriz de Protocolos a busca compara a origem por IGUALDADE com a UF da
#: nota, então um "*" ali é justamente uma linha inencontrável. `ncm = "GERAL"`
#: (FCP e Alíquota) não entra nesta varredura — não é UF, é a convenção da
#: regra do estado inteiro, e acusá-la seria falso positivo.
_CAMPOS_UF: dict[str, tuple[tuple[str, bool], ...]] = {
    "enquadramento": (("uf_destino", False),),
    "mva": (("uf_origem", True), ("uf_destino", False)),
    "protocolos": (("uf_origem", False), ("uf_destino", False)),
    "aliquotas": (("uf_destino", False),),
    "fcp": (("uf_destino", False),),
}

#: Teto de itens da amostra devolvida à tela (o total continua exato).
LIMITE_AMOSTRA_UF = 20


def _fora_do_padrao(valor: str | None, permite_curinga: bool) -> bool:
    """A UF gravada é diferente da sigla canônica que o motor procura?

    Comparação ESTRITA com as 27 siglas: o motor casa a linha com a sigla de 2
    letras em caixa alta vinda do XML, então "mg", " MG " e "Minas Gerais" são
    tão invisíveis quanto "XX" — ainda que as duas primeiras sejam óbvias para
    um humano. O curinga "*" só passa onde ele é regra de verdade.
    """
    bruto = (valor or "").strip()
    if permite_curinga and bruto == CURINGA_UF:
        return False
    return valor not in UFS


async def _ufs_invalidas(session: AsyncSession, hoje: date) -> dict:
    """Linhas VIGENTES com UF fora do padrão, por matriz, com amostra.

    Até a virada para dropdown os campos de UF eram texto livre; o que ficou no
    banco continua lá. Uma linha assim é INVISÍVEL para o motor (a busca compara
    com a sigla de 2 letras do XML): a regra aparece na tela, parece cadastrada
    e nunca é aplicada — erro silencioso com cara de resolvido. Este bloco é o
    radar que as encontra, e a tela oferece a correção quando `normalizar_uf`
    consegue resolver ("Minas Gerais" → "MG"); `sugestao` None = precisa de um
    humano decidir (ex.: "XX").

    Só linhas vigentes: regra encerrada não é aplicada por ninguém mesmo.
    """
    por_matriz: dict[str, int] = {}
    amostra: list[dict] = []
    total = 0
    for tipo, modelo in _MATRIZES:
        campos = _CAMPOS_UF[tipo]
        # Um SELECT DISTINCT por campo (cardinalidade de UF é baixíssima) diz
        # QUAIS valores estão fora do padrão antes de tocar nas linhas.
        suspeitos: dict[str, dict[str | None, str | None]] = {}
        for campo, permite_curinga in campos:
            coluna = getattr(modelo, campo)
            valores = (await session.execute(
                filtrar_vigencia(select(coluna).distinct(), modelo, hoje)
            )).scalars().all()
            fora = {
                v: normalizar_uf(v, permitir_curinga=permite_curinga)
                for v in valores if _fora_do_padrao(v, permite_curinga)
            }
            if fora:
                suspeitos[campo] = fora
        if not suspeitos:
            por_matriz[tipo] = 0
            continue

        condicoes = []
        for campo, fora in suspeitos.items():
            coluna = getattr(modelo, campo)
            concretos = [v for v in fora if v is not None]
            if concretos:
                condicoes.append(coluna.in_(concretos))
            if None in fora:      # NULL não casa com IN — precisa do IS NULL
                condicoes.append(coluna.is_(None))
        alvo = or_(*condicoes)

        linhas = await session.scalar(select(func.count()).select_from(
            filtrar_vigencia(select(modelo.id).where(alvo), modelo, hoje).subquery()
        )) or 0
        por_matriz[tipo] = linhas
        total += linhas

        if len(amostra) < LIMITE_AMOSTRA_UF:
            nomes = [campo for campo, _ in campos]
            rows = (await session.execute(
                filtrar_vigencia(
                    select(modelo.id, *(getattr(modelo, c) for c in nomes)).where(alvo),
                    modelo, hoje,
                ).order_by(modelo.id).limit(LIMITE_AMOSTRA_UF - len(amostra))
            )).all()
            for linha in rows:
                # Uma linha pode ter os DOIS campos tortos: cada um vira um item
                # (a tela corrige campo a campo), mas a contagem é de linhas.
                for campo, valor in zip(nomes, linha[1:], strict=True):
                    fora = suspeitos.get(campo)
                    if fora is not None and valor in fora:
                        amostra.append({
                            "id": linha[0],
                            "matriz": tipo,
                            "campo": campo,
                            "valor": valor,
                            "sugestao": fora[valor],
                        })
    return {
        "total": total,
        "por_matriz": por_matriz,
        "amostra": amostra,
        "limite_amostra": LIMITE_AMOSTRA_UF,
    }


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
    envelhece ninguém.

    Traz junto o bloco `ufs_invalidas`: as linhas com UF fora do padrão, que
    existem no banco e o motor nunca encontra."""
    agora = datetime.now(UTC)
    corte = agora - timedelta(days=JANELA_FRESCOR_DIAS)
    hoje = agora.date()

    ufs = await _ufs_invalidas(session, hoje)
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
            # Duplicado de propósito em `ufs_invalidas.por_matriz`: a tela lista
            # as matrizes por esta chave e precisa do selo na própria linha.
            "ufs_invalidas": ufs["por_matriz"].get(tipo, 0),
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
            "ufs_invalidas": ufs["total"],
        },
        "matrizes": matrizes,
        "ufs_invalidas": ufs,
    }
