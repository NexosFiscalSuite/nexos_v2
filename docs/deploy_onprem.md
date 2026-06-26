# Deploy On-Prem — Servidor do Escritório

Como subir o Nexos Fiscal Suite V2 num servidor local do escritório, acessível
de qualquer lugar **sem VPN no PC do usuário** e **sem abrir porta no roteador**,
usando Cloudflare Tunnel.

**Domínio:** `contabilidadesol.com.br` · **Acesso:** `https://app.contabilidadesol.com.br`

```
Usuário (qualquer lugar) ─ https://app.contabilidadesol.com.br ─▶ Cloudflare (TLS)
                                                              │  Tunnel (saída)
                                                              ▼
   Servidor do escritório:  cloudflared ─▶ caddy ─┬─ /api/* ─▶ api (FastAPI)
                                                   └─ resto  ─▶ SPA (frontend/dist)
                            postgres · redis · minio · worker  (só rede interna)
```

---

## 0. Pré-requisitos

- Servidor: **Ubuntu Server LTS**, 4 cores / 8–16 GB RAM / SSD, **no-break (UPS)**.
- **Docker + Docker Compose** e **git** instalados.
- Domínio `contabilidadesol.com.br` registrado no **registro.br**.
- Conta **Cloudflare** (free) com o domínio adicionado (DNS gerido pela Cloudflare).

---

## 1. Apontar o domínio para a Cloudflare

> ⚠️ **ATENÇÃO — domínio em uso.** `contabilidadesol.com.br` já é o domínio do
> escritório e provavelmente tem **e-mail (registros MX)** e talvez um **site**.
> Mover os nameservers para a Cloudflare transfere TODO o DNS — se os registros
> atuais não forem replicados, **o e-mail e o site param**.
>
> Antes de trocar os nameservers:
> 1. No painel atual (registro.br ou onde o DNS está hoje), **anote todos os
>    registros**: A, CNAME, **MX** (e-mail), TXT (SPF/DKIM), etc.
> 2. Ao adicionar o site na Cloudflare, ela faz um *scan* e importa o que achar —
>    **confira** se MX e os registros de site vieram corretos.
> 3. Só então troque os nameservers. Mantenha esses registros (a Cloudflare só
>    "intermedia" o app via o subdomínio `app.`; o resto continua resolvendo igual).
>
> Se preferir **não mexer no DNS atual**, a alternativa é manter o caminho 100%
> grátis sem domínio próprio para o app (Tailscale Funnel `…ts.net`), deixando o
> `contabilidadesol.com.br` intocado. Mas o ideal é usar `app.contabilidadesol.com.br`.

1. Em **dash.cloudflare.com** → *Add a site* → `contabilidadesol.com.br` (plano Free).
2. **Confira os registros importados** (especialmente MX/e-mail) — ver aviso acima.
3. A Cloudflare mostra 2 **nameservers** (ex.: `xxx.ns.cloudflare.com`).
4. No **registro.br** → seu domínio → *Alterar servidores DNS* → cole os 2 da Cloudflare.
5. Aguarde a propagação (minutos a algumas horas).

---

## 2. Clonar o repositório no servidor

O repo é **privado** (org NexosFiscalSuite) — autentique com uma **deploy key** SSH
(read-only) ou um **PAT fine-grained**.

```bash
git clone https://github.com/NexosFiscalSuite/nexos_v2.git
cd nexos_v2/backend
```

> Nada do desenvolvimento fica "preso" no seu notebook: a fonte da verdade é o
> GitHub. O servidor só clona e sobe.

---

## 3. Criar o `.env` de produção

O `.env` **não** vem do git (está no `.gitignore`, de propósito). Crie a partir do
exemplo e preencha com **segredos fortes**:

```bash
cp .env.example .env
```

Gere segredos:
```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"   # JWT
python -c "import secrets; print(secrets.token_urlsafe(24))"   # senhas de DB/S3
```

Variáveis obrigatórias no `.env` (produção):

```ini
NEXOS_ENVIRONMENT=production
NEXOS_JWT_SECRET=<token forte de 64+ chars>

# Senhas do banco (a do app e a do superuser precisam ser FORTES)
POSTGRES_PASSWORD=<senha forte do superuser 'nexos'>
NEXOS_APP_DB_PASSWORD=<senha forte da role 'nexos_app'>

# Storage (MinIO) — credenciais fortes
MINIO_ROOT_USER=<usuario forte>
MINIO_ROOT_PASSWORD=<senha forte>
NEXOS_S3_ACCESS_KEY=<mesmo do MINIO_ROOT_USER>
NEXOS_S3_SECRET_KEY=<mesmo do MINIO_ROOT_PASSWORD>

# CORS (mesma origem; mantido por segurança)
NEXOS_CORS_ORIGINS=https://app.contabilidadesol.com.br

# Cloudflare Tunnel (preenchido no passo 4)
CLOUDFLARE_TUNNEL_TOKEN=
```

> O `prod-set-app-password.sh` aplica `NEXOS_APP_DB_PASSWORD` à role `nexos_app`
> na primeira inicialização do banco — fechando a brecha da senha default de dev.
> O `preflight` da app **recusa subir** se qualquer um desses estiver fraco.

---

## 4. Criar o Cloudflare Tunnel

1. **dash.cloudflare.com** → *Zero Trust* → *Networks* → *Tunnels* → *Create a tunnel*.
2. Tipo **Cloudflared**, dê um nome (ex.: `nexos-escritorio`).
3. Copie o **token** exibido e cole em `CLOUDFLARE_TUNNEL_TOKEN=` no `.env`.
4. Em *Public Hostnames* → *Add a public hostname*:
   - **Subdomain:** `app` · **Domain:** `contabilidadesol.com.br`
   - **Service:** `HTTP` → `caddy:80`
5. Salve. (O `cloudflared` roda como contêiner no compose e se conecta sozinho.)

---

## 5. Build do frontend

O Caddy serve os arquivos estáticos de `frontend/dist`:

```bash
cd ../frontend
npm ci
npm run build          # gera frontend/dist
cd ../backend
```

---

## 6. Subir tudo

```bash
# a partir de backend/
docker compose -f docker-compose.prod.yml up -d --build
```

Isso: provisiona Postgres (com senha forte no `nexos_app`), Redis, MinIO, roda
`alembic upgrade head`, sobe API + worker, Caddy e o túnel.

### Verificação de go-live (portão de segurança)
```bash
docker compose -f docker-compose.prod.yml exec api python -m scripts.go_live_check
```
Só siga se imprimir **✅ APROVADO** (valida migrações no head, JWT/segredos fortes,
RLS+FORCE e role do app sem bypass).

Acesse: **https://app.contabilidadesol.com.br** 🎉

---

## 7. Backup diário (com OneDrive)

1. Garanta que a pasta de backup fica **dentro do diretório sincronizado pelo OneDrive**
   no servidor (ex.: `/mnt/onedrive/nexos-backups`).
2. Agende o cron (rode a partir de `backend/`):

```bash
crontab -e
```
```cron
0 2 * * * cd /caminho/para/nexos_v2/backend && BACKUP_DIR=/mnt/onedrive/nexos-backups sh scripts/backup.sh >> /var/log/nexos-backup.log 2>&1
```

Regras de ouro (ver também [runbook_backup.md](runbook_backup.md)):
- ✅ Sincronize **os dumps** (`.sql.gz`), **nunca** o volume vivo `pgdata`.
- ✅ Mantenha **30 dias** (o script já faz) — protege contra ransomware sincronizado.
- 💡 Opcional: defina `AGE_RECIPIENT` no ambiente do cron para **cifrar** o dump
  antes de ir ao OneDrive.
- 🔁 **Teste o restore** mensalmente (ver runbook).

---

## 8. Atualizações futuras

```bash
cd nexos_v2 && git pull
cd frontend && npm ci && npm run build
cd ../backend && docker compose -f docker-compose.prod.yml up -d --build
```

---

## Notas

- **Tráfego interno + externo** passa pelo mesmo `https://app.contabilidadesol.com.br`
  (via Cloudflare). Simples e sempre com TLS. Se quiser acesso LAN direto (mais
  rápido in-office) depois, dá para expor o Caddy na rede local — otimização opcional.
- **Nada exposto ao roteador/internet** além do túnel de saída do `cloudflared`.
- **Postgres/Redis/MinIO** não têm portas publicadas — só a rede interna do compose
  (o console do MinIO fica em `127.0.0.1:9001`, acessível via SSH tunnel para admin).
- A segurança que blindamos (JWT, rate limit, RLS+FORCE, HSTS/CSP, limites de upload)
  é o que torna seguro expor a API publicamente pelo túnel.
