# Nexos Fiscal Suite V2

**SaaS multi-tenant de Auditoria Fiscal** para escritórios de contabilidade.
Importa XMLs fiscais (NF-e / NFC-e / CT-e / NFS-e), classifica fluxos, audita
ICMS-ST e gera relatórios — com **isolamento de dados por tenant garantido no
banco** (PostgreSQL Row-Level Security) e RBAC.

| Camada | Stack |
|--------|-------|
| Backend | FastAPI · PostgreSQL (RLS) · Redis · Celery · SQLAlchemy async · Alembic |
| Frontend | React · TypeScript · Vite |
| Segurança | JWT (HS256) · Argon2 · RLS + `FORCE ROW LEVEL SECURITY` · rate limiting por tenant |

> Monorepo: o backend fica em [`backend/`](backend/) e o frontend em
> [`frontend/`](frontend/). Cada um tem um README com detalhes adicionais.

---

## Pré-requisitos

- **Python 3.13** (evite 3.14 — faltam wheels de `asyncpg`/`pydantic-core`)
- **Node 18+** (frontend)
- **Docker** (Postgres, Redis e MinIO) — ou instâncias locais equivalentes

---

## Backend — instalar, testar e rodar

Todos os comandos rodam **de dentro de `backend/`** (lá ficam `pyproject.toml`,
`alembic.ini` e `docker-compose.yml`).

```bash
cd backend
cp .env.example .env          # ajuste NEXOS_JWT_SECRET (gere um forte, veja abaixo)

# 1) Infra
docker compose up -d postgres redis minio

# 2) Dependências (ambiente virtual)
python -m venv .venv
source .venv/Scripts/activate     # Git Bash;  PowerShell: .venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 3) Migrações
alembic upgrade head

# 4) Rodar a API (http://localhost:8000/docs)
uvicorn app.main:app --reload

# 5) Worker Celery (outro terminal, venv ativado)
celery -A app.core.celery_app:celery_app worker --loglevel=info --queues nexos --pool=solo
```

Gerar um `NEXOS_JWT_SECRET` forte:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Rodar os testes

```bash
cd backend
pytest            # ou: make test
```

### Git hooks (proteção local da `main`)

O repositório versiona um hook `pre-push` em [`.githooks/`](.githooks/pre-push) que
bloqueia force-push/deleção da `main` e roda `ruff`+`pytest` antes de qualquer push
que a afete. Ative-o **uma vez por clone**:

```bash
git config core.hooksPath .githooks
```
> Emergência: `git push --no-verify` pula o hook (use com consciência).

### Checagem de go-live (produção)

```bash
cd backend
make go-live-check     # valida migrações no head, JWT forte, RLS+FORCE e role do app
```

---

## Frontend — instalar e rodar

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

---

## Isolamento de dados (resumo)

- Toda tabela tenant-scoped tem `tenant_id` + policy de RLS com `USING` **e**
  `WITH CHECK`, e `FORCE ROW LEVEL SECURITY` (vale até para o owner).
- A API conecta como `nexos_app` — role **não-owner, sujeita a RLS**. A role
  privilegiada (BYPASSRLS) é usada só por migrações e autenticação.
- A cada request, `tenant_session` injeta o tenant via
  `set_config('app.current_tenant', <tid>, true)` — toda query já sai filtrada
  pelo banco (fail-closed: sem contexto, nenhuma linha casa).

Detalhes em [`backend/README.md`](backend/README.md).
