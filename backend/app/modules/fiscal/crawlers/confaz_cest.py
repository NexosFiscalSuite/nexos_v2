"""Extrator da relação NCM×CEST do CONFAZ (Convênio ICMS 142/2018).

A fonte é a PÁGINA OFICIAL CONSOLIDADA do convênio: os Anexos II a XXVI são
tabelas HTML de 4 colunas (ITEM | CEST | NCM/SH | DESCRIÇÃO) e o Anexo I é a
tabela de segmentos (ITEM | NOME | CÓDIGO). Não existe CSV oficial publicado —
a URL de dados abertos imaginada no go-live retornava 404; o HTML consolidado
é a fonte estável. O `parse` é tolerante a ruído (cabeçalhos, máscara em
NCM/CEST, células com vários NCM) — página governamental é irregular.
"""
from __future__ import annotations

from app.shared.domain.value_objects import only_digits

from .base import CestRecord, Extractor, TabelasHtml, separar_ncms


class ConfazCestExtractor(Extractor):
    fonte = "CONFAZ — Convênio ICMS 142/2018 (página oficial consolidada)"

    # Ponto único de configuração da origem (HTML consolidado com os Anexos).
    URL = "https://www.confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18"

    def __init__(self, url: str | None = None):
        self.url = url or self.URL   # público: vai ao FonteSnapshot (trilha)

    def fetch(self) -> bytes:
        return self._http_get(self.url)

    def parse(self, raw: bytes) -> list[CestRecord]:
        coletor = TabelasHtml()
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
                for ncm in separar_ncms(linha[2]):
                    registros.append(CestRecord(
                        cest=cest, ncm=ncm, descricao=linha[3],
                        segmento=segmentos.get(cest[:2]),
                    ))
        return registros
