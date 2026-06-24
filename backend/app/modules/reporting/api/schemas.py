"""Schemas de reporting (gerador avançado)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class TagInfo(BaseModel):
    key: str
    label: str
    escopo: str   # capa | item
    grupo: str
    money: bool


class ColunaCfg(BaseModel):
    tag: str | None = None
    label: str | None = None
    audit: bool = False


class ModeloConfig(BaseModel):
    capa: list[ColunaCfg] = []
    itens: list[ColunaCfg] = []
    totais: bool = False
    finalidade: bool = True
    calculos: bool = True
    auditoria: list[str] = []


class ModeloCreate(ModeloConfig):
    nome: str = Field(..., min_length=2, max_length=120)
    fluxo: str = Field(..., examples=["entrada", "saida", "servico", "cte"])


class ModeloUpdate(BaseModel):
    nome: str | None = None
    config: ModeloConfig | None = None


class ModeloResponse(BaseModel):
    id: UUID
    nome: str
    fluxo: str
    config: dict
    created_at: datetime | None = None


class GerarRequest(BaseModel):
    modelo_id: UUID
    ano: str | None = None
    mes: str | None = None


class GerarResponse(BaseModel):
    job_id: UUID
    status: str
    detail: str = "Geração enfileirada. Baixe em GET /reporting/download/{job_id} quando concluir."
