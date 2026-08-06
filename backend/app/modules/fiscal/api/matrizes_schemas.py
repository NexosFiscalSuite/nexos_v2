"""Schemas do CRUD de Matrizes Fiscais (V1: MVA Original)."""
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, Field, field_validator, model_validator

from app.core.exceptions import DomainError
from app.shared.domain.uf import CURINGA_UF, UF_NOMES, normalizar_uf
from app.shared.domain.value_objects import DocumentoFiscal, only_digits


# ── UF: campo controlado, nunca texto livre ─────────────────────────────────
# A busca do motor compara a UF da nota (sigla de 2 letras) com a coluna da
# matriz. Linha gravada como "Minas Gerais", "mg " ou "XX" é linha que NUNCA
# vai ser encontrada: a regra existe no banco e o cálculo sai errado do mesmo
# jeito. Aqui a entrada é generosa (aceita o que o humano digita na planilha) e
# a saída é canônica — o que não dá para reconhecer vira erro, nunca palpite.
def _uf_sigla(valor: object) -> object:
    if not isinstance(valor, str):
        return valor                      # deixa o pydantic reclamar do tipo
    sigla = normalizar_uf(valor)
    if sigla is None:
        raise ValueError("UF inválida: use a sigla do estado (ex.: MG)")
    return sigla


def _uf_sigla_ou_curinga(valor: object) -> object:
    if not isinstance(valor, str):
        return valor
    sigla = normalizar_uf(valor, permitir_curinga=True)
    if sigla is None:
        raise ValueError(
            "UF de origem inválida: use a sigla do estado (ex.: SP) "
            "ou '*' para valer em qualquer origem"
        )
    return sigla


#: UF de estado: aceita "mg", " MG " e "Minas Gerais"; devolve sempre "MG".
Uf = Annotated[str, BeforeValidator(_uf_sigla)]
#: Idem, e ainda aceita "*" (a regra vale para qualquer UF de origem).
#: Só a MVA usa o curinga: a busca de MVA prefere a origem exata e só então cai
#: no "*". Protocolo NÃO — lá a comparação é por igualdade com a UF da nota, e
#: um "*" viraria justamente a linha inencontrável que queremos extinguir.
UfOuCuringa = Annotated[str, BeforeValidator(_uf_sigla_ou_curinga)]

# _UF_NA_RESPOSTA: os schemas de LEITURA (*Response) redeclaram a UF como `str`
# simples, de propósito. A validação estrita é da ESCRITA. Antes deste ajuste a
# UF era texto livre, então a base tem linhas legadas gravadas torto ("Minas
# Gerais", "sp"). Se a resposta as rejeitasse, elas sumiriam da tela e o curador
# nunca poderia corrigi-las — o contrário do que queremos. A tela mostra o que
# está no banco; salvar por cima é que exige a sigla canônica.


class UfOpcao(BaseModel):
    """Uma UF para o dropdown da tela (sigla + nome por extenso)."""

    sigla: str = Field(..., examples=["MG"])
    nome: str = Field(..., examples=["Minas Gerais"])


def ufs_disponiveis() -> list[UfOpcao]:
    """As 27 UFs em ordem alfabética de sigla — fonte única das telas."""
    return [UfOpcao(sigla=s, nome=n) for s, n in UF_NOMES.items()]


# ── Exceção por produto da empresa ──────────────────────────────────────────
def _documento_ou_vazio(valor: object) -> object:
    """CNPJ/CPF/CEI do fornecedor — vazio é válido e quer dizer "qualquer um".

    O código do produto é do fornecedor: dois fornecedores usam códigos
    diferentes para o mesmo produto e o MESMO código para produtos distintos.
    Aqui a entrada é generosa (aceita com ou sem pontuação) e a saída é só
    dígitos; documento com DV errado é recusado na hora — regra gravada torto é
    regra que nunca vai ser encontrada pelo motor.
    """
    if not isinstance(valor, str):
        return valor                      # deixa o pydantic reclamar do tipo
    if not valor.strip():
        return ""                         # "" = vale para QUALQUER fornecedor
    try:
        return DocumentoFiscal(valor).value
    except DomainError as e:              # pydantic espera ValueError
        raise ValueError(getattr(e, "message", None) or str(e)) from e


class _ExcecaoProdutoCampos(BaseModel):
    empresa_id: UUID
    cnpj_fornecedor: Annotated[str, BeforeValidator(_documento_ou_vazio)] = Field(
        default="", examples=["11.444.777/0001-61", ""],
        description="CNPJ (ou CPF do produtor rural) do FORNECEDOR que usa esse "
                    "código de produto. Deixe em branco para a regra valer "
                    "quando qualquer fornecedor mandar esse código.",
    )
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
    uf_origem: UfOuCuringa = Field(
        default=CURINGA_UF, examples=["SP", CURINGA_UF],
        description="UF de origem da mercadoria — '*' vale para qualquer origem",
    )
    uf_destino: Uf = Field(..., examples=["MG"], description="UF de destino da mercadoria")
    mva_original: Decimal = Field(..., ge=0, le=999, examples=["42.00"])
    base_legal: str | None = Field(default=None, examples=["Decreto 48.589/2023"])
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["ncm"] = only_digits(self.ncm)
        d["cest"] = only_digits(self.cest)
        return d


class MatrizMvaCreate(_MatrizMvaCampos):
    pass


class MatrizMvaUpdate(_MatrizMvaCampos):
    pass


class MatrizMvaResponse(_MatrizMvaCampos):
    uf_origem: str          # UF crua na leitura — ver _UF_NA_RESPOSTA
    uf_destino: str
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Enquadramento ST (o produto é ST no destino?) ────────────────────────────
_REGIMES = ("ST", "TN", "ST_ENTRADA")


class _MatrizEnquadramentoCampos(BaseModel):
    ncm: str = Field(..., examples=["40111000"])
    cest: str = Field(..., examples=["0107500"])
    uf_destino: Uf = Field(..., examples=["MG"], description="UF de destino da mercadoria")
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
        return d


class MatrizEnquadramentoCreate(_MatrizEnquadramentoCampos):
    pass


class MatrizEnquadramentoUpdate(_MatrizEnquadramentoCampos):
    pass


class MatrizEnquadramentoResponse(_MatrizEnquadramentoCampos):
    uf_destino: str         # UF crua na leitura — ver _UF_NA_RESPOSTA
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── NCM 'GERAL': a regra que vale para o estado inteiro ──────────────────────
# Convenção compartilhada pelo FCP e pela Alíquota: a linha do estado é gravada
# com o NCM literal "GERAL" e as linhas de produto com os dígitos do NCM. A
# busca do motor desce 8→6→4 dígitos e só então cai na GERAL, então o que está
# em branco na planilha PRECISA virar "GERAL" (e não ""): NCM vazio seria uma
# linha que nenhuma busca encontra.
NCM_GERAL = "GERAL"


def _ncm_ou_geral(valor: str | None) -> str:
    """"" ou "geral" → "GERAL"; qualquer outra coisa → só os dígitos do NCM."""
    ncm = (valor or "").strip().upper()
    return NCM_GERAL if ncm in ("", NCM_GERAL) else only_digits(valor or "")


# ── FCP (Fundo de Combate à Pobreza) por UF + NCM ────────────────────────────
class _MatrizFcpCampos(BaseModel):
    uf_destino: Uf = Field(..., examples=["MG"], description="UF de destino da mercadoria")
    ncm: str = Field(default=NCM_GERAL, examples=[NCM_GERAL, "22030000"],
                     description="'GERAL' aplica a alíquota a toda a UF")
    aliq_fcp_st: Decimal = Field(..., ge=0, le=100, examples=["2.00"],
                                 description="FCP-ST que o motor consome")
    aliq_fcp_interno: Decimal = Field(default=Decimal("0"), ge=0, le=100, examples=["2.00"])
    base_legal: str | None = None
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["ncm"] = _ncm_ou_geral(self.ncm)
        return d


class MatrizFcpCreate(_MatrizFcpCampos):
    pass


class MatrizFcpUpdate(_MatrizFcpCampos):
    pass


class MatrizFcpResponse(_MatrizFcpCampos):
    uf_destino: str         # UF crua na leitura — ver _UF_NA_RESPOSTA
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Alíquota do ICMS na UF de destino: a do estado e a do produto ────────────
class _MatrizAliquotaCampos(BaseModel):
    uf_destino: Uf = Field(..., examples=["MG"], description="UF de destino da mercadoria")
    ncm: str = Field(
        default=NCM_GERAL, examples=[NCM_GERAL, "30049099"],
        description="Deixe 'GERAL' para a alíquota do estado, a que vale para "
                    "todo produto sem regra própria. Preencha o NCM só quando o "
                    "produto tiver alíquota própria em lei (cesta básica, "
                    "medicamento, etc.): o cálculo procura o NCM de 8, depois 6, "
                    "depois 4 dígitos e, se não achar nenhum, usa a linha GERAL.",
    )
    # gt=0 (e não ge=0): alíquota zero não é "produto isento" — isso é
    # enquadramento/exceção de item, não alíquota. Uma linha 0% aqui zeraria o
    # débito do ST em silêncio para a UF (ou para o NCM) inteira.
    aliq_modal: Decimal = Field(..., gt=0, le=100, examples=["18.00"],
                                description="Alíquota do ICMS no destino — débito "
                                            "do ST (sem FCP)")
    aliq_fcp_integrado: Decimal = Field(
        default=Decimal("0"), ge=0, le=100, examples=["2.00"],
        description="FCP integrado à modal — só na carga efetiva do ajuste de MVA",
    )
    p_red_bc_st: Decimal = Field(
        default=Decimal("0"), ge=0, lt=100, examples=["0", "38.89"],
        description="Redução da base de cálculo do ST prevista na lei do destino, "
                    "em % (ex.: 38,89 = a base cai para 61,11% do valor). Deixe 0 "
                    "quando não houver redução. Vale por produto: só faz sentido "
                    "junto com o NCM.",
    )
    base_legal: str | None = Field(default=None, examples=["Lei 9.776/2025 (AL)"])
    data_inicio_vigencia: date
    data_fim_vigencia: date | None = None

    def normalizado(self) -> dict:
        d = self.model_dump()
        d["ncm"] = _ncm_ou_geral(self.ncm)
        return d


class _RecusaReducaoNoEstadoInteiro(BaseModel):
    """Guarda de ESCRITA: redução de base sem NCM é recusada.

    A linha GERAL é a alíquota do estado — ela responde por TODO produto que
    não tem regra própria. Redução de base, ao contrário, é sempre de um
    produto específico (a lei reduz a base daquela mercadoria). Salvar redução
    na linha GERAL aplicaria o desconto ao estado inteiro sem ninguém perceber,
    e o ST sairia a menor em toda a carteira. Fail-closed: recusa na hora, com
    o motivo, em vez de calcular por palpite.

    Só Create/Update herdam. A LEITURA não valida — se uma linha torta chegou
    ao banco por outro caminho, ela precisa APARECER na tela para o curador
    poder corrigir (mesma razão do _UF_NA_RESPOSTA).
    """

    @model_validator(mode="after")
    def _reducao_de_base_exige_ncm(self):
        if self.p_red_bc_st > 0 and _ncm_ou_geral(self.ncm) == NCM_GERAL:
            raise ValueError(
                "A redução de base é de um produto, não do estado: informe o NCM "
                "do item que a lei manda reduzir. A linha 'GERAL' vale para todos "
                "os produtos da UF — com redução nela, todo o estado calcularia o "
                "ST a menor. Para cadastrar só a alíquota do estado, deixe a "
                "redução em 0."
            )
        return self


class MatrizAliquotaCreate(_MatrizAliquotaCampos, _RecusaReducaoNoEstadoInteiro):
    pass


# Update = Create (mesmos campos, MESMA guarda): editar uma linha não pode ser
# a porta de entrada do que a criação recusa.
class MatrizAliquotaUpdate(MatrizAliquotaCreate):
    pass


class MatrizAliquotaResponse(_MatrizAliquotaCampos):
    uf_destino: str         # UF crua na leitura — ver _UF_NA_RESPOSTA
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── Protocolo / Convênio (ativa a ST interestadual no par UF origem→destino) ──
# Situações: só ATIVO conta como acordo vigente para o motor; SEM_ACORDO é o
# registro explícito de que NÃO há acordo no par (→ antecipação do destinatário);
# INATIVO/DENUNCIADO = acordo encerrado. Qualquer linha marca o par como CURADO.
SITUACOES_PROTOCOLO = ("ATIVO", "SEM_ACORDO", "INATIVO", "DENUNCIADO")


class _MatrizProtocoloCampos(BaseModel):
    # Sem curinga aqui: o acordo é de um PAR de estados concreto, e a busca
    # compara a origem por igualdade — "*" nunca casaria com nota nenhuma.
    uf_origem: Uf = Field(..., examples=["SP"], description="UF de origem da mercadoria")
    uf_destino: Uf = Field(..., examples=["MG"], description="UF de destino da mercadoria")
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
        d["numero_acordo"] = self.numero_acordo.strip()
        return d


class MatrizProtocoloCreate(_MatrizProtocoloCampos):
    pass


class MatrizProtocoloUpdate(_MatrizProtocoloCampos):
    pass


class MatrizProtocoloResponse(_MatrizProtocoloCampos):
    uf_origem: str          # UF crua na leitura — ver _UF_NA_RESPOSTA
    uf_destino: str
    id: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}
