"""Schemas do CRUD de Matrizes Fiscais (V1: MVA Original)."""
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.shared.domain.value_objects import only_digits


# ── Exceção por produto da empresa ──────────────────────────────────────────
class _ExcecaoProdutoCampos(BaseModel):
    empresa_id: UUID
    codigo_produto: str = Field(..., min_length=1, max_length=60)
    descricao_produto: str | None = Field(default=None, max_length=500)
    ncm: str | None = Field(default=None, max_length=10)
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None
    tributado_icms: bool = True
    lei_icms: str | None = Field(default=None, max_length=2000)
    ativo: bool = True

    @field_validator("data_fim_vigencia")
    @classmethod
    def _periodo_valido(cls, v: date | None, info):
        inicio = info.data.get("data_inicio_vigencia")
        if v is not None and inicio is not None and v < inicio:
            raise ValueError("data final não pode ser anterior à inicial")
        return v

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["codigo_produto"] = self.codigo_produto.strip().upper()
        d["ncm"] = only_digits(self.ncm or "") or None
        d["descricao_produto"] = (self.descricao_produto or "").strip() or None
        d["lei_icms"] = (self.lei_icms or "").strip() or None
        return d


class ExcecaoProdutoCreate(_ExcecaoProdutoCampos):
    pass


class ExcecaoProdutoUpdate(_ExcecaoProdutoCampos):
    pass


class ExcecaoProdutoResponse(_ExcecaoProdutoCampos):
    id: UUID
    definido_por: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


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
    created_at: datetime | None = None

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
    created_at: datetime | None = None

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
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Alíquota modal do ICMS por UF de destino (com FCP integrado à modal) ─────
class _MatrizAliquotaCampos(BaseModel):
    uf_destino: str = Field(..., min_length=2, max_length=2, examples=["MG"])
    aliq_modal: Decimal = Field(..., gt=0, le=100, examples=["18.00"],
                                description="Alíquota modal — débito do ST (sem FCP)")
    aliq_fcp_integrado: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, examples=["2.00"],
        description="FCP integrado à modal — só na carga efetiva do ajuste de MVA",
    )
    base_legal: str | None = Field(default=None, examples=["Lei 9.776/2025 (AL)"])
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["uf_destino"] = self.uf_destino.upper()
        return d


class MatrizAliquotaCreate(_MatrizAliquotaCampos):
    pass


class MatrizAliquotaUpdate(_MatrizAliquotaCampos):
    pass


class MatrizAliquotaResponse(_MatrizAliquotaCampos):
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Protocolo / Convênio (ativa a ST interestadual no par UF origem→destino) ──
# Situações: só ATIVO conta como acordo vigente para o motor; SEM_ACORDO é o
# registro explícito de que NÃO há acordo no par (→ antecipação do destinatário);
# INATIVO/DENUNCIADO = acordo encerrado. Qualquer linha marca o par como CURADO.
SITUACOES_PROTOCOLO = ("ATIVO", "SEM_ACORDO", "INATIVO", "DENUNCIADO")


class _MatrizProtocoloCampos(BaseModel):
    uf_origem: str = Field(..., min_length=2, max_length=2, examples=["SP"])
    uf_destino: str = Field(..., min_length=2, max_length=2, examples=["MG"])
    ncm: str | None = Field(default=None,
                            description="Escopo do acordo por NCM (vazio = par inteiro)")
    numero_acordo: str = Field(..., min_length=2, max_length=80,
                               examples=["Protocolo ICMS 41/2008"], description="Acordo (texto livre)")
    situacao: str = Field(default="ATIVO", examples=["ATIVO"])
    base_legal: str | None = None
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    @field_validator("situacao")
    @classmethod
    def _situacao_valida(cls, v: str) -> str:
        v = (v or "ATIVO").strip().upper()
        if v not in SITUACOES_PROTOCOLO:
            raise ValueError(f"situação inválida (use: {', '.join(SITUACOES_PROTOCOLO)})")
        return v

    @field_validator("ncm")
    @classmethod
    def _ncm_digitos(cls, v: str | None) -> str | None:
        """Aceita formatado ('4011.70.00') e normaliza para dígitos."""
        if v is None:
            return None
        digitos = "".join(ch for ch in v if ch.isdigit())
        if len(digitos) > 8:
            raise ValueError("NCM tem no máximo 8 dígitos")
        return digitos or None

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
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
