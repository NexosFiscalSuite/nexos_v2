"""Implementações em memória dos ports — seed dos exemplos do Vault + uso em teste.

Substituíveis por repositórios SQLAlchemy sem tocar no domínio (é o ponto de
ter os ports). A higienização de NCM/CEST (remoção de máscara) e o fallback por
hierarquia de NCM vivem aqui, como manda a MATRIZ_MVA_Por_Segmento (Seção 2).
"""
from __future__ import annotations

import re
from datetime import date
from decimal import Decimal

from .enums import Regime
from .money import ZERO, D
from .ports import MvaInfo


def _limpar(codigo: str) -> str:
    """Remove qualquer caractere não numérico (8512.20.11 -> 85122011)."""
    return re.sub(r"\D", "", codigo or "")


class MvaEmMemoria:
    """MvaRepository seed. Chave (ncm_limpo, cest_limpo, uf); fallback 8→6→4."""

    def __init__(self, dados: dict[tuple[str, str, str], str] | None = None):
        # (ncm, cest, uf) -> MVA original (%). Exemplos da MATRIZ_MVA_Por_Segmento.
        base = {
            ("85122011", "0100100", "MG"): "40.00",
            ("8512", "0100100", "SP"): "36.50",
            ("33049910", "2001600", "RJ"): "52.00",
        }
        if dados:
            base.update(dados)
        self._dados = {(_limpar(n), _limpar(c), uf.upper()): D(v) for (n, c, uf), v in base.items()}

    def buscar(self, ncm: str, cest: str, uf_dest: str, data: date) -> MvaInfo | None:
        ncm_l, cest_l, uf = _limpar(ncm), _limpar(cest), uf_dest.upper()
        for chave_ncm in (ncm_l, ncm_l[:6], ncm_l[:4]):
            mva = self._dados.get((chave_ncm, cest_l, uf))
            if mva is not None:
                return MvaInfo(mva_original=mva, ncm_casado=chave_ncm)
        return None


class EnquadramentoEmMemoria:
    """EnquadramentoRepository seed. Por padrão devolve ST; UFs/itens podem ser
    marcados como TN para exercitar o portão. Em produção, troca pela query da
    MATRIZ_NCM_Enquadramento_ST."""

    def __init__(
        self,
        tn: set[tuple[str, str, str]] | None = None,
        padrao: Regime = Regime.ST,
    ):
        self._tn = {(_limpar(n), _limpar(c), uf.upper()) for (n, c, uf) in (tn or set())}
        self._padrao = padrao

    def regime(
        self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date
    ) -> Regime:
        if (_limpar(ncm), _limpar(cest), uf_dest.upper()) in self._tn:
            return Regime.TN
        return self._padrao


class FcpEmMemoria:
    """FcpRepository seed. Chave (uf, ncm) com fallback 8→4→'GERAL'."""

    def __init__(self, dados: dict[tuple[str, str], str] | None = None):
        base = {
            ("MG", "2203"): "1.00",     # vigente atual (MATRIZ_FCP_Por_UF)
            ("RJ", "GERAL"): "2.00",
        }
        if dados:
            base.update(dados)
        self._dados = {
            (uf.upper(), ncm if ncm == "GERAL" else _limpar(ncm)): D(v)
            for (uf, ncm), v in base.items()
        }

    def aliquota_st(self, ncm: str, uf_dest: str, data: date) -> Decimal:
        ncm_l, uf = _limpar(ncm), uf_dest.upper()
        for chave in (ncm_l, ncm_l[:4], "GERAL"):
            aliq = self._dados.get((uf, chave))
            if aliq is not None:
                return aliq
        return ZERO


class ProtocoloEmMemoria:
    """ProtocoloRepository seed. Passe os pares (UF orig, UF dest) com acordo
    vigente; sem nenhum par, `padrao` decide (True = assume protocolo, replicando
    o comportamento histórico do motor; False = simula antecipação)."""

    fonte = "matriz"   # configurada explicitamente pelo teste = resposta consultada

    def __init__(self, pares: set[tuple[str, str]] | None = None, padrao: bool = True):
        self._pares = {(o.upper(), d.upper()) for (o, d) in (pares or set())}
        self._padrao = padrao

    def tem_protocolo(self, uf_orig: str, uf_dest: str, data: date) -> bool:
        if self._pares:
            return (uf_orig.upper(), uf_dest.upper()) in self._pares
        return self._padrao
