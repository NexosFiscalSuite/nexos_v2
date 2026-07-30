"""Cadastro de empresas em lote (planilha CSV — padrão das Matrizes Fiscais).

Template = export (cabeçalho + empresas atuais); import = upsert por CNPJ
dentro do tenant (o tenant_id é injetado pelo spec, nunca vem da planilha).
Linha inválida vira erro relatado (linha + motivo) — não derruba o lote.
"""
from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.core.exceptions import DomainError
from app.modules.companies.infrastructure.models import Empresa
from app.shared.bulk_csv import BulkSpec
from app.shared.domain.value_objects import CNPJ


class EmpresaLinha(BaseModel):
    """Uma linha da planilha — ordem dos campos = ordem das colunas do template."""

    cnpj: str = Field(..., examples=["11.444.777/0001-61"],
                      description="Com ou sem pontuação — normalizado e validado (DV)")
    razao_social: str = Field(..., min_length=2, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    regime: str | None = Field(default=None, max_length=40,
                               description="Ex.: Simples Nacional, Lucro Presumido, Lucro Real")
    uf: str | None = Field(default=None, max_length=2)
    municipio: str | None = Field(default=None, max_length=120)
    inscricao_estadual: str | None = Field(default=None, max_length=30)
    cnae: str | None = Field(default=None, max_length=20)
    cep: str | None = Field(default=None, max_length=9)
    logradouro: str | None = Field(default=None, max_length=200)
    numero: str | None = Field(default=None, max_length=20)
    bairro: str | None = Field(default=None, max_length=120)

    @field_validator("cnpj")
    @classmethod
    def _cnpj_valido(cls, v: str) -> str:
        try:
            return CNPJ(v).value          # 14 dígitos, DV conferido
        except DomainError as e:          # pydantic espera ValueError
            raise ValueError(e.message if hasattr(e, "message") else str(e)) from e

    @field_validator("uf")
    @classmethod
    def _uf_maiuscula(cls, v: str | None) -> str | None:
        return v.strip().upper() if v else v


def spec_empresas(tenant_id: UUID) -> BulkSpec:
    """Spec por requisição: o tenant do usuário logado entra em TODA linha
    criada — a planilha não tem (nem poderia ter) coluna de tenant."""
    return BulkSpec(
        Empresa,
        EmpresaLinha,
        chave=("cnpj",),
        normalizar=lambda o: {**o.model_dump(), "tenant_id": tenant_id},
    )
