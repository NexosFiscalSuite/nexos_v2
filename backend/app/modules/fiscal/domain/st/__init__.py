"""Motor de Auditoria de ICMS Substituição Tributária (domínio puro).

Núcleo v1: CST 10/30/70/90 e CSOSN 201/202/203; modBCST 4 (MVA) e 6 (valor da
operação); MVA Ajustada com as 4 travas de exclusão; dedução do ICMS próprio
(real / teórica do Simples / trava do zerado); FCP-ST em trilha paralela;
réguas de centavos. Fora do v1: CST 60/500 (ressarcimento), ST_ENTRADA, pauta.

Uso típico:
    engine = StAuditEngine(MvaEmMemoria(), EnquadramentoEmMemoria(), FcpEmMemoria())
    resultado = engine.auditar_item(item, operacao)
"""
from .aliquotas import AliquotaResolver
from .engine import StAuditEngine
from .enums import Crt, MetodoReducao, ModBcSt, Regime
from .errors import ErroST
from .model import (
    ItemFiscal,
    MemoriaCalculo,
    Operacao,
    ResultadoAuditoria,
    StatusAuditoria,
)
from .ports import EnquadramentoRepository, FcpRepository, MvaInfo, MvaRepository
from .seed import EnquadramentoEmMemoria, FcpEmMemoria, MvaEmMemoria

__all__ = [
    "StAuditEngine",
    "AliquotaResolver",
    "Crt",
    "ModBcSt",
    "MetodoReducao",
    "Regime",
    "ErroST",
    "ItemFiscal",
    "Operacao",
    "MemoriaCalculo",
    "ResultadoAuditoria",
    "StatusAuditoria",
    "MvaRepository",
    "EnquadramentoRepository",
    "FcpRepository",
    "MvaInfo",
    "MvaEmMemoria",
    "EnquadramentoEmMemoria",
    "FcpEmMemoria",
]
