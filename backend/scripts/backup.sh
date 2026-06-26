#!/bin/sh
# backup.sh — dump diário do Postgres para a pasta sincronizada com o OneDrive.
#
# Gera um snapshot consistente (pg_dump formato custom), comprime e mantém os 30
# mais recentes. Coloque BACKUP_DIR dentro da pasta que o OneDrive sincroniza ->
# offsite automático. NUNCA sincronize o volume vivo do Postgres (pgdata): só os
# .sql.gz gerados aqui são restauráveis.
#
# Agende no cron do SERVIDOR (rode a partir de backend/):
#   0 2 * * * cd /caminho/para/nexos_v2/backend && BACKUP_DIR=/mnt/onedrive/nexos-backups sh scripts/backup.sh >> /var/log/nexos-backup.log 2>&1
set -e

BACKUP_DIR="${BACKUP_DIR:-/mnt/onedrive/nexos-backups}"   # pasta sincronizada c/ OneDrive
COMPOSE="docker compose -f docker-compose.prod.yml"
TS=$(date +%Y%m%d_%H%M%S)
OUT="$BACKUP_DIR/nexos_${TS}.sql.gz"

mkdir -p "$BACKUP_DIR"

# Dump consistente direto do container, comprimido.
$COMPOSE exec -T postgres pg_dump -U nexos -d nexos \
    --format=custom --no-owner --no-privileges | gzip > "$OUT"

# (Opcional) cifrar para o cloud de terceiro: se AGE_RECIPIENT estiver definido,
# cifra com age e remove o .gz em claro. Requer 'age' instalado no servidor.
if [ -n "$AGE_RECIPIENT" ] && command -v age >/dev/null 2>&1; then
    age -r "$AGE_RECIPIENT" -o "$OUT.age" "$OUT" && rm -f "$OUT"
    OUT="$OUT.age"
fi

# Retenção: mantém os 30 backups mais recentes.
ls -1t "$BACKUP_DIR"/nexos_*.sql.gz* 2>/dev/null | tail -n +31 | xargs -r rm -f

# Falha o script se o arquivo final não existir ou estiver vazio (alerta no log).
[ -s "$OUT" ] || { echo "[$(date)] ERRO: backup vazio/inexistente -> $OUT" >&2; exit 1; }
echo "[$(date)] backup OK -> $OUT ($(du -h "$OUT" | cut -f1))"
