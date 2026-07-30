"""Atualização de cadastro de empresas pela base pública da Receita (OpenCNPJ).

O lote roda no worker Celery com PAUSA entre consultas: a API é gratuita e sem
chave — rajada de centenas de CNPJs derruba o serviço (ou nos derruba via 429).
O intervalo cresce com o tamanho do lote e um 429 ganha pausa longa + nova
tentativa antes de virar falha. Progresso vai para processing_jobs (polling).
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select

from app.modules.companies.infrastructure.models import Empresa
from app.modules.jobs.infrastructure.models import (
    STATUS_DONE,
    STATUS_RUNNING,
)
from app.modules.jobs.infrastructure.repositories import JobRepository
from app.shared.cnpj_lookup import consultar_opencnpj, formatar_cnpj

# Campos que a consulta pode atualizar → limite da coluna (trunca, não estoura).
_LIMITES = {
    "razao_social": 200, "nome_fantasia": 200, "regime": 40, "uf": 2,
    "municipio": 120, "cnae": 20, "cep": 9, "logradouro": 200,
    "numero": 20, "bairro": 120,
}
# A consulta só CONFIRMA Simples/MEI; Presumido×Real é escolha do escritório.
_REGIMES_CONFIAVEIS = ("Simples Nacional", "MEI")

PAUSA_RATE_LIMIT = 30.0     # 429 = "devagar": espera longa e tenta 1x de novo
_MAX_LISTA = 100            # falhas/avisos guardados no job (o resto vira contagem)


def montar_atualizacao(dados: dict) -> dict:
    """Consulta → campos a aplicar na Empresa. Só valor NÃO vazio entra (a
    Receita nunca APAGA o que já temos) e o regime só muda quando a consulta
    confirma Simples/MEI."""
    campos = {}
    for campo, limite in _LIMITES.items():
        valor = str(dados.get(campo) or "").strip()
        if not valor:
            continue
        if campo == "regime" and valor not in _REGIMES_CONFIAVEIS:
            continue
        campos[campo] = valor[:limite]
    return campos


def intervalo_lote(total: int) -> float:
    """Pausa entre consultas — quanto maior o lote, mais folga para a API."""
    if total <= 30:
        return 1.0
    if total <= 120:
        return 2.0
    return 3.0


async def atualizar_cadastros_lote(
    tenant_id: UUID,
    job_id: UUID,
    *,
    sessao_factory,
    consultar: Callable[[str, str], dict] = consultar_opencnpj,
    dormir=asyncio.sleep,
) -> dict:
    """Atualiza TODAS as empresas do tenant consultando CNPJ a CNPJ.

    Sessão POR EMPRESA (transação curta): o progresso fica visível ao polling
    a cada passo e a pausa entre consultas acontece SEM conexão aberta.
    Falha em um CNPJ não derruba o lote — vira linha no resumo.
    """
    async with sessao_factory() as s:
        job = await JobRepository(s).by_id(job_id)
        linhas = (await s.execute(
            select(Empresa.id, Empresa.cnpj, Empresa.razao_social)
            .where(Empresa.tenant_id == tenant_id)
            .order_by(Empresa.razao_social)
        )).all()
        if job:
            job.status = STATUS_RUNNING
            job.total = len(linhas)

    pausa = intervalo_lote(len(linhas))
    resumo = {"total": len(linhas), "atualizadas": 0, "pf_puladas": 0,
              "falhas": [], "avisos": []}

    for i, (empresa_id, cnpj, razao) in enumerate(linhas):
        # Produtor rural PF (CPF): não existe consulta pública — cadastro manual.
        if len(cnpj or "") != 14:
            resumo["pf_puladas"] += 1
            async with sessao_factory() as s:
                job = await JobRepository(s).by_id(job_id)
                if job:
                    job.processed = i + 1
            continue

        res = await asyncio.to_thread(consultar, cnpj, "empresa")
        if not res.get("ok") and "429" in (res.get("error") or ""):
            await dormir(PAUSA_RATE_LIMIT)
            res = await asyncio.to_thread(consultar, cnpj, "empresa")

        async with sessao_factory() as s:
            if res.get("ok"):
                dados = res.get("dados") or {}
                empresa = await s.get(Empresa, empresa_id)
                if empresa is not None:
                    for campo, valor in montar_atualizacao(dados).items():
                        setattr(empresa, campo, valor)
                    resumo["atualizadas"] += 1
                situacao = str(dados.get("situacao") or "").strip()
                if situacao and not situacao.lower().startswith("ativa") \
                        and len(resumo["avisos"]) < _MAX_LISTA:
                    resumo["avisos"].append({
                        "cnpj": formatar_cnpj(cnpj), "razao_social": razao,
                        "situacao": situacao,
                    })
            elif len(resumo["falhas"]) < _MAX_LISTA:
                resumo["falhas"].append({
                    "cnpj": formatar_cnpj(cnpj), "razao_social": razao,
                    "erro": res.get("error") or "Falha na consulta",
                })
            job = await JobRepository(s).by_id(job_id)
            if job:
                job.processed = i + 1

        if i < len(linhas) - 1:
            await dormir(pausa)

    async with sessao_factory() as s:
        job = await JobRepository(s).by_id(job_id)
        if job:
            job.status = STATUS_DONE
            job.result = resumo
    return resumo
