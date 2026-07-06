# Deploy no Windows Server 2025 — VM Ubuntu no Hyper-V

Como hospedar o **Sol Contabilidade (Nexos V2)** num servidor **Windows Server
2025**: a stack roda numa **VM Ubuntu Server dentro do Hyper-V** (papel nativo
do Windows). Dentro da VM, vale o guia [deploy_onprem.md](deploy_onprem.md)
sem nenhuma alteração.

## Por que uma VM (e não a stack direto no Windows)?

| Opção | Veredito |
|---|---|
| **VM Ubuntu no Hyper-V** | ✅ **Recomendada.** Docker Linux nativo; o compose, o runbook de backup e o go-live-check valem sem mudança; isolamento do host; autostart de VM é recurso de primeira classe do Hyper-V. |
| WSL2 | ⚠️ Funciona, mas WSL não foi feito para serviço de produção: auto-start após reboot sem logon exige gambiarras (tarefa agendada), e atualizações do Windows podem reiniciar o subsistema. |
| Nativo no Windows (sem Docker) | ❌ Redis não tem build oficial para Windows, o pool padrão do Celery (prefork) não roda em Windows e todo o compose/backup teria de ser reescrito. |

```
Internet ─ https://fiscal.solsistema.com.br ─▶ Cloudflare (TLS)
                                                │ Tunnel (só SAÍDA — nada aberto
                                                ▼  no firewall do Windows)
Windows Server 2025 ─ Hyper-V ─▶ VM Ubuntu: cloudflared ▶ caddy ▶ api/worker
                                            postgres · redis · minio (rede interna)
```

---

## 0. Pré-requisitos

- Windows Server 2025 com virtualização habilitada na BIOS/UEFI e **no-break (UPS)**.
- Host com folga para a VM: **4 vCPU / 8–12 GB RAM / 150 GB** de disco para ela.
- Domínio `solsistema.com.br` registrado (✅ já comprado) e conta Cloudflare (free).
- ISO do **Ubuntu Server 24.04 LTS**: <https://ubuntu.com/download/server>.

---

## 1. Instalar o Hyper-V (PowerShell como Administrador)

```powershell
Install-WindowsFeature -Name Hyper-V -IncludeManagementTools -Restart
```

Após o reboot, crie o **switch externo** (dá rede de verdade à VM — ela aparece
na LAN como uma máquina própria):

```powershell
Get-NetAdapter                       # anote o nome da placa física (ex.: "Ethernet")
New-VMSwitch -Name "LAN" -NetAdapterName "Ethernet" -AllowManagementOS $true
```

---

## 2. Criar a VM

```powershell
$vm = "nexos-ubuntu"
New-VM -Name $vm -Generation 2 -MemoryStartupBytes 8GB `
  -NewVHDPath "C:\Hyper-V\$vm\$vm.vhdx" -NewVHDSizeBytes 150GB -SwitchName "LAN"

Set-VM -Name $vm -ProcessorCount 4 -CheckpointType Disabled `
  -AutomaticStartAction Start -AutomaticStartDelay 30 -AutomaticStopAction ShutDown

# Secure Boot com o template p/ Linux (senão o Ubuntu não inicia em Gen 2):
Set-VMFirmware -VMName $vm -SecureBootTemplate MicrosoftUEFICertificateAuthority

# Plugar a ISO e priorizar o boot por ela na 1ª vez:
Add-VMDvdDrive -VMName $vm -Path "C:\ISOs\ubuntu-24.04-live-server-amd64.iso"
Set-VMFirmware -VMName $vm -FirstBootDevice (Get-VMDvdDrive -VMName $vm)

Start-VM -Name $vm
```

> **Decisões embutidas:** `AutomaticStartAction Start` = a VM volta sozinha
> quando o Windows reiniciar (update, queda de energia). `CheckpointType
> Disabled` = sem snapshot automático em cima de banco vivo — backup é o
> `pg_dump` do runbook, não checkpoint de VM.

Abra o **Gerenciador do Hyper-V → Connect** na VM e instale o Ubuntu:
- usuário `nexos`, hostname `nexos-ubuntu`;
- ✅ marque **Install OpenSSH server** (administração via `ssh nexos@<ip-da-vm>`);
- rede: DHCP e depois **fixe o IP por reserva no roteador** (ou IP estático).

Ao final, remova a ISO: `Set-VMDvdDrive -VMName $vm -Path $null`.

---

## 3. Dentro da VM — preparar e seguir o guia principal

```bash
# Docker + git + Node (Node só para o build do frontend)
sudo apt update && sudo apt install -y git curl
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER && newgrp docker
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
```

**A partir daqui, siga o [deploy_onprem.md](deploy_onprem.md) do início ao fim**
(clone do repo, `.env` com segredos fortes, Cloudflare Tunnel, build do
frontend, `docker compose -f docker-compose.prod.yml up -d --build` e o
`go_live_check`). O domínio já comprado entra nos passos 1 e 4 daquele guia
(apontar os nameservers do registro.br para a Cloudflare e criar o túnel).

> **Firewall do Windows: nenhuma porta de entrada.** O `cloudflared` abre uma
> conexão de SAÍDA — não crie regra de inbound nem port-forward no roteador.

---

## 4. Backup: dump da VM → OneDrive do host Windows

O runbook ([runbook_backup.md](runbook_backup.md)) gera dumps diários na VM; o
OneDrive roda no **host Windows**. Ponte: uma pasta compartilhada do host
montada na VM.

**No host (PowerShell, Admin)** — compartilhe uma pasta DENTRO do diretório
sincronizado pelo OneDrive:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\OneDrive\nexos-backups"
New-SmbShare -Name "nexos-backups" -Path "$env:USERPROFILE\OneDrive\nexos-backups" -FullAccess "$env:USERDOMAIN\$env:USERNAME"
```

**Na VM** — monte via CIFS e aponte o cron do backup para lá:

```bash
sudo apt install -y cifs-utils
sudo mkdir -p /mnt/onedrive-backups
sudo tee /root/.smb-nexos >/dev/null <<'EOF'
username=SEU_USUARIO_WINDOWS
password=SUA_SENHA
EOF
sudo chmod 600 /root/.smb-nexos
echo "//IP_DO_HOST/nexos-backups /mnt/onedrive-backups cifs credentials=/root/.smb-nexos,iocharset=utf8,uid=nexos 0 0" | sudo tee -a /etc/fstab
sudo mount -a
```

No cron do backup (passo 7 do deploy_onprem), use
`BACKUP_DIR=/mnt/onedrive-backups`. Regras de ouro continuam as do runbook:
sincronizar **os dumps**, nunca o volume `pgdata`; reter 30 dias; **ensaiar o
restore**.

---

## 5. Checklist final

- [ ] `Get-VM nexos-ubuntu` mostra `AutomaticStartAction = Start`.
- [ ] Reboot de teste do host: a VM volta e `https://fiscal.solsistema.com.br` responde.
- [ ] `docker compose -f docker-compose.prod.yml ps` — tudo `running/healthy`
      (o worker tem healthcheck próprio: travou = `unhealthy`).
- [ ] `go_live_check` imprimiu **✅ APROVADO**.
- [ ] Seed das matrizes rodado 1×: `docker compose -f docker-compose.prod.yml exec api python scripts/seed_matrizes.py`.
- [ ] `.env`: `NEXOS_ALERT_WEBHOOK_URL` (ntfy/Slack) e `NEXOS_MATRIZ_CURADORES` preenchidos; `NEXOS_SENTRY_DSN` se tiver conta.
- [ ] Dump de backup apareceu na pasta do OneDrive no host.
