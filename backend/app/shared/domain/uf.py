"""UF brasileira — a fonte ÚNICA de siglas do sistema.

Havia duas tabelas de UF espalhadas (import de empresas e crawler do Anexo VII
de MG) e vários campos de texto livre. Digitação livre em UF é veneno para as
matrizes: "Minas Gerais", "mg " ou "MGG" viram linha que o motor NUNCA encontra
na busca (que compara com a sigla de 2 letras vinda do XML) — a regra existe no
banco e o cálculo sai errado do mesmo jeito.

`normalizar_uf` aceita o que o humano digita (minúscula, com acento, nome por
extenso) e devolve a sigla canônica, ou None quando não é UF — nunca "conserta"
por aproximação.
"""
from __future__ import annotations

import unicodedata

__all__ = [
    "CURINGA_UF",
    "UFS",
    "UF_NOMES",
    "normalizar_uf",
]

#: Curinga de origem: a regra vale para QUALQUER UF de origem.
CURINGA_UF = "*"

#: Sigla → nome por extenso. Ordem alfabética por sigla (é a ordem dos dropdowns).
UF_NOMES: dict[str, str] = {
    "AC": "Acre",
    "AL": "Alagoas",
    "AM": "Amazonas",
    "AP": "Amapá",
    "BA": "Bahia",
    "CE": "Ceará",
    "DF": "Distrito Federal",
    "ES": "Espírito Santo",
    "GO": "Goiás",
    "MA": "Maranhão",
    "MG": "Minas Gerais",
    "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso",
    "PA": "Pará",
    "PB": "Paraíba",
    "PE": "Pernambuco",
    "PI": "Piauí",
    "PR": "Paraná",
    "RJ": "Rio de Janeiro",
    "RN": "Rio Grande do Norte",
    "RO": "Rondônia",
    "RR": "Roraima",
    "RS": "Rio Grande do Sul",
    "SC": "Santa Catarina",
    "SE": "Sergipe",
    "SP": "São Paulo",
    "TO": "Tocantins",
}

#: Conjunto das 27 siglas válidas (26 estados + DF).
UFS: frozenset[str] = frozenset(UF_NOMES)


def _chave(texto: str) -> str:
    """Minúscula, sem acento e sem espaço duplicado — para casar 'Goiás'/'goias'."""
    sem_acento = "".join(
        ch for ch in unicodedata.normalize("NFD", texto)
        if unicodedata.category(ch) != "Mn"
    )
    return " ".join(sem_acento.lower().split())


_POR_EXTENSO: dict[str, str] = {_chave(nome): sigla for sigla, nome in UF_NOMES.items()}


def normalizar_uf(valor: str | None, *, permitir_curinga: bool = False) -> str | None:
    """Sigla canônica de `valor`, ou None se não for UF reconhecível.

    Aceita sigla em qualquer caixa ("mg") e nome por extenso com ou sem acento
    ("Minas Gerais", "minas gerais"). Com `permitir_curinga`, o "*" (qualquer
    origem) também é aceito — usado só nas matrizes que têm UF de origem.
    """
    bruto = (valor or "").strip()
    if not bruto:
        return None
    if permitir_curinga and bruto == CURINGA_UF:
        return CURINGA_UF

    sigla = bruto.upper()
    if len(sigla) == 2 and sigla in UFS:
        return sigla
    return _POR_EXTENSO.get(_chave(bruto))
