#!/bin/sh
# Init de PRODUÇÃO (roda só na 1ª criação do volume, após o 10-init.sql).
#
# O 10-init.sql cria a role nexos_app com uma senha de DEV ('nexos_app'). Em
# produção isso é fraco — e o preflight da app recusaria subir. Aqui trocamos
# para a senha forte vinda do ambiente (NEXOS_APP_DB_PASSWORD), que casa com a
# usada na NEXOS_DATABASE_URL.
#
# Para volumes JÁ existentes (init não roda de novo), rode manualmente:
#   docker compose -f docker-compose.prod.yml exec postgres \
#     psql -U nexos -d nexos -c "ALTER ROLE nexos_app PASSWORD 'SUA_SENHA_FORTE';"
set -e

if [ -z "$NEXOS_APP_DB_PASSWORD" ]; then
    echo "ERRO: NEXOS_APP_DB_PASSWORD não definido — abortando init de produção." >&2
    exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
ALTER ROLE nexos_app WITH PASSWORD '${NEXOS_APP_DB_PASSWORD}';
SQL

echo "[prod-init] senha forte aplicada à role nexos_app."
