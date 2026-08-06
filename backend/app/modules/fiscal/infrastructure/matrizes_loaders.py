"""Loaders assíncronos das matrizes (padrão "carrega-então-calcula", ADR/Fase 1).

A camada async vai ao banco UMA vez por matriz (sem N+1), filtra pela vigência
(ADR-0002) e hidrata repositórios SÍNCRONOS que implementam os ports do motor.
O domínio (`StAuditEngine`) permanece puro, síncrono e cego ao banco.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import ClassVar
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.domain.st.enums import Regime
from app.modules.fiscal.domain.st.model import ItemFiscal, Operacao
from app.modules.fiscal.domain.st.ports import AliquotaUf, MvaInfo
from app.modules.fiscal.infrastructure.matrizes_models import (
    MatrizAliquota,
    MatrizEnquadramentoSt,
    MatrizFcp,
    MatrizMva,
    MatrizProtocoloSt,
)
from app.modules.fiscal.infrastructure.models import ExcecaoEnquadramentoStProduto
from app.modules.fiscal.infrastructure.vigencia import filtrar_vigencia
from app.shared.domain.uf import CURINGA_UF
from app.shared.domain.value_objects import only_digits


def _uf(valor: str | None) -> str:
    """Sigla em caixa alta preservando o curinga '*' (regra de qualquer origem)."""
    bruto = (valor or "").strip()
    return CURINGA_UF if bruto == CURINGA_UF else bruto.upper()


def _candidatos_ncm(ncm: str) -> list[str]:
    """NCM do mais específico ao mais geral (8→6→4), sem duplicar."""
    n = only_digits(ncm)
    vistos: list[str] = []
    for c in (n, n[:6], n[:4]):
        if c and c not in vistos:
            vistos.append(c)
    return vistos


# --------------------------------------------------------------------------- #
# Repositórios SÍNCRONOS hidratados (implementam os Protocols do domínio)
# --------------------------------------------------------------------------- #
@dataclass(frozen=True, slots=True)
class _MvaSnapshot:
    """MVA vigente por NCM+CEST+UF ORIGEM→DESTINO.

    Precedência: o NCM é o laço EXTERNO (8→6→4) e, dentro dele, a origem EXATA
    vence o curinga `"*"`. Assim uma regra genérica ("vale para qualquer
    remetente") nunca sequestra o par curado UF→UF, e um NCM de 8 dígitos com
    regra curinga ganha de um NCM de 6 dígitos com origem específica — o
    produto é mais determinante que o remetente.
    """

    # (ncm, cest, uf_origem, uf_destino) -> (MVA, id da linha, base legal)
    dados: dict[tuple[str, str, str, str], tuple[Decimal, int, str | None]]

    def buscar(
        self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date
    ) -> MvaInfo | None:
        cest_l = only_digits(cest)
        orig, dest = _uf(uf_orig), _uf(uf_dest)
        origens = (orig,) if orig == CURINGA_UF else (orig, CURINGA_UF)
        for c in _candidatos_ncm(ncm):
            for o in origens:
                par = self.dados.get((c, cest_l, o, dest))
                if par is not None:
                    mva, linha_id, base_legal = par
                    return MvaInfo(mva_original=mva, ncm_casado=c,
                                   matriz_id=linha_id, base_legal=base_legal,
                                   uf_origem_casada=o)
        if not cest_l:
            # XML sem a tag CEST (típico de emitente que nem tratou o item como
            # ST): casa pelo NCM. MVA única no NCM → usa; MVAs distintas por
            # CEST → ambíguo, fail-closed (None trava com o erro de MVA).
            # A origem exata é resolvida ANTES do curinga também aqui — e um
            # empate ambíguo na origem exata trava, não escorrega pro curinga.
            for c in _candidatos_ncm(ncm):
                for o in origens:
                    pares = [
                        v for (n, _ce, uo, ud), v in self.dados.items()
                        if n == c and uo == o and ud == dest
                    ]
                    if pares:
                        mvas = {p[0] for p in pares}
                        if len(mvas) == 1:
                            mva, linha_id, base_legal = pares[0]
                            return MvaInfo(mva_original=mva, ncm_casado=c,
                                           matriz_id=linha_id, base_legal=base_legal,
                                           uf_origem_casada=o)
                        return None
        return None


@dataclass(frozen=True, slots=True)
class _EnquadramentoSnapshot:
    """Portão NCM×CEST×UF + as Exceções do Item da empresa.

    A exceção é chaveada por (CNPJ do fornecedor, cProd) porque o código do
    produto é do FORNECEDOR: dois fornecedores usam códigos diferentes para o
    mesmo produto e — pior — o MESMO código para produtos distintos. Chaveada
    só pelo código, a exceção do fornecedor A desligava o ST do item homônimo
    do fornecedor B (imposto fora da conta sem ninguém ver).

    Precedência igual à da UF de origem na MVA: o CNPJ EXATO vence e o genérico
    `""` (vale para qualquer fornecedor, valor do legado migrado) só responde
    quando não há regra do fornecedor. Uma regra genérica nunca sequestra a
    regra específica.
    """

    dados: dict[tuple[str, str, str], Regime]    # (ncm, cest, uf) -> regime
    # (cnpj_fornecedor, cProd) -> regime; cnpj "" = qualquer fornecedor
    excecoes: dict[tuple[str, str], Regime] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normaliza a chave na CONSTRUÇÃO (e não só na busca) para que o
        # casamento independa de quem montou o snapshot: cadastro formatado
        # ("11.111.111/0001-11") tem de bater com o CNPJ limpo do XML, e o
        # cProd é comparado sem espaços e em caixa alta.
        normalizado = {
            (only_digits(cnpj), (codigo or "").strip().upper()): regime
            for (cnpj, codigo), regime in self.excecoes.items()
        }
        if normalizado != self.excecoes:
            object.__setattr__(self, "excecoes", normalizado)

    def _excecao(self, codigo_produto: str, cnpj_emitente: str = "") -> Regime | None:
        codigo = (codigo_produto or "").strip().upper()
        if not codigo:
            return None
        # Normaliza dos DOIS lados: o XML traz o documento com pontuação em
        # alguns casos e o cadastro pode ter sido salvo formatado.
        cnpj = only_digits(cnpj_emitente)
        candidatos = ((cnpj, codigo), ("", codigo)) if cnpj else (("", codigo),)
        for chave in candidatos:
            regime = self.excecoes.get(chave)
            if regime is not None:
                return regime
        return None

    def fonte_regime(self, codigo_produto: str, cnpj_emitente: str = "") -> str:
        excecao = self._excecao(codigo_produto, cnpj_emitente)
        return "EXCECAO_ITEM" if excecao is not None else "MATRIZ"

    def regime(
        self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date,
        codigo_produto: str = "", cnpj_emitente: str = "",
    ) -> Regime:
        excecao = self._excecao(codigo_produto, cnpj_emitente)
        if excecao is not None:
            return excecao
        cest_l, uf = only_digits(cest), uf_dest.upper()
        for c in _candidatos_ncm(ncm):
            reg = self.dados.get((c, cest_l, uf))
            if reg is not None:
                return reg
        if not cest_l:
            # XML sem CEST: o cadastro NCM×CEST ainda vale — casa pelo NCM.
            # Regime único entre os CEST do NCM → esse regime; conflito → abre o
            # portão (ST) e a checagem de MVA a jusante decide com transparência.
            for c in _candidatos_ncm(ncm):
                regimes = {r for (n, _ce, u), r in self.dados.items() if n == c and u == uf}
                if regimes:
                    return regimes.pop() if len(regimes) == 1 else Regime.ST
        return Regime.TN   # não enquadrado = tributação normal

    def explicar_tn(
        self, ncm: str, cest: str, uf_dest: str,
        codigo_produto: str = "", cnpj_emitente: str = "",
    ) -> str | None:
        """Por que o item caiu em TN? None = TN explícito por cadastro (legítimo,
        fora do motor por decisão). String = falta/conflito de cadastro — vira
        NAO_AUDITAVEL acionável (com código de erro, reprocessável)."""
        if self._excecao(codigo_produto, cnpj_emitente) == Regime.TN:
            return None
        cest_l, uf = only_digits(cest), uf_dest.upper()
        candidatos = _candidatos_ncm(ncm)
        for c in candidatos:
            if (c, cest_l, uf) in self.dados:
                return None
        cests_ncm = sorted({ce for (n, ce, u) in self.dados if u == uf and n in candidatos})
        if not cests_ncm:
            alvo = f"NCM {only_digits(ncm) or '—'}" + (f" · CEST {cest_l}" if cest_l else "")
            return (f"{alvo} sem enquadramento cadastrado para {uf} — cadastre ST ou TN "
                    "nas Matrizes Fiscais (Enquadramento) para o motor auditar.")
        if cest_l:
            return (f"CEST {cest_l} do XML não casa com o cadastro do NCM em {uf} "
                    f"(CEST cadastrado: {', '.join(cests_ncm)}) — confira o item ou "
                    "complete o cadastro para auditar.")
        return None   # sem CEST no XML e NCM cadastrado: o fallback já respondeu


@dataclass(frozen=True, slots=True)
class _FcpSnapshot:
    dados: dict[tuple[str, str], Decimal]        # (uf, ncm|'GERAL') -> FCP-ST

    def aliquota_st(self, ncm: str, uf_dest: str, data: date) -> Decimal:
        uf, n = uf_dest.upper(), only_digits(ncm)
        for chave in (n, n[:4], "GERAL"):
            aliq = self.dados.get((uf, chave))
            if aliq is not None:
                return aliq
        return Decimal("0")


@dataclass(frozen=True, slots=True)
class _ProtocoloSnapshot:
    """Tri-state do par UF origem→destino da nota (o loader já filtrou o par):
    - `curado` False (nenhuma linha na matriz, qualquer situação) → None: o par
      nunca foi avaliado; o motor trava com ERRO_PROTOCOLO_NAO_AVALIADO em vez
      de decidir errado (fail-closed, ADR-0002);
    - acordo ATIVO vigente casando o NCM (linha sem NCM = par inteiro; com NCM,
      fallback 8→6→4) → True (remetente é o substituto);
    - curado sem acordo aplicável (denunciado/vencido/outro NCM) → False
      (antecipação do destinatário)."""

    curado: bool
    ncms_ativos: frozenset[str]                  # "*" = acordo do par inteiro
    fonte: ClassVar[str] = "matriz"              # resposta consultada (vai à memória)

    def tem_protocolo(
        self, uf_orig: str, uf_dest: str, data: date, ncm: str = ""
    ) -> bool | None:
        if not self.curado:
            return None
        if "*" in self.ncms_ativos:
            return True
        return any(c in self.ncms_ativos for c in _candidatos_ncm(ncm))


@dataclass(frozen=True, slots=True)
class _AliquotaSnapshot:
    dados: dict[str, AliquotaUf]                 # UF -> alíquota vigente na data

    def buscar(self, uf_dest: str, data: date) -> AliquotaUf | None:
        return self.dados.get(uf_dest.upper())


@dataclass(frozen=True, slots=True)
class MatrizesHidratadas:
    """O que o orquestrador injeta no StAuditEngine."""

    mva: _MvaSnapshot
    enquadramento: _EnquadramentoSnapshot
    fcp: _FcpSnapshot
    protocolo: _ProtocoloSnapshot
    aliquota: _AliquotaSnapshot


# --------------------------------------------------------------------------- #
# Loader async
# --------------------------------------------------------------------------- #
class MatrizesLoader:
    """Carrega em lote as matrizes vigentes para os itens de uma nota."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def hidratar(
        self, itens: list[ItemFiscal], operacao: Operacao,
        empresa_id: UUID | None = None,
    ) -> MatrizesHidratadas:
        uf, data = operacao.uf_dest.upper(), operacao.data
        uf_orig = operacao.uf_emit.upper()
        ncms: set[str] = set()
        cests: set[str] = set()
        for it in itens:
            ncms.update(_candidatos_ncm(it.ncm))
            cests.add(only_digits(it.cest))

        return MatrizesHidratadas(
            mva=await self._mva(uf_orig, uf, ncms, cests, data),
            enquadramento=await self._enquadramento(
                uf, ncms, cests, data, empresa_id, itens
            ),
            fcp=await self._fcp(uf, ncms, data),
            protocolo=await self._protocolo(operacao.uf_emit.upper(), uf, data),
            aliquota=await self._aliquota(uf, data),
        )

    async def _mva(self, uf_orig, uf, ncms, cests, data) -> _MvaSnapshot:
        # Sem filtro por CEST: o XML pode vir sem a tag (o snapshot resolve o
        # fallback por NCM) — poucas linhas por NCM, custo irrelevante.
        # A origem entra na query com o curinga junto: o snapshot é quem decide
        # a precedência (exata > "*") dentro de cada nível de NCM.
        stmt = filtrar_vigencia(
            select(MatrizMva).where(
                MatrizMva.uf_destino == uf,
                MatrizMva.uf_origem.in_({uf_orig, CURINGA_UF}),
                MatrizMva.ncm.in_(ncms),
            ),
            MatrizMva,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _MvaSnapshot({
            (r.ncm, r.cest, _uf(r.uf_origem), r.uf_destino):
                (r.mva_original, r.id, r.base_legal)
            for r in rows
        })

    async def _enquadramento(
        self, uf, ncms, cests, data,
        empresa_id: UUID | None = None,
        itens: list[ItemFiscal] | None = None,
    ) -> _EnquadramentoSnapshot:
        # Sem filtro por CEST (mesma razão do _mva): o cadastro NCM×CEST precisa
        # ser visível mesmo quando a nota veio sem a tag CEST.
        stmt = filtrar_vigencia(
            select(MatrizEnquadramentoSt).where(
                MatrizEnquadramentoSt.uf_destino == uf,
                MatrizEnquadramentoSt.ncm.in_(ncms),
            ),
            MatrizEnquadramentoSt,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        excecoes: dict[tuple[str, str], Regime] = {}
        codigos = {
            (it.codigo_produto or "").strip().upper()
            for it in (itens or []) if (it.codigo_produto or "").strip()
        }
        if empresa_id is not None and codigos:
            stmt_exc = select(ExcecaoEnquadramentoStProduto).where(
                ExcecaoEnquadramentoStProduto.empresa_id == empresa_id,
                ExcecaoEnquadramentoStProduto.codigo_produto.in_(codigos),
                ExcecaoEnquadramentoStProduto.ativo.is_(True),
                ExcecaoEnquadramentoStProduto.data_inicio_vigencia <= data,
                (
                    ExcecaoEnquadramentoStProduto.data_fim_vigencia.is_(None)
                    | (ExcecaoEnquadramentoStProduto.data_fim_vigencia >= data)
                ),
            )
            exc_rows = (await self.session.execute(stmt_exc)).scalars().all()
            # Chave composta (fornecedor, código): sem o CNPJ a regra de um
            # fornecedor vazaria para o item homônimo de outro. O CNPJ é
            # normalizado aqui porque o cadastro pode ter vindo formatado —
            # o snapshot compara sempre só dígitos.
            excecoes = {
                (only_digits(r.cnpj_fornecedor), r.codigo_produto.strip().upper()):
                    (Regime.TN if r.tributado_icms else Regime.ST)
                for r in exc_rows
            }
        return _EnquadramentoSnapshot(
            {(r.ncm, r.cest, r.uf_destino): Regime(r.regime) for r in rows},
            excecoes,
        )

    async def _fcp(self, uf, ncms, data) -> _FcpSnapshot:
        stmt = filtrar_vigencia(
            select(MatrizFcp).where(
                MatrizFcp.uf_destino == uf,
                MatrizFcp.ncm.in_(set(ncms) | {"GERAL"}),
            ),
            MatrizFcp,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _FcpSnapshot({(r.uf_destino, r.ncm): r.aliq_fcp_st for r in rows})

    async def _protocolo(self, uf_orig: str, uf_dest: str, data) -> _ProtocoloSnapshot:
        # Operação interna (mesma UF) não tem protocolo a checar — o engine nem
        # consulta; `curado` True evita falso "não avaliado" em qualquer borda.
        if uf_orig == uf_dest:
            return _ProtocoloSnapshot(curado=True, ncms_ativos=frozenset())
        par = [
            MatrizProtocoloSt.uf_origem == uf_orig,
            MatrizProtocoloSt.uf_destino == uf_dest,
        ]
        # Curadoria: existe QUALQUER linha do par (mesmo vencida/denunciada)?
        curado = bool(await self.session.scalar(
            select(func.count()).select_from(MatrizProtocoloSt).where(*par)
        ))
        stmt = filtrar_vigencia(
            select(MatrizProtocoloSt).where(*par, MatrizProtocoloSt.situacao == "ATIVO"),
            MatrizProtocoloSt,
            data,
        )
        rows = (await self.session.execute(stmt)).scalars().all()
        return _ProtocoloSnapshot(
            curado=curado,
            ncms_ativos=frozenset(
                only_digits(r.ncm) if r.ncm else "*" for r in rows
            ),
        )

    async def _aliquota(self, uf: str, data) -> _AliquotaSnapshot:
        stmt = (
            filtrar_vigencia(
                select(MatrizAliquota).where(MatrizAliquota.uf_destino == uf),
                MatrizAliquota,
                data,
            )
            # Desempate (ADR-0002): se houver sobreposição indevida, vence a
            # vigência mais recente — a validação de carga é quem impede o caso.
            .order_by(MatrizAliquota.data_inicio_vigencia.desc())
            .limit(1)
        )
        row = (await self.session.execute(stmt)).scalars().first()
        if row is None:
            return _AliquotaSnapshot({})
        return _AliquotaSnapshot({row.uf_destino: AliquotaUf(
            modal=row.aliq_modal, fcp_integrado=row.aliq_fcp_integrado,
            matriz_id=row.id, base_legal=row.base_legal,
        )})
