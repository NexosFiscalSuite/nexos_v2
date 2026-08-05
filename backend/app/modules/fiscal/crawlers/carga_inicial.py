"""Carga inicial das matrizes — deixa a base CHEIA com um comando.

O desenho da automação (robô propõe, curador aprova) vale para o dia a dia,
mas a PRIMEIRA carga ficava presa na fila. Esta carga semeia o que já foi
verificado com base legal (alíquotas das 7 UFs e FCP geral do RJ — os mesmos
valores de docs/seeds, conferidos em fontes cruzadas em 04/08/2026) e o
worker aprova em lote as propostas de MVA/Protocolos do Anexo VII com
revisor explícito — a trilha registra que foi a carga inicial, e qualquer
linha já existente (inclusive curadoria manual) NUNCA é sobrescrita.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.fiscal.infrastructure.matrizes_models import MatrizAliquota, MatrizFcp
from app.modules.fiscal.infrastructure.vigencia import sobreposicao_existente

REVISOR_CARGA = "carga inicial automática (robô)"

# Alíquotas modais das 7 UFs com clientes (verificadas em 04/08/2026).
_SEED_ALIQUOTAS = [
    {"uf_destino": "MG", "aliq_modal": "18.00", "aliq_fcp_integrado": "0",
     "base_legal": "Lei 6.763/1975, art. 12 (RICMS/MG 2023)",
     "data_inicio_vigencia": date(2024, 1, 1), "data_fim_vigencia": None},
    {"uf_destino": "SP", "aliq_modal": "18.00", "aliq_fcp_integrado": "0",
     "base_legal": "Lei 6.374/1989, art. 34 (RICMS/SP art. 52, I)",
     "data_inicio_vigencia": date(2024, 1, 1), "data_fim_vigencia": None},
    {"uf_destino": "PR", "aliq_modal": "19.50", "aliq_fcp_integrado": "0",
     "base_legal": "Lei 21.850/2023 (efeitos 18/03/2024)",
     "data_inicio_vigencia": date(2024, 3, 18), "data_fim_vigencia": None},
    {"uf_destino": "RJ", "aliq_modal": "18.00", "aliq_fcp_integrado": "2.00",
     "base_legal": "Lei 2.657/1996 + FECP Lei 4.056/2002",
     "data_inicio_vigencia": date(2024, 1, 1), "data_fim_vigencia": date(2024, 3, 19)},
    {"uf_destino": "RJ", "aliq_modal": "20.00", "aliq_fcp_integrado": "2.00",
     "base_legal": "Lei 10.253/2023 + FECP LC 210/2023 (efeitos 20/03/2024)",
     "data_inicio_vigencia": date(2024, 3, 20), "data_fim_vigencia": None},
    {"uf_destino": "RS", "aliq_modal": "17.00", "aliq_fcp_integrado": "0",
     "base_legal": "Lei 8.820/1989 (RICMS/RS art. 27, I)",
     "data_inicio_vigencia": date(2024, 1, 1), "data_fim_vigencia": None},
    {"uf_destino": "GO", "aliq_modal": "19.00", "aliq_fcp_integrado": "0",
     "base_legal": "Lei 22.460/2023 (RCTE/GO, efeitos 01/04/2024)",
     "data_inicio_vigencia": date(2024, 4, 1), "data_fim_vigencia": None},
    {"uf_destino": "DF", "aliq_modal": "20.00", "aliq_fcp_integrado": "0",
     "base_legal": "Lei 7.326/2023 (efeitos 21/01/2024)",
     "data_inicio_vigencia": date(2024, 1, 21), "data_fim_vigencia": None},
]

# FCP-ST geral do RJ (única UF do escritório com FCP de base ampla; os FCP
# por produto das demais UFs seguem pela curadoria — fonte própria por lei).
_SEED_FCP = [
    {"uf_destino": "RJ", "ncm": "GERAL", "aliq_fcp_st": "2.00",
     "aliq_fcp_interno": "2.00",
     "base_legal": "FECP — Lei 4.056/2002 + LC 210/2023 (exceções: cesta básica)",
     "data_inicio_vigencia": date(2024, 1, 1), "data_fim_vigencia": None},
]


def _decimais(dados: dict) -> dict:
    return {
        k: (Decimal(v) if isinstance(v, str) and k.startswith("aliq") else v)
        for k, v in dados.items()
    }


async def aplicar_seed_aliquotas_fcp(session: AsyncSession) -> dict:
    """Insere as alíquotas/FCP verificadas onde a família de vigência está
    VAZIA — qualquer linha existente (manual ou não) tem prioridade e nada é
    sobrescrito. Idempotente: rodar de novo não duplica."""
    resumo = {"aliquotas_inseridas": 0, "fcp_inseridos": 0, "ja_existiam": 0}
    for modelo, linhas, chave in (
        (MatrizAliquota, _SEED_ALIQUOTAS, "aliquotas_inseridas"),
        (MatrizFcp, _SEED_FCP, "fcp_inseridos"),
    ):
        for dados in linhas:
            dados = _decimais(dados)
            if await sobreposicao_existente(session, modelo, dados) is not None:
                resumo["ja_existiam"] += 1
                continue
            session.add(modelo(**dados))
            resumo[chave] += 1
    await session.flush()
    return resumo
