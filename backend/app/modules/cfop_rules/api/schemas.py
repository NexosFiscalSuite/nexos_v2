"""Schemas das regras De/Para CFOP."""
from uuid import UUID

from pydantic import BaseModel, Field


class CfopRegraCreate(BaseModel):
    tipo_item: str = Field(..., examples=["Mercadoria para Revenda"])
    cfop_origem: str = Field(..., examples=["5102"])
    cfop_destino: str = Field(..., examples=["1102"])
    usa_extensao: bool = False
    extensao: str | None = None
    descricao: str | None = None


class CfopRegraUpdate(BaseModel):
    tipo_item: str | None = None
    cfop_destino: str | None = None
    usa_extensao: bool | None = None
    extensao: str | None = None
    descricao: str | None = None


class CfopRegraResponse(BaseModel):
    id: UUID
    tipo_item: str
    cfop_origem: str
    cfop_destino: str
    usa_extensao: bool
    extensao: str | None = None
    descricao: str | None = None

    model_config = {"from_attributes": True}
