PY = ./.venv/Scripts/python.exe

.PHONY: up down migrate seed-matrizes seed-demo seed-pg test lint

up:                ## Sobe Postgres + Redis (dev)
	docker compose up -d postgres redis

down:              ## Derruba os containers
	docker compose down

migrate:           ## Aplica as migrations (alembic upgrade head)
	$(PY) -m alembic upgrade head

seed-matrizes:     ## Carrega as matrizes fiscais (MVA/enquadramento/FCP) no banco
	$(PY) scripts/seed_matrizes.py

seed-demo:         ## Cria o tenant/login + a nota da autopeça e roda a auditoria
	$(PY) scripts/seed_demo.py

# Alvo único para preparar o Postgres de dev do zero:
# migrations + matrizes (NCMs de laboratório, ex.: 87082919 SP->MG 71,78%) + demo.
seed-pg: migrate seed-matrizes seed-demo  ## Prepara o Postgres de dev completo

test:              ## Roda a suíte
	$(PY) -m pytest -q

lint:              ## Ruff
	./.venv/Scripts/ruff.exe check app scripts tests
