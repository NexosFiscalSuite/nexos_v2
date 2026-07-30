"""Atualização de cadastro pela Receita (OpenCNPJ): mapeamento e lote.

O lote roda no worker com sessão POR EMPRESA e pausa entre consultas; aqui a
pausa é capturada por um dublê (nada dorme de verdade) e a API é um dicionário.
"""
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.modules.companies.application.atualiza_cadastro import (
    PAUSA_RATE_LIMIT,
    atualizar_cadastros_lote,
    intervalo_lote,
    montar_atualizacao,
)
from app.modules.companies.infrastructure.models import Empresa
from app.modules.jobs.infrastructure.models import (
    KIND_ATUALIZA_CADASTRO,
    STATUS_DONE,
    STATUS_QUEUED,
    ProcessingJob,
)

_TABELAS = [Empresa.__table__, ProcessingJob.__table__]


# ── Mapeamento (função pura) ────────────────────────────────────────────────

def test_montar_atualizacao_so_aplica_valor_preenchido():
    campos = montar_atualizacao({
        "razao_social": "NOVA RAZAO LTDA", "nome_fantasia": "", "uf": "SP",
        "municipio": None, "cep": " 38740-000 ",
    })
    assert campos == {"razao_social": "NOVA RAZAO LTDA", "uf": "SP", "cep": "38740-000"}


def test_montar_atualizacao_regime_so_quando_confirmado():
    assert montar_atualizacao({"regime": "Simples Nacional"})["regime"] == "Simples Nacional"
    assert montar_atualizacao({"regime": "MEI"})["regime"] == "MEI"
    # "Normal" não distingue Presumido de Real → não sobrescreve a escolha do escritório.
    assert "regime" not in montar_atualizacao({"regime": "Normal"})


def test_montar_atualizacao_trunca_no_limite_da_coluna():
    assert len(montar_atualizacao({"razao_social": "X" * 300})["razao_social"]) == 200


def test_intervalo_cresce_com_o_lote():
    assert intervalo_lote(30) == 1.0
    assert intervalo_lote(31) == 2.0
    assert intervalo_lote(120) == 2.0
    assert intervalo_lote(500) == 3.0


# ── Lote (sessão por empresa + job de progresso) ────────────────────────────

@pytest_asyncio.fixture
async def ambiente():
    # StaticPool: o lote abre uma sessão POR EMPRESA; em :memory: cada conexão
    # nova seria um banco novo — o pool estático compartilha a única conexão.
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    fabrica = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def sessao_factory():
        async with fabrica() as s, s.begin():
            yield s

    yield fabrica, sessao_factory
    await engine.dispose()


async def test_lote_atualiza_avisa_e_registra_progresso(ambiente):
    fabrica, sessao_factory = ambiente
    tid, job_id = uuid4(), uuid4()
    respostas = {
        "11444777000161": {"ok": True, "error": None, "dados": {
            "razao_social": "ACME COMERCIO E SERVICOS LTDA", "uf": "SP",
            "municipio": "Campinas", "regime": "", "situacao": "Ativa",
        }},
        "04640241000156": {"ok": True, "error": None, "dados": {
            "razao_social": "SOL CONSULTORIA LTDA",
            "regime": "Simples Nacional", "situacao": "Baixada",
        }},
        "97837181000147": {"ok": False, "error": "CNPJ não encontrado", "dados": {}},
    }
    async with sessao_factory() as s:
        s.add_all([
            Empresa(id=uuid4(), tenant_id=tid, cnpj=c, razao_social=f"ANTIGA {c}",
                    regime="Lucro Presumido", uf="MG")
            for c in respostas
        ])
        # Empresa de OUTRO tenant: o lote não pode encostar nela.
        s.add(Empresa(id=uuid4(), tenant_id=uuid4(), cnpj="11444777000161",
                      razao_social="DE OUTRO ESCRITORIO"))
        s.add(ProcessingJob(id=job_id, tenant_id=tid, user_id=uuid4(),
                            kind=KIND_ATUALIZA_CADASTRO, status=STATUS_QUEUED))

    pausas = []

    async def dormir(seg):
        pausas.append(seg)

    resumo = await atualizar_cadastros_lote(
        tid, job_id, sessao_factory=sessao_factory,
        consultar=lambda cnpj, ctx: respostas[cnpj], dormir=dormir,
    )

    assert resumo["total"] == 3 and resumo["atualizadas"] == 2
    assert resumo["falhas"] == [{"cnpj": "97.837.181/0001-47",
                                 "razao_social": "ANTIGA 97837181000147",
                                 "erro": "CNPJ não encontrado"}]
    assert [a["situacao"] for a in resumo["avisos"]] == ["Baixada"]
    assert pausas == [intervalo_lote(3)] * 2          # pausa ENTRE consultas (n-1)

    async with fabrica() as s:
        acme = await s.scalar(select(Empresa).where(
            Empresa.tenant_id == tid, Empresa.cnpj == "11444777000161"))
        assert acme.razao_social == "ACME COMERCIO E SERVICOS LTDA"
        assert acme.uf == "SP" and acme.municipio == "Campinas"
        assert acme.regime == "Lucro Presumido"       # "" da Receita NÃO apaga

        sol = await s.scalar(select(Empresa).where(Empresa.cnpj == "04640241000156"))
        assert sol.regime == "Simples Nacional"       # confirmado → atualiza

        alheia = await s.scalar(select(Empresa).where(
            Empresa.razao_social == "DE OUTRO ESCRITORIO"))
        assert alheia.uf is None                      # outro tenant: intocada

        job = await s.get(ProcessingJob, job_id)
        assert job.status == STATUS_DONE
        assert job.total == 3 and job.processed == 3
        assert job.result["atualizadas"] == 2


async def test_lote_pula_cpf_e_cei(ambiente):
    """CPF (produtor rural) e CEI (obra) não têm consulta pública: saem do
    lote SEM contar como falha e sem gastar pausa de API."""
    fabrica, sessao_factory = ambiente
    tid, job_id = uuid4(), uuid4()
    async with sessao_factory() as s:
        s.add(Empresa(id=uuid4(), tenant_id=tid, cnpj="11144477735",
                      razao_social="JOSE DA SILVA (PRODUTOR RURAL)"))
        s.add(Empresa(id=uuid4(), tenant_id=tid, cnpj="123456789010",
                      razao_social="OBRA SEDE ACME (CEI)"))
        s.add(Empresa(id=uuid4(), tenant_id=tid, cnpj="11444777000161",
                      razao_social="ACME LTDA"))
        s.add(ProcessingJob(id=job_id, tenant_id=tid, user_id=uuid4(),
                            kind=KIND_ATUALIZA_CADASTRO, status=STATUS_QUEUED))

    consultados = []

    def consultar(cnpj, ctx):
        consultados.append(cnpj)
        return {"ok": True, "error": None, "dados": {"razao_social": "ACME NOVA LTDA"}}

    async def dormir(seg):
        pass

    resumo = await atualizar_cadastros_lote(
        tid, job_id, sessao_factory=sessao_factory,
        consultar=consultar, dormir=dormir,
    )

    assert consultados == ["11444777000161"]      # CPF e CEI nunca vão à API
    assert resumo["sem_consulta"] == 2 and resumo["atualizadas"] == 1
    assert not resumo["falhas"]
    async with fabrica() as s:
        job = await s.get(ProcessingJob, job_id)
        assert job.processed == 3 and job.status == STATUS_DONE


async def test_429_espera_e_tenta_de_novo(ambiente):
    fabrica, sessao_factory = ambiente
    tid, job_id = uuid4(), uuid4()
    async with sessao_factory() as s:
        s.add(Empresa(id=uuid4(), tenant_id=tid, cnpj="11444777000161",
                      razao_social="ANTIGA LTDA"))
        s.add(ProcessingJob(id=job_id, tenant_id=tid, user_id=uuid4(),
                            kind=KIND_ATUALIZA_CADASTRO, status=STATUS_QUEUED))

    chamadas = []

    def consultar(cnpj, ctx):
        chamadas.append(cnpj)
        if len(chamadas) == 1:
            return {"ok": False, "error": "Erro HTTP 429", "dados": {}}
        return {"ok": True, "error": None,
                "dados": {"razao_social": "DEPOIS DO 429 LTDA"}}

    pausas = []

    async def dormir(seg):
        pausas.append(seg)

    resumo = await atualizar_cadastros_lote(
        tid, job_id, sessao_factory=sessao_factory,
        consultar=consultar, dormir=dormir,
    )

    assert len(chamadas) == 2                         # 429 → espera longa → repete
    assert pausas == [PAUSA_RATE_LIMIT]
    assert resumo["atualizadas"] == 1 and not resumo["falhas"]
