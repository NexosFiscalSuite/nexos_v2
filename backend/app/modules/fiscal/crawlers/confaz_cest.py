"""Extrator da relação NCM×CEST do CONFAZ (Convênio ICMS 142/2018).

A fonte é a PÁGINA OFICIAL CONSOLIDADA do convênio: os Anexos II a XXVI são
tabelas HTML de 4 colunas (ITEM | CEST | NCM/SH | DESCRIÇÃO) e o Anexo I é a
tabela de segmentos (ITEM | NOME | CÓDIGO). Não existe CSV oficial publicado —
a URL de dados abertos imaginada no go-live retornava 404; o HTML consolidado
é a fonte estável. O `parse` é tolerante a ruído (cabeçalhos, máscara em
NCM/CEST, células com vários NCM) — página governamental é irregular.
"""
from __future__ import annotations

import re
from html.parser import HTMLParser

from app.shared.domain.value_objects import only_digits

from .base import CestRecord, Extractor


class _TabelasHtml(HTMLParser):
    """Coleta toda <table> da página como linhas de células em texto plano."""

    def __init__(self) -> None:
        super().__init__()
        self.tabelas: list[list[list[str]]] = []
        self._linha: list[str] | None = None
        self._celula: list[str] | None = None

    def handle_starttag(self, tag: str, attrs) -> None:  # noqa: ANN001 — assinatura da stdlib
        if tag == "table":
            self.tabelas.append([])
        elif tag == "tr":
            self._linha = []
        elif tag in ("td", "th"):
            self._celula = []

    def handle_endtag(self, tag: str) -> None:
        if tag in ("td", "th") and self._celula is not None and self._linha is not None:
            self._linha.append(" ".join("".join(self._celula).split()))
            self._celula = None
        elif tag == "tr" and self._linha is not None:
            if self.tabelas:
                self.tabelas[-1].append(self._linha)
            self._linha = None

    def handle_data(self, data: str) -> None:
        if self._celula is not None:
            self._celula.append(data)


class ConfazCestExtractor(Extractor):
    fonte = "CONFAZ — Convênio ICMS 142/2018 (página oficial consolidada)"

    # Ponto único de configuração da origem (HTML consolidado com os Anexos).
    URL = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"

    def __init__(self, url: str | None = None):
        self.url = url or self.URL   # público: vai ao FonteSnapshot (trilha)

    def fetch(self) -> bytes:
        return self._http_get(self.url)

    def parse(self, raw: bytes) -> list[CestRecord]:
        coletor = _TabelasHtml()
        coletor.feed(raw.decode("utf-8", errors="replace"))

        # Anexo I (3 colunas): código do segmento → nome. Os dois primeiros
        # dígitos do CEST são o segmento, então o mapa legenda os demais anexos.
        segmentos: dict[str, str] = {}
        registros: list[CestRecord] = []
        for tabela in coletor.tabelas:
            for linha in tabela:
                if len(linha) == 3:
                    codigo = only_digits(linha[2])
                    if len(codigo) == 2 and linha[1]:
                        segmentos[codigo] = linha[1]
                    continue
                if len(linha) < 4:
                    continue
                cest = only_digits(linha[1])
                if len(cest) != 7:          # cabeçalho ou linha-lixo
                    continue
                for ncm in self._ncms(linha[2]):
                    registros.append(CestRecord(
                        cest=cest, ncm=ncm, descricao=linha[3],
                        segmento=segmentos.get(cest[:2]),
                    ))
        return registros

    @staticmethod
    def _ncms(celula: str) -> list[str]:
        """A célula NCM/SH pode listar vários códigos ('3815.12.10, 3815.12.90').
        Só 8/6/4 dígitos entram — é o que o fallback hierárquico da matriz lê;
        capítulos de 2 dígitos nunca casariam na busca e ficam de fora."""
        vistos: list[str] = []
        for token in re.split(r"[,;\s]+", celula):
            n = only_digits(token)
            if len(n) in (4, 6, 8) and n not in vistos:
                vistos.append(n)
        return vistos
