"""Alíquotas de ICMS: interestadual em fórmula + referência intra em código.

A INTERESTADUAL (4/7/12) é lei estável e determinística — Resoluções do Senado
22/1989 (geografia) e 13/2012 (importados) — e vive em código (`AliquotaResolver`).

A INTRAESTADUAL (modal + FCP integrado) muda por lei estadual: em produção ela
vem da MATRIZ_ALIQUOTA no banco, com vigência (ADR-0002), hidratada pelo
MatrizesLoader. A tabela abaixo é a implementação de REFERÊNCIA do port
`AliquotaRepository` (testes e dev sem banco) — nunca a fonte de verdade de
produção.

Dois conceitos distintos e propositais (ver `AliquotaUf`):
  - `modal`  → usada no DÉBITO do ST (pICMSST). NÃO inclui o FCP, que roda em
    trilha paralela (Seção 7); incluí-lo contaria o FCP de RJ/AL/SE em dobro.
  - `efetiva` (modal + FCP integrado) → usada SÓ no denominador do ajuste de
    MVA (R-07), onde a carga efetiva impede inflar a MVA Ajustada.

⚠️ Valores conferidos em 12/06/2026. Alíquotas específicas por produto
(supérfluos, cesta básica) entram pela matriz no banco — ver MATRIZ_NCM_Aliquotas.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .money import D
from .ports import AliquotaUf

# UF -> (alíquota modal, FCP integrado à modal). Fonte: Seção 1.
_MODAL_E_FCP: dict[str, tuple[str, str]] = {
    "AC": ("19", "0"), "AL": ("20.5", "1"), "AM": ("20", "0"), "AP": ("18", "0"),
    "BA": ("20.5", "0"), "CE": ("20", "0"), "DF": ("20", "0"), "ES": ("17", "0"),
    "GO": ("19", "0"), "MA": ("23", "0"), "MG": ("18", "0"), "MS": ("17", "0"),
    "MT": ("17", "0"), "PA": ("19", "0"), "PB": ("20", "0"), "PE": ("20.5", "0"),
    "PI": ("22.5", "0"), "PR": ("19.5", "0"), "RJ": ("20", "2"), "RN": ("20", "0"),
    "RO": ("19.5", "0"), "RR": ("20", "0"), "RS": ("17", "0"), "SC": ("17", "0"),
    "SE": ("19", "1"), "SP": ("18", "0"), "TO": ("20", "0"),
}

# Lei 9.776/2025 (AL): modal 19% até 31/03/2026, 20,5% a partir de 01/04/2026.
# Única virada intra-ano replicada aqui, para a referência não mentir sobre
# notas anteriores a abril/2026. O histórico completo é papel da matriz no banco.
_AL_VIRADA = date(2026, 4, 1)
_AL_ANTES = ("19", "1")

# Regra dos 7%: origem Sul/Sudeste (exceto ES) -> destino N/NE/CO/ES.
_ORIGENS_7 = frozenset({"SP", "MG", "RJ", "PR", "RS", "SC"})
_DESTINOS_7 = frozenset({
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MS",
    "MT", "PA", "PB", "PE", "PI", "RN", "RO", "RR", "SE", "TO",
})

# Origem da mercadoria que dispara a Resolução Senado 13/2012 (4%).
_ORIGENS_IMPORTADAS = frozenset({"1", "2", "3", "8"})


class AliquotaResolver:
    """Determina a Alq_Inter (4/7/12) — geografia + origem da mercadoria."""

    def alq_inter(
        self, uf_orig: str, uf_dest: str, orig: str, data: date | None = None
    ) -> Decimal:
        # Exceção soberana: importado (orig 1/2/3/8) força 4%, ignora geografia.
        if (orig or "").strip() in _ORIGENS_IMPORTADAS:
            return D("4")
        if uf_orig.upper() in _ORIGENS_7 and uf_dest.upper() in _DESTINOS_7:
            return D("7")
        return D("12")


class AliquotasReferencia:
    """`AliquotaRepository` de referência: tabela em código, para testes e dev.

    Em produção o motor recebe o snapshot do banco (MatrizesLoader). UF sem
    linha (ex.: 'EX', exterior) devolve None — o motor classifica o item como
    não auditável em vez de estourar o lote.
    """

    def buscar(self, uf_dest: str, data: date) -> AliquotaUf | None:
        uf = (uf_dest or "").strip().upper()
        par = _MODAL_E_FCP.get(uf)
        if par is None:
            return None
        if uf == "AL" and data < _AL_VIRADA:
            par = _AL_ANTES
        modal, fcp = par
        return AliquotaUf(modal=D(modal), fcp_integrado=D(fcp))
