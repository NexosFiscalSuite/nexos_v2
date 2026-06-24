"""Resolver concreto de alíquotas de ICMS (MATRIZ_ICMS_Aliquotas).

Diferente das MVAs/FCP (que vivem no banco com vigência), as alíquotas modais
das 27 UFs e a regra interestadual (4/7/12) estão 100% especificadas no Vault,
então são implementadas em código.

Dois conceitos distintos e propositais:
  - `alq_intra_modal`  → usada no DÉBITO do ST (pICMSST). NÃO inclui o FCP, que
    roda em trilha paralela (Seção 7); incluí-lo contaria o FCP de RJ/AL/SE em
    dobro.
  - `alq_intra_efetiva` (modal + FCP integrado) → usada SÓ no denominador do
    ajuste de MVA (R-07), onde a carga efetiva impede inflar a MVA Ajustada.

⚠️ Valores conferidos em 12/06/2026. Dupla vigência intra-ano (ex.: AL a partir
de 01/04/2026) e alíquotas específicas por produto (supérfluos, cesta básica)
entram com a tabela temporal no banco — ver MATRIZ_NCM_Aliquotas.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from .money import D

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

# Regra dos 7%: origem Sul/Sudeste (exceto ES) -> destino N/NE/CO/ES.
_ORIGENS_7 = frozenset({"SP", "MG", "RJ", "PR", "RS", "SC"})
_DESTINOS_7 = frozenset({
    "AC", "AL", "AM", "AP", "BA", "CE", "DF", "ES", "GO", "MA", "MS",
    "MT", "PA", "PB", "PE", "PI", "RN", "RO", "RR", "SE", "TO",
})

# Origem da mercadoria que dispara a Resolução Senado 13/2012 (4%).
_ORIGENS_IMPORTADAS = frozenset({"1", "2", "3", "8"})


class AliquotaResolver:
    """Determina Alq_Intra (modal e efetiva) e Alq_Inter (4/7/12)."""

    def _modal_fcp(self, uf_dest: str) -> tuple[Decimal, Decimal]:
        try:
            modal, fcp = _MODAL_E_FCP[uf_dest.upper()]
        except KeyError as e:
            raise ValueError(f"UF de destino sem alíquota cadastrada: {uf_dest!r}") from e
        return D(modal), D(fcp)

    def alq_intra_modal(self, uf_dest: str, data: date | None = None) -> Decimal:
        """Alíquota modal para o débito do ST (sem FCP integrado)."""
        return self._modal_fcp(uf_dest)[0]

    def alq_intra_efetiva(self, uf_dest: str, data: date | None = None) -> Decimal:
        """Carga efetiva (modal + FCP integrado) — só no denominador da MVA Ajustada."""
        modal, fcp = self._modal_fcp(uf_dest)
        return modal + fcp

    def alq_inter(
        self, uf_orig: str, uf_dest: str, orig: str, data: date | None = None
    ) -> Decimal:
        # Exceção soberana: importado (orig 1/2/3/8) força 4%, ignora geografia.
        if (orig or "").strip() in _ORIGENS_IMPORTADAS:
            return D("4")
        if uf_orig.upper() in _ORIGENS_7 and uf_dest.upper() in _DESTINOS_7:
            return D("7")
        return D("12")
