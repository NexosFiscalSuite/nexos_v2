# Nexos Fiscal Suite V2 — Backend

SaaS multi-tenant para escritórios de contabilidade. FastAPI + PostgreSQL (RLS) +
Redis + Celery. Clean Architecture / DDD por bounded context.

> Repo novo (cloud-native). O projeto legado em `Nexos_FiscalSuite/backend` serve
> só como referência das regras de negócio fiscais.

## O que já existe

**Fase 2 — Setup, Auth, RLS, Rate Limiting**
- **Core**: config (env), engines async (app + privilegiada), segurança (Argon2 +
  JWT), RLS por transação, RBAC (admin/supervisor/user), rate limiting por tenant.
- **Módulo `identity`**: `tenants`, `users`, `plans`, `refresh_tokens`; signup de
  escritório, login (com rotação de refresh), `/me`, gestão de usuários.

**Fase 3 — Filas Assíncronas e Regras de Negócio**
- **Celery + Redis** + tabela `processing_jobs` (rastreio de progresso/resultado).
- **Storage de XML por tenant** (`core/storage.py`): backend `local` (dev) ou `s3`/MinIO.
- **Módulo `companies`**: empresas-cliente do escritório.
- **Módulo `fiscal`**: parser portado do V1 (NF-e/NFC-e/CT-e/NFS-e ABRASF+Nacional +
  eventos de cancelamento), classificação de fluxo, e **importação assíncrona**
  (upload → staging → fila → parse → persiste sob RLS). `notas`/`nota_itens`/`nota_eventos`.
- **Módulo `compliance`**: detecção de quebra de sequência + ciência.
- **Módulo `reporting`**: modelos de relatório + geração assíncrona de Excel + download.

### Fluxo de importação assíncrona

```
POST /fiscal/empresas/{id}/upload   ── API grava XMLs no staging, cria job, enfileira
        │                              (responde 202 + job_id, sem travar)
        ▼
   Celery worker  ── lê staging → parse_xml → classifica fluxo → grava XML final →
        │            insere notas (RLS) → atualiza job (running → done)
        ▼
GET /jobs/{job_id}  ── frontend faz polling do status/resultado (base da Fase 4)
```

## Pré-requisitos

- **Python 3.12 ou 3.13** (use 3.13). **Evite 3.14 por ora**: ainda faltam wheels
  pré-compiladas de `asyncpg` e `pydantic-core` para cp314, e o pip tentaria
  compilar do zero (exigiria MSVC C++ Build Tools + Rust).
- Docker (para Postgres, Redis e MinIO) — ou um Postgres/Redis locais.

## Subindo em desenvolvimento

> **Rode tudo de dentro de `backend/`** — é onde ficam `docker-compose.yml`,
> `pyproject.toml` e `alembic.ini`.

```bash
cd backend                           # a partir da raiz do repo nexos_v2/
cp .env.example .env                 # ajuste NEXOS_JWT_SECRET

# 1) Infra (Postgres cria as roles via docker/postgres-init.sql)
docker compose up -d postgres redis minio

# 2) Dependências
python -m venv .venv
pip install -e ".[dev]"

# 3) Migrações (rodam com a role privilegiada)
alembic upgrade head

# 4) API
uvicorn app.main:app --reload

# 5) Worker Celery (OUTRO terminal, com o venv ativado) — processa a fila
celery -A app.core.celery_app:celery_app worker --loglevel=info --queues nexos --pool=solo
```

> No Windows, use `--pool=solo` (ou `--pool=threads`) no worker — o pool padrão
> (prefork) não funciona bem no Windows. Em produção (Linux), remova essa flag.
> Em dev, `NEXOS_STORAGE_BACKEND=local` exige que API e worker rodem na MESMA
> máquina (compartilham o disco). Com MinIO/S3, podem ser separados.

**Ativação do venv depende do shell** (passo 2, antes do `pip install`):

| Shell | Comando |
|-------|---------|
| Git Bash (MINGW64) | `source .venv/Scripts/activate` |
| PowerShell | `.venv\Scripts\Activate.ps1` |
| CMD | `.venv\Scripts\activate.bat` |
| Linux/macOS | `source .venv/bin/activate` |

Gerar um JWT secret forte: `python -c "import secrets; print(secrets.token_urlsafe(64))"`

Docs interativas: http://localhost:8000/docs · Health: http://localhost:8000/health

## Modelo de isolamento (RLS) — resumo

- Toda tabela tenant-scoped tem `tenant_id`; as policies filtram por
  `current_setting('app.current_tenant')`.
- A API conecta como **`nexos_app`** (não-owner, **sujeita** a RLS).
- **Migrações e auth** usam a role privilegiada (**BYPASSRLS**): signup cria o
  tenant e o login acha o usuário antes de existir contexto.
- Por request, `tenant_session` abre uma transação e executa
  `SELECT set_config('app.current_tenant', <tid>, true)` — daí toda query já sai
  filtrada pelo banco.

## Testes

```bash
pytest            # unitários (CNPJ, senha, JWT, RBAC) — não precisam de banco
```
Testes de integração de RLS (provar que um tenant não lê dados de outro) entram
com testcontainers na Fase 3.

## Fluxo rápido da API

```bash
# 1) Signup (cria escritório + admin, já retorna tokens)
curl -X POST localhost:8000/api/v1/auth/register -H 'Content-Type: application/json' -d '{
  "cnpj":"11.444.777/0001-61","razao_social":"Escritório Exemplo",
  "slug":"exemplo","admin_email":"admin@exemplo.com",
  "admin_full_name":"Admin","admin_password":"senha-forte-123","plan_code":"trial"}'

# 2) Login
curl -X POST localhost:8000/api/v1/auth/login -H 'Content-Type: application/json' -d '{
  "email":"admin@exemplo.com","password":"senha-forte-123"}'

# 3) Usar o access_token
curl localhost:8000/api/v1/auth/me -H 'Authorization: Bearer <access_token>'
```

## Estrutura

```
app/
  core/        config, database, security, rls, rbac, rate_limit, exceptions, logging
  shared/      value objects fiscais (CNPJ; demais na Fase 3)
  modules/
    identity/  domain → application → infrastructure → api
  migrations/  Alembic (env async + versions)
tests/
```
