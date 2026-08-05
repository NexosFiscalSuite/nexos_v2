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
_COD_AMBITO = re.compile(r"\d{1,2}\.\d{1,2}")
# "Alagoas (Protocolo ICMS 103/12)" / "São Paulo (Convênio ICMS 52/17)"
_UF_ACORDO = re.compile(
    r"([A-Za-zÀ-ÿ ]+?)\s*\((Protocolo|Conv[êe]nio)\s+ICMS\s+n?º?\s*([\d.]+/\d{2,4})\)",
    re.IGNORECASE,
)
_EXCECAO = re.compile(r"Exce[çc]\w*:?\s*([^)]*)", re.IGNORECASE)

# Nome por extenso → sigla (como o Anexo VII escreve as UFs).
UF_SIGLAS = {
    "Acre": "AC", "Alagoas": "AL", "Amapá": "AP", "Amazonas": "AM",
    "Bahia": "BA", "Ceará": "CE", "Distrito Federal": "DF",
    "Espírito Santo": "ES", "Goiás": "GO", "Maranhão": "MA",
    "Mato Grosso": "MT", "Mato Grosso do Sul": "MS", "Minas Gerais": "MG",
    "Pará": "PA", "Paraíba": "PB", "Paraná": "PR", "Pernambuco": "PE",
    "Piauí": "PI", "Rio de Janeiro": "RJ", "Rio Grande do Norte": "RN",
    "Rio Grande do Sul": "RS", "Rondônia": "RO", "Roraima": "RR",
    "Santa Catarina": "SC", "São Paulo": "SP", "Sergipe": "SE",
    "Tocantins": "TO",
}


def _ufs_no_texto(trecho: str) -> list[str]:
    """Siglas das UFs citadas por extenso num trecho (mais longas primeiro,
    para 'Mato Grosso do Sul' não casar como 'Mato Grosso')."""
    achadas: list[str] = []
    resto = trecho
    for nome in sorted(UF_SIGLAS, key=len, reverse=True):
        if nome in resto:
            achadas.append(UF_SIGLAS[nome])
            resto = resto.replace(nome, " ")
    return achadas


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
    ambito: str = ""                      # célula bruta (ex.: "16.1 (Exceção: Rondônia)")
    ambitos: tuple[str, ...] = ()         # códigos citados (ex.: ("2.1", "2.2"))
    excecoes: tuple[str, ...] = ()        # siglas de UF excluídas do item


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
                celula_ambito = linha[idx + 3]
                m_exc = _EXCECAO.search(celula_ambito)
                excecoes = tuple(_ufs_no_texto(m_exc.group(1))) if m_exc else ()
                for ncm in separar_ncms(linha[idx + 1]):
                    registros.append(MvaRecord(
                        cest=cest, ncm=ncm, mva=mva,
                        descricao=linha[idx + 2], ambito=celula_ambito,
                        ambitos=tuple(_COD_AMBITO.findall(celula_ambito)),
                        excecoes=excecoes,
                    ))
        return registros

    def parse_ambitos(self, raw: bytes) -> dict[str, list[tuple[str, str]]]:
        """Legenda oficial do 'Âmbito de Aplicação': código → [(UF, acordo)].

        O próprio anexo define cada código, ex.: '2.1 Interno e nas seguintes
        unidades da Federação: Alagoas (Protocolo ICMS 103/12), …'. É a fonte
        da matriz de Protocolos com a base legal item a item. Códigos só
        internos ('Interno.') ou de inaplicabilidade viram lista vazia.
        Limitação documentada: notas de rodapé por item ('* Relativamente ao
        item…') não são interpretadas — a proposta carrega o código do âmbito
        e o curador confere na fonte."""
        texto = re.sub(r"<[^>]+>", "|", _decodificar(raw))
        texto = re.sub(r"\s+", " ", texto)

        # Início de cada definição: código seguido de Interno/Inaplicabilidade.
        inicios = [
            (m.start(), m.group(1))
            for m in re.finditer(r"(\d{1,2}\.\d{1,2})\s+(?:Interno|Inaplicabilidade)", texto)
        ]
        ambitos: dict[str, list[tuple[str, str]]] = {}
        for i, (pos, codigo) in enumerate(inicios):
            fim = inicios[i + 1][0] if i + 1 < len(inicios) else pos + 1500
            trecho = texto[pos:fim]
            pares: list[tuple[str, str]] = []
            for m in _UF_ACORDO.finditer(trecho):
                nome = m.group(1).strip(" ,;e|")
                # O nome da UF é o fim do trecho capturado (ex.: "e São Paulo").
                sigla = next(
                    (UF_SIGLAS[n] for n in sorted(UF_SIGLAS, key=len, reverse=True)
                     if nome.endswith(n)),
                    None,
                )
                if sigla is None:
                    continue
                tipo = "Protocolo" if m.group(2).lower().startswith("prot") else "Convênio"
                par = (sigla, f"{tipo} ICMS {m.group(3)}")
                if par not in pares:
                    pares.append(par)
            # Mesmo código pode reaparecer (páginas concatenadas): une sem duplicar.
            destino = ambitos.setdefault(codigo, [])
            for par in pares:
                if par not in destino:
                    destino.append(par)
        return ambitos
