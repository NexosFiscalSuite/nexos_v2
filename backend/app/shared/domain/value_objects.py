"""Value Objects fiscais compartilhados entre módulos.

Por ora só o CNPJ (usado no signup do tenant). Competência, ChaveAcesso e CFOP
entram na Fase 3 junto com o domínio fiscal.
"""
import re
from dataclasses import dataclass

from app.core.exceptions import DomainError

_NON_DIGIT = re.compile(r"\D")


def only_digits(value: str) -> str:
    return _NON_DIGIT.sub("", value or "")


def _cnpj_check_digits(base12: str) -> str:
    def calc(nums: str, weights: list[int]) -> str:
        total = sum(int(d) * w for d, w in zip(nums, weights, strict=False))
        rest = total % 11
        return "0" if rest < 2 else str(11 - rest)

    w1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    w2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = calc(base12, w1)
    d2 = calc(base12 + d1, w2)
    return d1 + d2


@dataclass(frozen=True, slots=True)
class CNPJ:
    """CNPJ validado, normalizado para 14 dígitos."""

    value: str

    def __post_init__(self) -> None:
        digits = only_digits(self.value)
        if len(digits) != 14:
            raise DomainError("CNPJ deve ter 14 dígitos.", code="invalid_cnpj")
        if digits == digits[0] * 14:
            raise DomainError("CNPJ inválido.", code="invalid_cnpj")
        if _cnpj_check_digits(digits[:12]) != digits[12:]:
            raise DomainError("CNPJ inválido (dígitos verificadores).", code="invalid_cnpj")
        object.__setattr__(self, "value", digits)

    @property
    def formatted(self) -> str:
        d = self.value
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
