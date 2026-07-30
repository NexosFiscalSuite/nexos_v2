"""Cadastro de empresas em lote (planilha CSV): template, upsert e validação.

O tenant_id NUNCA vem da planilha — o spec injeta o do usuário logado; CNPJ é
normalizado (pontuação fora) e validado por dígito verificador linha a linha.
"""
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.companies.api.empresas_bulk import spec_empresas
from app.modules.companies.infrastructure.models import Empresa
from app.shared.bulk_csv import exportar_csv, importar_csv

_TABELAS = [Empresa.__table__]


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _csv(linhas: list[str]) -> bytes:
    cab = ("cnpj;razao_social;nome_fantasia;regime;uf;municipio;"
           "inscricao_estadual;cnae;cep;logradouro;numero;bairro")
    return ("\n".join([cab, *linhas])).encode("utf-8")


async def test_template_tem_cnpj_primeiro(sessao):
    csv_text = await exportar_csv(sessao, spec_empresas(uuid4()))
    cabecalho = csv_text.splitlines()[0].split(";")
    assert cabecalho[:2] == ["cnpj", "razao_social"]
    assert "bairro" in cabecalho and "tenant_id" not in cabecalho


async def test_import_upsert_e_validacao(sessao):
    tid = uuid4()
    conteudo = _csv([
        "11.444.777/0001-61;ACME COMERCIO LTDA;ACME;Simples Nacional;MG;Patrocínio;;;;;;",
        "04.640.241/0001-56;SOL CONSULTORIA LTDA;;Lucro Presumido;MG;;;;;;;",
        "11.111.111/1111-11;CNPJ RUIM LTDA;;;;;;;;;;",          # DV inválido
    ])
    r = await importar_csv(sessao, spec_empresas(tid), conteudo)

    assert r["inseridos"] == 2 and r["atualizados"] == 0
    assert len(r["erros"]) == 1 and r["erros"][0]["linha"] == 4
    assert "inválido" in r["erros"][0]["erro"]

    acme = await sessao.scalar(select(Empresa).where(Empresa.cnpj == "11444777000161"))
    assert acme is not None
    assert acme.tenant_id == tid                       # injetado pelo spec
    assert acme.uf == "MG" and acme.razao_social == "ACME COMERCIO LTDA"

    # Reimportar com razão social nova = ATUALIZA (upsert por CNPJ), não duplica.
    r2 = await importar_csv(sessao, spec_empresas(tid), _csv([
        "11444777000161;ACME COMERCIO E SERVICOS LTDA;;;;;;;;;;",
    ]))
    assert r2["inseridos"] == 0 and r2["atualizados"] == 1
    assert await sessao.scalar(select(func.count()).select_from(Empresa)) == 2
    await sessao.refresh(acme)
    assert acme.razao_social == "ACME COMERCIO E SERVICOS LTDA"
