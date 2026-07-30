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


def _cei_check_digit(base11: str) -> str:
    """DV da matrícula CEI/CNO (INSS): pesos fixos, soma o algarismo da dezena
    com o da unidade e subtrai de 10 (10 vira 0)."""
    pesos = (7, 4, 1, 8, 5, 2, 1, 6, 3, 7, 4)
    soma = sum(int(d) * p for d, p in zip(base11, pesos, strict=True))
    dezena_mais_unidade = (soma // 10) % 10 + soma % 10
    return str((10 - dezena_mais_unidade % 10) % 10)


def _cpf_check_digits(base9: str) -> str:
    def calc(nums: str, primeiro_peso: int) -> str:
        total = sum(int(d) * w for d, w in zip(nums, range(primeiro_peso, 1, -1), strict=False))
        resto = total % 11
        return "0" if resto < 2 else str(11 - resto)

    d1 = calc(base9, 10)
    d2 = calc(base9 + d1, 11)
    return d1 + d2


@dataclass(frozen=True, slots=True)
class DocumentoFiscal:
    """CPF (11 dígitos), CEI/CNO (12) ou CNPJ (14) validado por DV — produtor
    rural PF e matrícula de obra também são clientes do escritório. Normaliza
    para só dígitos (o comprimento distingue o tipo)."""

    value: str

    def __post_init__(self) -> None:
        digits = only_digits(self.value)
        if len(digits) == 14:
            object.__setattr__(self, "value", CNPJ(digits).value)
            return
        if len(digits) == 12:
            if digits == digits[0] * 12:
                raise DomainError("CEI inválido.", code="invalid_cei")
            if _cei_check_digit(digits[:11]) != digits[11]:
                raise DomainError("CEI inválido (dígito verificador).", code="invalid_cei")
            object.__setattr__(self, "value", digits)
            return
        if len(digits) != 11:
            raise DomainError(
                "Informe um CPF (11 dígitos), CEI (12) ou CNPJ (14).",
                code="invalid_documento",
            )
        if digits == digits[0] * 11:
            raise DomainError("CPF inválido.", code="invalid_cpf")
        if _cpf_check_digits(digits[:9]) != digits[9:]:
            raise DomainError("CPF inválido (dígitos verificadores).", code="invalid_cpf")
        object.__setattr__(self, "value", digits)

    @property
    def formatted(self) -> str:
        d = self.value
        if len(d) == 11:
            return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
        if len(d) == 12:
            return f"{d[:2]}.{d[2:5]}.{d[5:10]}/{d[10:]}"
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
