"""Extrator das MVAs de MG — Anexo VII do RICMS/2023 (Parte 2), SEFAZ-MG.

A fonte oficial publica o anexo em 7 páginas HTML; as tabelas de itens da
Parte 2 têm colunas fixas: ITEM | CEST | NBM/SH | DESCRIÇÃO | ÂMBITO DE
APLICAÇÃO | MVA (%). Desde a Portaria SUTRI 1.518/2025 (01/11/2025) o PMPF
foi extinto em MG — a MVA do anexo é a base da ST. O parse é tolerante:
linha sem CEST de 7 dígitos ou sem MVA numérica fica de fora (itens ainda
sem margem publicada não viram palpite — fail-closed).

A coluna ÂMBITO é lida duas vezes, para dois fins diferentes:
`parse_ambitos` (código → UFs com acordo) alimenta a matriz de Protocolos, e
`resolver_origens` usa o mesmo âmbito — mais `parse_internos` — para dizer em
que operações a margem vale, ou seja, a UF de ORIGEM de cada linha de MVA.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from app.shared.domain.uf import CURINGA_UF, UF_NOMES
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

#: Nome por extenso → sigla (como o Anexo VII escreve as UFs). Derivado da
#: fonte única de UF do sistema — nunca uma segunda tabela de siglas.
UF_SIGLAS = {nome: sigla for sigla, nome in UF_NOMES.items()}

#: UF de destino do anexo: é o RICMS de MG.
UF_ANEXO = "MG"


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
    # UFs de ORIGEM em que a margem se aplica, resolvidas pela legenda de
    # âmbito (`resolver_origens`). Vazio = âmbito não resolvido → a proposta
    # sai com CURINGA_UF ("qualquer origem"), como antes desta fase.
    ufs_origem: tuple[str, ...] = ()

    def origens(self) -> tuple[str, ...]:
        """Origens EXPLÍCITAS da linha: as resolvidas pelo âmbito, ou o curinga
        quando o âmbito não foi legível.

        A linha "regra geral" (curinga com a mesma margem, para entradas de UF
        fora do âmbito) NÃO sai daqui: ela depende de olhar o anexo inteiro
        (o par NCM+CEST pode ter mais de uma margem publicada) e por isso é
        montada em `propor.propor_mva`."""
        return self.ufs_origem or (CURINGA_UF,)


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

    @staticmethod
    def _texto_plano(raw: bytes) -> str:
        """Página sem tags e sem quebra de linha — a legenda é lida por regex."""
        texto = re.sub(r"<[^>]+>", "|", _decodificar(raw))
        return re.sub(r"\s+", " ", texto)

    def parse_internos(self, raw: bytes) -> frozenset[str]:
        """Códigos de âmbito cuja definição começa por 'Interno' — ou seja, a ST
        (e a margem publicada) também vale na operação DENTRO de MG.

        Existe separado de `parse_ambitos` porque aquele responde "quais UFs de
        FORA": o âmbito 'Interno.' puro tem lista vazia lá, mas aqui aparece —
        é o que dá origem à linha de MVA interna (MG→MG)."""
        texto = self._texto_plano(raw)
        return frozenset(
            m.group(1) for m in re.finditer(r"(\d{1,2}\.\d{1,2})\s+Interno", texto)
        )

    def parse_ambitos(self, raw: bytes) -> dict[str, list[tuple[str, str]]]:
        """Legenda oficial do 'Âmbito de Aplicação': código → [(UF, acordo)].

        O próprio anexo define cada código, ex.: '2.1 Interno e nas seguintes
        unidades da Federação: Alagoas (Protocolo ICMS 103/12), …'. É a fonte
        da matriz de Protocolos com a base legal item a item. Códigos só
        internos ('Interno.') ou de inaplicabilidade viram lista vazia.
        Limitação documentada: notas de rodapé por item ('* Relativamente ao
        item…') não são interpretadas — a proposta carrega o código do âmbito
        e o curador confere na fonte."""
        texto = self._texto_plano(raw)

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


def resolver_origens(
    registros: list[MvaRecord],
    ambitos: dict[str, list[tuple[str, str]]],
    internos: frozenset[str] | set[str] = frozenset(),
    *,
    uf_destino: str = UF_ANEXO,
) -> list[MvaRecord]:
    """Carimba em cada linha as UFs de ORIGEM que o âmbito cita explicitamente.

    A coluna "Âmbito de Aplicação" é o que o anexo diz sobre o ALCANCE do
    acordo do item: "Interno e nas seguintes unidades da Federação: …".
    Traduzindo para a matriz: a MVA daquela linha vale na operação interna
    (origem = MG) e nas entradas vindas das UFs listadas.

    ATENÇÃO — leitura revista em 06/08/2026: até então este docstring dizia
    "e em mais nenhuma", e o crawler passou a propor SÓ as linhas por origem.
    Efeito em produção: item com âmbito curto (ex.: SP/RJ/PR) ficava sem
    margem nenhuma para fornecedor de outro estado, e o motor caía na base
    "valor da operação" — ST a menos. O âmbito diz quem é o SUBSTITUTO (com
    que estados MG tem acordo), não se EXISTE margem: entrada de UF sem
    acordo continua gerando ST como antecipação do destinatário, e a
    antecipação usa a margem interna do produto, que é a mesma publicada.
    Por isso `propor_mva` acrescenta, além destas linhas específicas, uma
    linha CURINGA_UF com a mesma margem (a rede de baixo; a origem exata
    continua vencendo no motor). Aqui nada muda: esta função segue
    respondendo apenas "quem o âmbito cita" — a decisão de estender é do
    `propor_mva`, que enxerga o anexo inteiro e precisa dessa visão para não
    inventar uma "margem geral" quando o par tem margens divergentes.

    Sem inventar nada:
    - código de âmbito desconhecido (legenda não lida) → origem fica vazia e a
      proposta sai com CURINGA_UF, exatamente como antes desta fase;
    - "Exceção: <UF>" na célula do item remove aquela origem;
    - código só de inaplicabilidade não acrescenta origem.
    """
    resolvidos: list[MvaRecord] = []
    for r in registros:
        origens: list[str] = []
        for codigo in r.ambitos:
            if codigo in internos and uf_destino not in origens:
                origens.append(uf_destino)          # operação interna do estado
            for uf_origem, _acordo in ambitos.get(codigo, ()):
                if uf_origem not in origens:
                    origens.append(uf_origem)
        origens = [uf for uf in origens if uf not in r.excecoes]
        resolvidos.append(
            r if not origens else replace(r, ufs_origem=tuple(origens))
        )
    return resolvidos
