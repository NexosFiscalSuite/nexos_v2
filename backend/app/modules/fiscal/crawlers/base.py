"""Contrato base dos extratores de regra fiscal.

A separação fetch()/parse() é deliberada: `fetch` concentra TODO o I/O (HTTP,
arquivo) e `parse` é PURO (bytes → registros). Assim os testes exercitam o
parser com uma amostra fixa, sem rede, e a fonte pode trocar (CSV→PDF→API) sem
mexer no parsing nem na orquestração.
"""
from __future__ import annotations

import re
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from html.parser import HTMLParser

from app.shared.domain.value_objects import only_digits


@dataclass(frozen=True, slots=True)
class CestRecord:
    """Uma linha da relação NCM×CEST (Convênio ICMS 142/2018)."""

    cest: str
    ncm: str
    descricao: str = ""
    segmento: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractResult:
    fonte: str
    registros: list[CestRecord] = field(default_factory=list)


class TabelasHtml(HTMLParser):
    """Coleta toda <table> de uma página como linhas de células em texto plano.
    Serve a qualquer fonte oficial publicada em tabela HTML (CONFAZ, SEFAZ-MG)."""

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


def separar_ncms(celula: str) -> list[str]:
    """Célula NCM/SH pode listar vários códigos ('3815.12.10, 3815.12.90').
    Só 8/6/4 dígitos entram — é o que o fallback hierárquico da matriz lê;
    capítulos de 2 dígitos nunca casariam na busca e ficam de fora."""
    vistos: list[str] = []
    for token in re.split(r"[,;\s]+", celula):
        n = only_digits(token)
        if len(n) in (4, 6, 8) and n not in vistos:
            vistos.append(n)
    return vistos


def http_get(url: str, timeout: int = 30) -> bytes:
    """Download com User-Agent e timeout (boa cidadania com portais públicos).
    Módulo-nível para tasks que só monitoram (sem parse) usarem também."""
    req = urllib.request.Request(url, headers={"User-Agent": "NexosFiscalBot/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (URL fixa de portal oficial)
        return resp.read()


class Extractor(ABC):
    """Extrator de uma fonte oficial. Subclasses implementam fetch()+parse()."""

    fonte: str = "desconhecida"
    timeout: int = 30

    @abstractmethod
    def fetch(self) -> bytes:
        """Baixa o conteúdo bruto da fonte (todo o I/O vive aqui)."""

    @abstractmethod
    def parse(self, raw: bytes) -> list[CestRecord]:
        """Transforma o bruto em registros normalizados (função pura)."""

    def extract(self) -> ExtractResult:
        """Orquestra fetch→parse. Mantida fina de propósito (testável por partes)."""
        return ExtractResult(fonte=self.fonte, registros=self.parse(self.fetch()))

    def _http_get(self, url: str) -> bytes:
        return http_get(url, timeout=self.timeout)
