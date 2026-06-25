"""Schemas do CRUD de Matrizes Fiscais (V1: MVA Original)."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.shared.domain.value_objects import only_digits


class _MatrizMvaCampos(BaseModel):
    ncm: str = Field(..., examples=["40111000"], description="8/6/4 dígitos (fallback hierárquico)")
    cest: str = Field(..., examples=["0107500"])
    uf_destino: str = Field(..., min_length=2, max_length=2, examples=["MG"])
    mva_original: Decimal = Field(..., ge=0, le=999, examples=["42.00"])
    ato_legal: str | None = Field(default=None, examples=["Decreto 48.589/2023"])
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["ncm"] = only_digits(self.ncm)
        d["cest"] = only_digits(self.cest)
        d["uf_destino"] = self.uf_destino.upper()
        return d


class MatrizMvaCreate(_MatrizMvaCampos):
    pass


class MatrizMvaUpdate(_MatrizMvaCampos):
    pass


class MatrizMvaResponse(_MatrizMvaCampos):
    id: int

    model_config = {"from_attributes": True}
