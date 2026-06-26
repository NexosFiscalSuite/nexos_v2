"""Schemas do CRUD de Matrizes Fiscais (V1: MVA Original)."""
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.shared.domain.value_objects import only_digits


class _MatrizMvaCampos(BaseModel):
    ncm: str = Field(..., examples=["40111000"], description="8/6/4 dígitos (fallback hierárquico)")
    cest: str = Field(..., examples=["0107500"])
    uf_destino: str = Field(..., min_length=2, max_length=2, examples=["MG"])
    mva_original: Decimal = Field(..., ge=0, le=999, examples=["42.00"])
    base_legal: str | None = Field(default=None, examples=["Decreto 48.589/2023"])
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


# ── Enquadramento ST (o produto é ST no destino?) ────────────────────────────
_REGIMES = ("ST", "TN", "ST_ENTRADA")


class _MatrizEnquadramentoCampos(BaseModel):
    ncm: str = Field(..., examples=["40111000"])
    cest: str = Field(..., examples=["0107500"])
    uf_destino: str = Field(..., min_length=2, max_length=2, examples=["MG"])
    regime: str = Field(..., examples=["ST"], description="ST | TN (Normal) | ST_ENTRADA")
    segmento: str | None = Field(default=None, examples=["Autopeças"])
    base_legal: str | None = None
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    @field_validator("regime")
    @classmethod
    def _regime_valido(cls, v: str) -> str:
        v = (v or "").upper()
        if v not in _REGIMES:
            raise ValueError(f"regime deve ser um de {_REGIMES}")
        return v

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["ncm"] = only_digits(self.ncm)
        d["cest"] = only_digits(self.cest)
        d["uf_destino"] = self.uf_destino.upper()
        return d


class MatrizEnquadramentoCreate(_MatrizEnquadramentoCampos):
    pass


class MatrizEnquadramentoUpdate(_MatrizEnquadramentoCampos):
    pass


class MatrizEnquadramentoResponse(_MatrizEnquadramentoCampos):
    id: int

    model_config = {"from_attributes": True}


# ── FCP (Fundo de Combate à Pobreza) por UF + NCM ────────────────────────────
class _MatrizFcpCampos(BaseModel):
    uf_destino: str = Field(..., min_length=2, max_length=2, examples=["MG"])
    ncm: str = Field(default="GERAL", examples=["GERAL", "22030000"],
                     description="'GERAL' aplica a alíquota a toda a UF")
    aliq_fcp_st: Decimal = Field(..., ge=0, le=100, examples=["2.00"],
                                 description="FCP-ST que o motor consome")
    aliq_fcp_interno: Decimal = Field(default=Decimal("0"), ge=0, le=100, examples=["2.00"])
    base_legal: str | None = None
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    def normalizado(self) -> dict:
        d = self.model_dump()
        ncm = (self.ncm or "").strip().upper()
        d["ncm"] = "GERAL" if ncm in ("", "GERAL") else only_digits(self.ncm)
        d["uf_destino"] = self.uf_destino.upper()
        return d


class MatrizFcpCreate(_MatrizFcpCampos):
    pass


class MatrizFcpUpdate(_MatrizFcpCampos):
    pass


class MatrizFcpResponse(_MatrizFcpCampos):
    id: int

    model_config = {"from_attributes": True}


# ── Protocolo / Convênio (ativa a ST interestadual no par UF origem→destino) ──
class _MatrizProtocoloCampos(BaseModel):
    uf_origem: str = Field(..., min_length=2, max_length=2, examples=["SP"])
    uf_destino: str = Field(..., min_length=2, max_length=2, examples=["MG"])
    numero_acordo: str = Field(..., min_length=2, max_length=80,
                               examples=["Protocolo ICMS 41/2008"], description="Acordo (texto livre)")
    base_legal: str | None = None
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["uf_origem"] = self.uf_origem.upper()
        d["uf_destino"] = self.uf_destino.upper()
        d["numero_acordo"] = self.numero_acordo.strip()
        return d


class MatrizProtocoloCreate(_MatrizProtocoloCampos):
    pass


class MatrizProtocoloUpdate(_MatrizProtocoloCampos):
    pass


class MatrizProtocoloResponse(_MatrizProtocoloCampos):
    id: int

    model_config = {"from_attributes": True}
