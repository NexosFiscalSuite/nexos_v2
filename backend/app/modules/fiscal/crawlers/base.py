"""Contrato base dos extratores de regra fiscal.

A separação fetch()/parse() é deliberada: `fetch` concentra TODO o I/O (HTTP,
arquivo) e `parse` é PURO (bytes → registros). Assim os testes exercitam o
parser com uma amostra fixa, sem rede, e a fonte pode trocar (CSV→PDF→API) sem
mexer no parsing nem na orquestração.
"""
from __future__ import annotations

import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


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
        """Download com User-Agent e timeout (boa cidadania com portais públicos)."""
        req = urllib.request.Request(url, headers={"User-Agent": "NexosFiscalBot/1.0"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 (URL fixa de portal oficial)
            return resp.read()
