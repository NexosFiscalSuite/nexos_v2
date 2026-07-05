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


class MvaRepository(Protocol):
    """MATRIZ_MVA_Por_Segmento — chave NCM+CEST+UF, com fallback 8→6→4 dígitos."""

    def buscar(self, ncm: str, cest: str, uf_dest: str, data: date) -> MvaInfo | None: ...


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
    """MATRIZ_NCM_Enquadramento_ST — portão ST / TN / ST_ENTRADA / DIFAL."""

    def regime(
        self, ncm: str, cest: str, uf_orig: str, uf_dest: str, data: date
    ) -> Regime: ...


class FcpRepository(Protocol):
    """MATRIZ_FCP_Por_UF — alíquota de FCP-ST por UF+NCM+vigência (fallback 8→4→GERAL).

    Retorna a alíquota (0 se o NCM não está sujeito ao fundo na UF de destino).
    """

    def aliquota_st(self, ncm: str, uf_dest: str, data: date) -> Decimal: ...


class ProtocoloRepository(Protocol):
    """MATRIZ_PROTOCOLO_ST — há acordo/convênio de ST vigente no par UF
    origem→destino? Decide a RESPONSABILIDADE na interestadual: com protocolo o
    remetente é o substituto; sem ele, a ST vira antecipação do destinatário.

    `fonte` vai para a memória de cálculo: "matriz" = a resposta veio de uma
    matriz consultada; "assumido" = default do motor sem matriz injetada
    (transparente na defesa fiscal, nunca silencioso).
    """

    fonte: str

    def tem_protocolo(self, uf_orig: str, uf_dest: str, data: date) -> bool: ...
