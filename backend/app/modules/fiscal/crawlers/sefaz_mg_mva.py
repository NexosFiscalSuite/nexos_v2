"""Extrator das MVAs de MG — Anexo VII do RICMS/2023 (Parte 2), SEFAZ-MG.

A fonte oficial publica o anexo em 7 páginas HTML; as tabelas de itens da
Parte 2 têm colunas fixas: ITEM | CEST | NBM/SH | DESCRIÇÃO | ÂMBITO DE
APLICAÇÃO | MVA (%). Desde a Portaria SUTRI 1.518/2025 (01/11/2025) o PMPF
foi extinto em MG — a MVA do anexo é a base da ST. O parse é tolerante:
linha sem CEST de 7 dígitos ou sem MVA numérica fica de fora (itens ainda
sem margem publicada não viram palpite — fail-closed).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from app.shared.domain.value_objects import only_digits

from .base import Extractor, TabelasHtml, separar_ncms

_NUMERO = re.compile(r"\d+(?:[.,]\d+)?")
_CEST = re.compile(r"\d{2}\.\d{3}\.\d{2}")


def _decodificar(raw: bytes) -> str:
    """As páginas da SEFAZ-MG são latin-1; tenta UTF-8 e cai no latin-1."""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


@dataclass(frozen=True, slots=True)
class MvaRecord:
    """Uma linha de MVA do Anexo VII (Parte 2)."""

    cest: str
    ncm: str
    mva: Decimal
    descricao: str = ""
    ambito: str = ""


def _mva_da_celula(celula: str) -> Decimal | None:
    """'40', '33,08', '40 (a)' → Decimal; vazio/'-'/texto → None (sem margem)."""
    m = _NUMERO.search(celula or "")
    if not m:
        return None
    try:
        valor = Decimal(m.group(0).replace(",", "."))
    except InvalidOperation:
        return None
    return valor if Decimal("0") < valor <= Decimal("999") else None


class SefazMgMvaExtractor(Extractor):
    fonte = "SEFAZ-MG — RICMS/2023, Anexo VII, Parte 2 (MVA da ST)"

    # O anexo consolidado é servido em 7 páginas; o fetch concatena todas —
    # as tabelas de itens (6 colunas) são filtradas no parse.
    PAGINAS = tuple(
        f"https://www.fazenda.mg.gov.br/empresas/legislacao_tributaria/ricms_2023_seco/anexovii2023_{n}.html"
        for n in range(1, 8)
    )

    def __init__(self, paginas: tuple[str, ...] | None = None):
        self.paginas = paginas or self.PAGINAS
        self.url = self.paginas[0].rsplit("_", 1)[0] + " (7 páginas)"

    def fetch(self) -> bytes:
        return b"\n".join(self._http_get(u) for u in self.paginas)

    def parse(self, raw: bytes) -> list[MvaRecord]:
        coletor = TabelasHtml()
        coletor.feed(_decodificar(raw))

        # As linhas de item variam de largura (célula de layout vazia à frente,
        # colunas extras em alguns capítulos): âncora é a célula do CEST no
        # formato ##.###.## — NCM, descrição, âmbito e MVA vêm em sequência.
        registros: list[MvaRecord] = []
        for tabela in coletor.tabelas:
            for linha in tabela:
                idx = next(
                    (i for i, c in enumerate(linha) if _CEST.fullmatch((c or "").strip())),
                    None,
                )
                if idx is None or len(linha) < idx + 5:
                    continue                     # artigos, cabeçalhos, layout
                mva = _mva_da_celula(linha[idx + 4])
                if mva is None:
                    continue                     # item sem margem publicada
                cest = only_digits(linha[idx])
                for ncm in separar_ncms(linha[idx + 1]):
                    registros.append(MvaRecord(
                        cest=cest, ncm=ncm, mva=mva,
                        descricao=linha[idx + 2], ambito=linha[idx + 3],
                    ))
        return registros
