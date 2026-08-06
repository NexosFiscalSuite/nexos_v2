"""Ports (interfaces) para os dados que vivem no banco com vigência temporal.

O domínio define O QUE precisa; a infraestrutura (Postgres, seed em memória)
decide COMO entrega. Isto mantém o motor puro e testável — inversão de
dependência da Clean Architecture.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from .enums import Regime


@dataclass(frozen=True, slots=True)
class MvaInfo:
    mva_original: Decimal
    ncm_casado: str          # qual nível do NCM bateu (diagnóstico do fallback)
    matriz_id: int | None = None   # linha da matriz usada (rastreabilidade na memória)
    base_legal: str | None = None  # norma da MVA (vai à memória e às cartas)
    # UF de origem da LINHA que casou ("*" = regra curinga, válida p/ qualquer
    # remetente). Vai à memória/carta: "de onde veio a MVA que aplicamos".
    uf_origem_casada: str | None = None


class MvaRepository(Protocol):
    """MATRIZ_MVA_Por_Segmento — chave NCM+CEST+UF origem→destino, fallback 8→6→4.

    A MVA NÃO depende só do destino: o acordo do estado REMETENTE muda a margem,
    e a interna (origem == destino) difere da interestadual. Precedência da
    busca: para cada nível de NCM (8→6→4), tenta a origem EXATA e só então o
    curinga `"*"` — especificidade da origem ganha DENTRO do nível de NCM, para
    que uma regra geral nunca sequestre um par curado.

    `None` = NENHUMA linha na matriz para a chave na data. O motor NÃO assume
    MVA zero: vira ERRO_MVA_NAO_ENCONTRADA (fail-closed). Uma linha cadastrada
    com MVA `0,00` é o contrário disso — é a DECISÃO curada de que a base é o
    valor da operação, e vem como MvaInfo com `mva_original == 0`.
    """

    def buscar(
        self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date
    ) -> MvaInfo | None: ...


@dataclass(frozen=True, slots=True)
class AliquotaUf:
    """Alíquotas da UF de destino vigentes na data da operação.

    `modal` alimenta o DÉBITO do ST (pICMSST) — sem FCP, que roda em trilha
    paralela. `fcp_integrado` só compõe a carga `efetiva`, usada exclusivamente
    no denominador do ajuste de MVA (R-07).
    """

    modal: Decimal
    fcp_integrado: Decimal = Decimal("0")
    matriz_id: int | None = None   # linha da matriz usada (rastreabilidade na memória)
    base_legal: str | None = None  # norma da alíquota (vai à memória e às cartas)

    @property
    def efetiva(self) -> Decimal:
        return self.modal + self.fcp_integrado


class AliquotaRepository(Protocol):
    """MATRIZ_ALIQUOTA — alíquota modal (e FCP integrado) por UF, com vigência.

    `None` = sem alíquota vigente cadastrada para a UF na data → o motor NÃO
    calcula (fail-closed), nunca assume a taxa "atual".
    """

    def buscar(self, uf_dest: str, data: date) -> AliquotaUf | None: ...


class EnquadramentoRepository(Protocol):
    """MATRIZ_NCM_Enquadramento_ST — portão ST / TN / ST_ENTRADA / DIFAL.

    A Exceção do Item da empresa (quando a implementação a suporta) é
    identificada pelo PAR `codigo_produto` + `cnpj_emitente`: o cProd é o
    código do FORNECEDOR, e fornecedores diferentes reaproveitam o mesmo
    código para produtos distintos. `cnpj_emitente` vazio (ou sem regra do
    fornecedor) cai na exceção genérica, cadastrada para qualquer fornecedor.

    Métodos OPCIONAIS que o motor consulta por `getattr` (implemente para ter
    diagnóstico melhor; a ausência só perde texto, nunca muda o cálculo):

      - ``explicar_tn(ncm, cest, uf_dest, codigo_produto="", cnpj_emitente="")
        -> str | None`` — por que o item caiu em TN. `None` = TN por decisão de
        cadastro (legítimo, fora do motor); string = falta/conflito de cadastro,
        que vira NAO_AUDITAVEL acionável.
      - ``fonte_regime(codigo_produto="", cnpj_emitente="") -> str`` — de onde
        veio a decisão: ``"EXCECAO_ITEM"`` (regra da empresa PARA AQUELE
        fornecedor) ou ``"MATRIZ"``. Sem o CNPJ a resposta mentiria, marcando
        como exceção o item homônimo de outro fornecedor.
    """

    def regime(
        self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date,
        codigo_produto: str = "", cnpj_emitente: str = "",
    ) -> Regime: ...


class FcpRepository(Protocol):
    """MATRIZ_FCP_Por_UF — alíquota de FCP-ST por UF+NCM+vigência (fallback 8→4→GERAL).

    Retorna a alíquota (0 se o NCM não está sujeito ao fundo na UF de destino).
    """

    def aliquota_st(self, ncm: str, uf_dest: str, data: date) -> Decimal: ...


class ProtocoloRepository(Protocol):
    """MATRIZ_PROTOCOLO_ST — há acordo/convênio de ST vigente no par UF
    origem→destino (para o NCM, quando o acordo tem escopo)? Decide a
    RESPONSABILIDADE na interestadual: com protocolo o remetente é o substituto;
    sem ele, a ST vira antecipação do destinatário.

    Tri-state: True = acordo vigente; False = par CURADO sem acordo aplicável;
    None = par sem NENHUM registro na matriz (nunca avaliado) — o motor não
    decide e trava com ERRO_PROTOCOLO_NAO_AVALIADO (fail-closed, ADR-0002).

    `fonte` vai para a memória de cálculo: "matriz" = a resposta veio de uma
    matriz consultada; "assumido" = default do motor sem matriz injetada
    (transparente na defesa fiscal, nunca silencioso).
    """

    fonte: str

    def tem_protocolo(
        self, uf_orig: str, uf_dest: str, data: date, ncm: str = ""
    ) -> bool | None: ...
