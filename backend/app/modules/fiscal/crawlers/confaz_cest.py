"""Extrator da relação NCM×CEST do CONFAZ (Convênio ICMS 142/2018).

A fonte oficial publica os Anexos em planilha/PDF; o portal de Dados Abertos
espelha em CSV (`;` como separador). O `parse` é tolerante a ruído (linhas
incompletas, máscara em NCM/CEST) — a planilha pública é irregular.

NOTA DE GO-LIVE: confirmar a URL estável do CSV publicado antes de ligar o job
em produção (a constante abaixo é o ponto único de configuração da fonte).
"""
from __future__ import annotations

import csv
import io

from app.shared.domain.value_objects import only_digits

from .base import CestRecord, Extractor


class ConfazCestExtractor(Extractor):
    fonte = "CONFAZ — Convênio ICMS 142/2018 (relação NCM×CEST)"

    # Ponto único de configuração da origem (CSV `;`: CEST;NCM;DESCRICAO;SEGMENTO).
    URL = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/cv142_18-anexos.csv"

    def __init__(self, url: str | None = None):
        self._url = url or self.URL

    def fetch(self) -> bytes:
        return self._http_get(self._url)

    def parse(self, raw: bytes) -> list[CestRecord]:
        texto = raw.decode("utf-8-sig", errors="replace")
        leitor = csv.reader(io.StringIO(texto), delimiter=";")
        registros: list[CestRecord] = []
        for i, linha in enumerate(leitor):
            if i == 0 or len(linha) < 2:        # cabeçalho ou linha-lixo
                continue
            cest, ncm = only_digits(linha[0]), only_digits(linha[1])
            if len(cest) != 7 or not ncm:       # CEST tem 7 dígitos; NCM obrigatório
                continue
            registros.append(CestRecord(
                cest=cest,
                ncm=ncm,
                descricao=(linha[2].strip() if len(linha) > 2 else ""),
                segmento=(linha[3].strip() if len(linha) > 3 else None),
            ))
        return registros
