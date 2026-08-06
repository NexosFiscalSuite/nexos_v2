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
from app.shared.domain.uf import normalizar_uf
from app.shared.domain.value_objects import DocumentoFiscal


class EmpresaLinha(BaseModel):
    """Uma linha da planilha — ordem dos campos = ordem das colunas do template."""

    cnpj: str = Field(..., examples=["11.444.777/0001-61"],
                      description="CNPJ, CPF (produtor rural) ou CEI (obra/INSS), "
                                  "com ou sem pontuação — normalizado e validado (DV)")
    razao_social: str = Field(..., min_length=2, max_length=200)
    nome_fantasia: str | None = Field(default=None, max_length=200)
    regime: str | None = Field(default=None, max_length=40,
                               description="Ex.: Simples Nacional, Lucro Presumido, Lucro Real")
    uf: str | None = Field(default=None,
                           description="Sigla (MG) ou nome por extenso (Minas Gerais)")
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
            return DocumentoFiscal(v).value   # CNPJ (14), CEI (12) ou CPF (11)
        except DomainError as e:              # pydantic espera ValueError
            raise ValueError(e.message if hasattr(e, "message") else str(e)) from e

    @field_validator("uf")
    @classmethod
    def _uf_normalizada(cls, v: str | None) -> str | None:
        """Planilha do mundo real traz "Minas Gerais", "mg", "MG " — converte
        tudo para a sigla; só reclama quando não dá para reconhecer. A tabela de
        UFs é a compartilhada (app.shared.domain.uf), a mesma das matrizes."""
        if v is None or not v.strip():
            return None                       # UF em branco é opcional aqui
        bruto = v.strip()
        sigla = normalizar_uf(bruto)
        if sigla is None:
            raise ValueError(f"UF '{bruto}' não reconhecida — use a sigla (ex.: MG)")
        return sigla


def spec_empresas(tenant_id: UUID) -> BulkSpec:
    """Spec por requisição: o tenant do usuário logado entra em TODA linha
    criada — a planilha não tem (nem poderia ter) coluna de tenant."""
    return BulkSpec(
        Empresa,
        EmpresaLinha,
        chave=("cnpj",),
        normalizar=lambda o: {**o.model_dump(), "tenant_id": tenant_id},
    )
