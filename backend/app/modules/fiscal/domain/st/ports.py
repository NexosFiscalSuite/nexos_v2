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

# Chave da linha "regra do estado" nas matrizes por NCM (alíquota e FCP): vale
# para todo produto que não tem linha própria. Mesma convenção do MATRIZ_FCP.
NCM_GERAL = "GERAL"


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
    """Tributação interna DO PRODUTO na UF de destino, vigente na data.

    `modal` alimenta o DÉBITO do ST (pICMSST) — sem FCP, que roda em trilha
    paralela. `fcp_integrado` só compõe a carga `efetiva`, usada exclusivamente
    no denominador do ajuste de MVA (R-07).

    A alíquota NÃO é só da UF: cesta básica, medicamento e afins têm alíquota
    própria por NCM, e usar a modal do estado neles cobra ST a maior (18% num
    produto de 12%, em MG). `ncm_casado` diz QUAL nível respondeu na busca
    8→6→4→GERAL — e é ele que separa "regra curada do produto" de "regra geral
    do estado", diferença que decide a redução de base (ver `p_red_bc_st`).
    """

    modal: Decimal
    fcp_integrado: Decimal = Decimal("0")
    matriz_id: int | None = None   # linha da matriz usada (rastreabilidade na memória)
    base_legal: str | None = None  # norma da alíquota (vai à memória e às cartas)
    # Nível do NCM que casou (8/6/4 dígitos) ou NCM_GERAL (regra do estado).
    ncm_casado: str = NCM_GERAL
    # Redução de base do ST prevista em NORMA para o produto no destino. Só é
    # decisão curada quando a linha é `especifica`: na GERAL a redução não foi
    # curada por produto e o motor segue o pRedBCST do XML (ver engine, passo 5).
    p_red_bc_st: Decimal = Decimal("0")

    @property
    def efetiva(self) -> Decimal:
        return self.modal + self.fcp_integrado

    @property
    def especifica(self) -> bool:
        """True = linha curada DO PRODUTO (NCM); False = regra geral do estado."""
        return self.ncm_casado != NCM_GERAL


class AliquotaRepository(Protocol):
    """MATRIZ_ALIQUOTA — tributação interna por UF **e NCM**, com vigência.

    Busca com fallback 8→6→4→GERAL (mesma convenção do FCP e da MVA): a linha do
    produto vence a regra do estado, e `NCM_GERAL` é a rede de segurança que
    responde por todo NCM sem curadoria própria.

    `None` = a UF não tem NENHUMA linha vigente na data (nem a GERAL) → o motor
    NÃO calcula (fail-closed, ERRO_ALIQUOTA_NAO_ENCONTRADA), nunca assume a
    taxa "atual".
    """

    def buscar(self, ncm: str, uf_dest: str, data: date) -> AliquotaUf | None: ...


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
