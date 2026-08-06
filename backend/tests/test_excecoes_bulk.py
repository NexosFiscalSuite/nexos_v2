"""Exceções de Item em lote: planilha por empresa e por FORNECEDOR.

O que estes testes travam:
- o `tenant_id` NUNCA vem da planilha (regra 1 do CLAUDE.md) — mesmo que alguém
  acrescente a coluna à mão;
- a empresa entra por CNPJ e CNPJ desconhecido vira erro DE LINHA, nunca
  cadastro novo e nunca lote derrubado;
- o mesmo código de produto convive com dois fornecedores (é o motivo de a
  coluna existir);
- linha com `tributado_icms` em branco é IGNORADA — nada entra por omissão;
- a lista de candidatos sai no MESMO cabeçalho do importador.
"""
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.companies.infrastructure.models import Empresa
from app.modules.fiscal.api.excecoes_bulk import (
    COLUNAS_CSV_EXCECOES,
    candidatos_csv,
    candidatos_excecao,
    spec_excecoes,
)
from app.modules.fiscal.infrastructure.models import (
    AuditoriaIcmsSt,
    ExcecaoEnquadramentoStProduto,
    Nota,
    NotaItem,
)
from app.shared.bulk_csv import exportar_csv, importar_csv

_TABELAS = [
    Empresa.__table__, ExcecaoEnquadramentoStProduto.__table__,
    Nota.__table__, NotaItem.__table__, AuditoriaIcmsSt.__table__,
]

# Documentos reais (DV válido) — o schema recusa qualquer coisa fora disso.
ACME = "11444777000161"
SOL = "04640241000156"
FORN_A = "45543915000181"
FORN_B = "33000167000101"
CABECALHO = ";".join(COLUNAS_CSV_EXCECOES)


@pytest_asyncio.fixture
async def sessao():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABELAS)
    async with async_sessionmaker(engine, class_=AsyncSession)() as s:
        yield s
    await engine.dispose()


def _csv(linhas: list[str], cabecalho: str = CABECALHO) -> bytes:
    return ("\n".join([cabecalho, *linhas])).encode("utf-8")


async def _empresas(s: AsyncSession, tenant):
    acme = Empresa(id=uuid4(), tenant_id=tenant, cnpj=ACME, razao_social="ACME LTDA")
    sol = Empresa(id=uuid4(), tenant_id=tenant, cnpj=SOL, razao_social="SOL LTDA")
    s.add_all([acme, sol])
    await s.flush()
    return acme, sol


async def test_cabecalho_e_contrato_com_a_tela(sessao):
    """O cabeçalho é contrato com o front — a ordem das colunas é fechada."""
    assert list(COLUNAS_CSV_EXCECOES) == [
        "cnpj_empresa", "cnpj_fornecedor", "codigo_produto", "descricao_produto",
        "ncm", "tributado_icms", "lei_icms", "data_inicio_vigencia",
        "data_fim_vigencia", "ativo",
    ]
    assert "tenant_id" not in COLUNAS_CSV_EXCECOES
    assert "empresa_id" not in COLUNAS_CSV_EXCECOES     # ninguém digita UUID


async def test_export_de_base_vazia_e_so_o_cabecalho(sessao):
    spec = await spec_excecoes(sessao, uuid4())
    texto = await exportar_csv(sessao, spec)
    assert texto.splitlines() == [CABECALHO]            # template pronto para uso


async def test_import_cria_e_faz_upsert_sem_duplicar(sessao):
    tenant = uuid4()
    acme, _ = await _empresas(sessao, tenant)

    r = await importar_csv(sessao, await spec_excecoes(sessao, tenant, autor="ana"), _csv([
        f"{ACME};{FORN_A};7891;CAFE TORRADO 500G;09011110;SIM;Art. 111;2026-01-01;;SIM",
    ]))
    assert r["inseridos"] == 1 and r["atualizados"] == 0 and not r["erros"]

    linha = await sessao.scalar(select(ExcecaoEnquadramentoStProduto))
    assert linha.tenant_id == tenant and linha.empresa_id == acme.id
    assert linha.cnpj_fornecedor == FORN_A and linha.codigo_produto == "7891"
    assert linha.tributado_icms is True and linha.definido_por == "ana"
    assert linha.data_inicio_vigencia == date(2026, 1, 1)

    # Reimportar a MESMA chave atualiza no lugar — o lote é idempotente.
    r2 = await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};{FORN_A};7891;CAFE TORRADO 1KG;09011110;NAO;;2026-01-01;;SIM",
    ]))
    assert r2["inseridos"] == 0 and r2["atualizados"] == 1
    assert await sessao.scalar(
        select(func.count()).select_from(ExcecaoEnquadramentoStProduto)
    ) == 1
    await sessao.refresh(linha)
    assert linha.descricao_produto == "CAFE TORRADO 1KG" and linha.tributado_icms is False


async def test_cnpj_de_empresa_inexistente_vira_erro_de_linha(sessao):
    """A empresa desconhecida não derruba o lote nem se cadastra sozinha."""
    tenant = uuid4()
    await _empresas(sessao, tenant)
    r = await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};;7891;CAFE;09011110;SIM;;2026-01-01;;SIM",
        "11222333000181;;7892;ACUCAR;17019900;SIM;;2026-01-01;;SIM",    # não cadastrada
        f"{SOL};;7893;LEITE;04012010;SIM;;2026-01-01;;SIM",
    ]))
    assert r["inseridos"] == 2
    assert len(r["erros"]) == 1 and r["erros"][0]["linha"] == 3
    assert "não está cadastrado" in r["erros"][0]["erro"]
    assert await sessao.scalar(select(func.count()).select_from(Empresa)) == 2


async def test_tenant_da_planilha_e_ignorado(sessao):
    """Coluna tenant_id na planilha é lixo: o tenant vem SEMPRE dos claims."""
    tenant, invasor = uuid4(), uuid4()
    await _empresas(sessao, tenant)
    r = await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv(
        [f"{invasor};{ACME};;7891;CAFE;09011110;SIM;;2026-01-01;;SIM"],
        cabecalho=f"tenant_id;{CABECALHO}",
    ))
    assert r["inseridos"] == 1 and not r["erros"]
    linha = await sessao.scalar(select(ExcecaoEnquadramentoStProduto))
    assert linha.tenant_id == tenant and linha.tenant_id != invasor


async def test_mesmo_codigo_com_dois_fornecedores_nao_colide(sessao):
    """O motivo de a coluna existir: dois fornecedores usam o MESMO código para
    produtos diferentes — são duas regras independentes, não um conflito."""
    tenant = uuid4()
    await _empresas(sessao, tenant)
    r = await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};{FORN_A};001;PARAFUSO (TRIBUTADO);73181500;SIM;;2026-01-01;;SIM",
        f"{ACME};{FORN_B};001;TINTA (SEGUE ST);32081010;NAO;;2026-01-01;;SIM",
        f"{ACME};;001;REGRA GERAL;;NAO;;2026-01-01;;SIM",
    ]))
    assert r["inseridos"] == 3 and not r["erros"]
    fornecedores = set((await sessao.scalars(
        select(ExcecaoEnquadramentoStProduto.cnpj_fornecedor)
    )).all())
    assert fornecedores == {FORN_A, FORN_B, ""}


async def test_tributado_em_branco_e_ignorado(sessao):
    """A planilha de candidatos vem com a coluna vazia: quem não for preenchido
    NÃO vira cadastro — nada entra por omissão."""
    tenant = uuid4()
    await _empresas(sessao, tenant)
    r = await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};{FORN_A};7891;CAFE;09011110;;;2026-01-01;;SIM",       # em branco
        f"{ACME};{FORN_A};7892;ACUCAR;17019900;SIM;;2026-01-01;;SIM",
    ]))
    assert r["inseridos"] == 1 and r["linhas_validas"] == 1
    assert len(r["ignoradas"]) == 1 and r["ignoradas"][0]["linha"] == 2
    assert "tributado_icms" in r["ignoradas"][0]["motivo"]
    assert not r["erros"]
    codigos = set((await sessao.scalars(
        select(ExcecaoEnquadramentoStProduto.codigo_produto)
    )).all())
    assert codigos == {"7892"}


async def test_sim_nao_aceita_os_jeitos_que_o_humano_escreve(sessao):
    tenant = uuid4()
    await _empresas(sessao, tenant)
    r = await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};;A1;;;SIM;;2026-01-01;;sim",
        f"{ACME};;A2;;;não;;2026-01-01;;NAO",
        f"{ACME};;A3;;;true;;2026-01-01;;false",
        f"{ACME};;A4;;;1;;2026-01-01;;0",
        f"{ACME};;A5;;;talvez;;2026-01-01;;SIM",       # não é decisão: erro de linha
    ]))
    assert r["inseridos"] == 4
    assert len(r["erros"]) == 1 and r["erros"][0]["linha"] == 6
    assert "SIM" in r["erros"][0]["erro"]

    por_codigo = {
        linha.codigo_produto: (linha.tributado_icms, linha.ativo)
        for linha in (await sessao.scalars(select(ExcecaoEnquadramentoStProduto))).all()
    }
    assert por_codigo == {
        "A1": (True, True), "A2": (False, False),
        "A3": (True, False), "A4": (True, False),
    }


async def test_vigencia_sobreposta_vira_erro_de_linha(sessao):
    """ADR-0002: duas vigências abertas para o mesmo (empresa, fornecedor,
    código) deixariam a busca do motor ambígua."""
    tenant = uuid4()
    await _empresas(sessao, tenant)
    r = await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};{FORN_A};7891;CAFE;09011110;SIM;;2026-01-01;;SIM",
        f"{ACME};{FORN_A};7891;CAFE;09011110;NAO;;2026-03-01;;SIM",
    ]))
    assert r["inseridos"] == 1
    assert len(r["erros"]) == 1 and "sobrepõe" in r["erros"][0]["erro"]


async def test_export_volta_no_formato_que_o_import_aceita(sessao):
    """Ciclo fechado: baixar, editar, subir. O que sai tem que voltar."""
    tenant = uuid4()
    await _empresas(sessao, tenant)
    await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};{FORN_A};7891;CAFE;09011110;SIM;Art. 111;2026-01-01;;SIM",
    ]))
    texto = await exportar_csv(sessao, await spec_excecoes(sessao, tenant))
    cabecalho, linha = texto.splitlines()
    assert cabecalho == CABECALHO
    campos = dict(zip(COLUNAS_CSV_EXCECOES, linha.split(";"), strict=True))
    assert campos["cnpj_empresa"] == ACME              # CNPJ, nunca o UUID
    assert campos["cnpj_fornecedor"] == FORN_A
    assert campos["tributado_icms"] == "SIM" and campos["ativo"] == "SIM"

    # Reimportar o próprio export não duplica nem quebra.
    r = await importar_csv(
        sessao, await spec_excecoes(sessao, tenant), texto.encode("utf-8")
    )
    assert r["atualizados"] == 1 and r["inseridos"] == 0 and not r["erros"]


# ── Candidatos ───────────────────────────────────────────────────────────────
def _nota(tenant, empresa_id, chave, cnpj_emit, ano="2026", mes="06"):
    return Nota(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa_id, chave_acesso=chave,
        tipo="NFe", fluxo="entrada", modelo="55", cnpj_emit=cnpj_emit,
        uf_emit="SP", uf_dest="MG", data_emissao=f"{ano}-{mes}-17", ano=ano, mes=mes,
    )


def _item(tenant, nota, n, codigo, descricao, ncm, valor):
    return NotaItem(
        id=uuid4(), tenant_id=tenant, nota_id=nota.id, numero_item=n, codigo=codigo,
        descricao=descricao, ncm=ncm, valor_produto=Decimal(valor),
    )


def _auditoria(tenant, empresa_id, nota, n, *, st: bool):
    """Linha de auditoria com (ou sem) ST calculado pelo motor."""
    return AuditoriaIcmsSt(
        id=uuid4(), tenant_id=tenant, empresa_id=empresa_id, nota_id=nota.id,
        chave_acesso=nota.chave_acesso, numero_item=n,
        vbc_st_calculado=Decimal("100") if st else Decimal("0"),
        vicms_st_calculado=Decimal("18") if st else Decimal("0"),
        status="OK",
    )


async def _carteira(s: AsyncSession):
    tenant = uuid4()
    acme, _ = await _empresas(s, tenant)
    n1 = _nota(tenant, acme.id, "1" * 44, FORN_A)
    n2 = _nota(tenant, acme.id, "2" * 44, FORN_B)
    n3 = _nota(tenant, acme.id, "3" * 44, FORN_A, mes="07")
    s.add_all([n1, n2, n3])
    s.add_all([
        # mesmo código "001" em dois fornecedores: dois candidatos distintos
        _item(tenant, n1, 1, "001", "PARAFUSO", "73181500", "1000"),
        _item(tenant, n3, 1, "001", "PARAFUSO", "73181500", "500"),
        _item(tenant, n2, 1, "001", "TINTA", "32081010", "9000"),
        # item tributado normal (sem ST no motor) — não é candidato
        _item(tenant, n1, 2, "002", "CADERNO", "48201000", "70000"),
        _auditoria(tenant, acme.id, n1, 1, st=True),
        _auditoria(tenant, acme.id, n3, 1, st=True),
        _auditoria(tenant, acme.id, n2, 1, st=True),
        _auditoria(tenant, acme.id, n1, 2, st=False),
    ])
    await s.flush()
    return tenant, acme


async def test_candidatos_agrupa_por_fornecedor_e_ordena_por_dinheiro(sessao):
    tenant, acme = await _carteira(sessao)
    linhas = await candidatos_excecao(sessao, tenant)

    assert [(x["cnpj_fornecedor"], x["codigo_produto"]) for x in linhas] == [
        (FORN_B, "001"),                       # 9.000 vem antes
        (FORN_A, "001"),                       # 1.000 + 500 em duas notas
    ]
    forn_a = linhas[1]
    assert forn_a["itens"] == 2 and forn_a["notas"] == 2 and forn_a["valor"] == 1500.0
    assert forn_a["descricao_produto"] == "PARAFUSO" and forn_a["ncm"] == "73181500"
    assert forn_a["cnpj_empresa"] == ACME
    # Sugestão de vigência = 1º dia do mês da nota mais antiga do grupo.
    assert forn_a["data_inicio_vigencia"] == "2026-06-01"
    # O item que o motor NÃO tratou como ST fica de fora, por maior que seja.
    assert all(x["codigo_produto"] != "002" for x in linhas)


async def test_candidatos_filtra_por_competencia(sessao):
    tenant, _ = await _carteira(sessao)
    linhas = await candidatos_excecao(sessao, tenant, ano="2026", mes="07")
    assert len(linhas) == 1 and linhas[0]["valor"] == 500.0


async def test_candidatos_saem_no_layout_do_import_com_a_decisao_em_branco(sessao):
    """O arquivo pergunta, não responde: sobe de volta sem editar layout e, sem
    o SIM escrito à mão, nada é cadastrado."""
    tenant, _ = await _carteira(sessao)
    texto = candidatos_csv(await candidatos_excecao(sessao, tenant))
    linhas = texto.splitlines()

    colunas = linhas[0].split(";")
    assert colunas == list(COLUNAS_CSV_EXCECOES)       # mesmo cabeçalho do import
    for linha in linhas[1:]:
        campos = dict(zip(colunas, linha.split(";"), strict=True))
        assert campos["tributado_icms"] == ""          # em branco de propósito
        assert campos["cnpj_empresa"] == ACME and campos["codigo_produto"] == "001"

    # Subir o arquivo intocado: tudo ignorado, nada cadastrado.
    r = await importar_csv(
        sessao, await spec_excecoes(sessao, tenant), texto.encode("utf-8")
    )
    assert r["inseridos"] == 0 and len(r["ignoradas"]) == 2 and not r["erros"]

    # Agora com o SIM escrito em UMA linha: só ela entra.
    decidido = [linhas[0], linhas[1].replace(";;;2026-06-01", ";SIM;;2026-06-01")]
    r2 = await importar_csv(
        sessao, await spec_excecoes(sessao, tenant),
        "\n".join(decidido).encode("utf-8"),
    )
    assert r2["inseridos"] == 1 and not r2["erros"]
    linha = await sessao.scalar(select(ExcecaoEnquadramentoStProduto))
    assert linha.tributado_icms is True and linha.cnpj_fornecedor == FORN_B


async def test_candidato_ja_cadastrado_sai_da_fila(sessao):
    """A lista é fila de trabalho: o que já foi decidido não volta a aparecer."""
    tenant, acme = await _carteira(sessao)
    await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};{FORN_B};001;TINTA;32081010;NAO;;2026-01-01;;SIM",
    ]))
    linhas = await candidatos_excecao(sessao, tenant)
    assert [x["cnpj_fornecedor"] for x in linhas] == [FORN_A]

    # Regra GENÉRICA (sem fornecedor) também tira o código da fila.
    await importar_csv(sessao, await spec_excecoes(sessao, tenant), _csv([
        f"{ACME};;001;PARAFUSO;73181500;SIM;;2026-02-01;;SIM",
    ]))
    assert await candidatos_excecao(sessao, tenant) == []
