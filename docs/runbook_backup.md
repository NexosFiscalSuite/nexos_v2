# Runbook — Backup & Restore (Produção)

Procedimento de backup automatizado e recuperação de desastre do banco
PostgreSQL do Nexos Fiscal Suite V2.

> **Por que isso importa:** os dados são fiscais (notas, itens, auditorias de
> ICMS-ST) com exigência legal de retenção. Perder o volume do Postgres sem
> backup = perda irreversível + risco de compliance.

---

## Objetivos (RPO / RTO)

| Métrica | Alvo | Significado |
|---------|------|-------------|
| **RPO** (Recovery Point Objective) | ≤ 24 h | Perda máxima aceitável: 1 dia (backup diário). Para RPO menor, use PITR/WAL. |
| **RTO** (Recovery Time Objective) | ≤ 1 h | Tempo máximo para restaurar o serviço a partir do backup. |
| **Retenção** | 30 dias diários + 12 meses mensais | Ajuste conforme a política fiscal do escritório. |

---

## Estratégia recomendada

1. **Preferencial — Postgres gerenciado** (RDS / Cloud SQL / Neon): habilite
   **backup automático + Point-In-Time Recovery (PITR)** e snapshots. Menos
   código para manter, RPO de minutos. **Esta é a opção recomendada para prod.**
2. **Self-hosted** (Docker/VM): `pg_dump` diário cifrado, enviado para storage
   **offsite** (S3/bucket separado do servidor). É o que o cronjob abaixo cobre.

> Backup **na mesma máquina/volume** do banco não conta — um incidente de disco
> leva os dois juntos. Sempre replique para fora do servidor.

---

## Cronjob diário com `pg_dump` (self-hosted)

### Opção A — serviço no `docker-compose.yml`

Acople este serviço ao seu compose de produção. Ele roda `pg_dump` todo dia às
02:00, comprime, e mantém os últimos 30 arquivos.

```yaml
  backup:
    image: postgres:16-alpine          # mesma major do banco (pg_dump compatível)
    restart: unless-stopped
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      PGHOST: postgres
      PGUSER: nexos
      PGDATABASE: nexos
      PGPASSWORD: ${POSTGRES_PASSWORD}  # injete via secret/.env, nunca hardcoded
    volumes:
      - ./backups:/backups
    entrypoint: ["sh", "-c"]
    command:
      - |
        echo "0 2 * * * sh /backup.sh >> /backups/backup.log 2>&1" > /etc/crontabs/root
        cat > /backup.sh <<'EOF'
        #!/bin/sh
        set -e
        TS=$(date +%Y%m%d_%H%M%S)
        OUT="/backups/nexos_${TS}.sql.gz"
        pg_dump --format=custom --no-owner --no-privileges | gzip > "$OUT"
        # Retenção: mantém os 30 backups mais recentes
        ls -1t /backups/nexos_*.sql.gz | tail -n +31 | xargs -r rm -f
        echo "[$(date)] backup OK -> $OUT"
        EOF
        chmod +x /backup.sh
        crond -f -l 2
```

> **Importante:** depois que o cron gravar em `./backups`, sincronize a pasta para
> **fora do servidor** (ex.: `aws s3 sync ./backups s3://nexos-backups/` num cron do
> host, ou um sidecar). O dump local é só o primeiro hop.

### Opção B — crontab direto no servidor (sem Docker)

```bash
# crontab -e  (no host de produção)
0 2 * * * PGPASSWORD="$POSTGRES_PASSWORD" pg_dump -h localhost -U nexos -d nexos \
  --format=custom --no-owner --no-privileges \
  | gzip > /var/backups/nexos/nexos_$(date +\%Y\%m\%d).sql.gz \
  && find /var/backups/nexos -name 'nexos_*.sql.gz' -mtime +30 -delete \
  && aws s3 sync /var/backups/nexos s3://nexos-backups/   # offsite
```

### Verificação (não confie em backup que você nunca restaurou)

- Mensalmente, **restaure o último dump num banco descartável** e rode
  `make go-live-check` apontado para ele. Backup sem teste de restore é teatro.
- Monitore `backup.log` / alerte se um dia não gerar arquivo novo.

---

## Restore (recuperação de desastre)

O dump usa formato `custom` (`-F c`), restaurado com `pg_restore`.

```bash
# 1) Provisione um Postgres limpo (container ou instância nova) e as roles:
#    docker compose up -d postgres   # roda docker/postgres-init.sql (cria nexos_app)

# 2) (Se necessário) recrie o banco vazio
psql -h <host> -U nexos -c "DROP DATABASE IF EXISTS nexos;"
psql -h <host> -U nexos -c "CREATE DATABASE nexos;"

# 3) Restaure o último backup bom
gunzip -c nexos_20260626.sql.gz | pg_restore -h <host> -U nexos -d nexos --no-owner --no-privileges

# 4) Confirme migrações no head e a postura de segurança
cd backend && make go-live-check
```

### Checklist pós-restore

- [ ] `alembic current` == head (inclui `0020_force_rls`).
- [ ] RLS + FORCE ativos em todas as tabelas tenant (o `go-live-check` valida).
- [ ] Role `nexos_app` existe e **não** tem superuser/bypassrls.
- [ ] Smoke test: login + listar empresas de 1 tenant retorna só os dados dele.
- [ ] **Rotacione segredos** se houver suspeita de que o incidente expôs o backup.

---

## Resumo operacional

| Item | Valor |
|------|-------|
| Frequência | Diária (02:00) |
| Ferramenta | `pg_dump -F c` + gzip |
| Local primário | `./backups` (volume) |
| Local offsite | bucket S3 separado (`s3://nexos-backups`) |
| Retenção | 30 diários (+ mensais se exigido) |
| Teste de restore | Mensal, em banco descartável |
| Senha do banco | via secret/env — **nunca** no YAML versionado |
