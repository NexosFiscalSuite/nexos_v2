# Passo a passo — Deploy e operação do Nexos (ST automatizado)

**Atualizado em 05/08/2026.** Este guia cobre o deploy pendente (commits de
04–05/08), a primeira rodada da automação das matrizes e a rotina de trabalho
do dia a dia. Escrito para a equipe — sem jargão onde dá.

---

## 1. Deploy (na VM `nexos-ubuntu`)

```bash
cd ~/nexos_v2
git pull
cd frontend && npm run build
cd ../backend && docker compose -f docker-compose.prod.yml up -d --build api worker
```

O que acontece sozinho no start da API (não precisa fazer nada):

- **Migrações 0028 a 0031** rodam em ordem: vigência do enquadramento
  retroage para **01/06/2026** (as notas de junho/julho destravam), nascem as
  tabelas da fila de propostas, o carimbo de "última verificação" nas
  matrizes e a tabela de triagem.

Conferências no `.env` do servidor (uma vez só):

| Variável | O que fazer |
|---|---|
| `NEXOS_CRAWLER_UF_ALVO` | Se existir com valor `MG`, apague a linha ou troque por `MG,PR,SP,DF,RS,RJ,GO` — senão o robô só alimenta MG |
| `NEXOS_MATRIZ_CURADORES` | Vazio = todo mundo aprova propostas. Preenchido (e-mails por vírgula) = só a lista |
| `NEXOS_ALERT_WEBHOOK_URL` | Opcional: URL de webhook (ntfy.sh, Slack, Teams) para receber o aviso do radar CONFAZ e falhas de job |

## 2. Conferência pós-deploy (5 minutos)

1. Abra o sistema e dê um **F5 forte (Ctrl+Shift+R)** — o visual novo (roxo,
   sidebar em card, sem a barra branca do topo) precisa do cache limpo;
2. **Matrizes Fiscais**: as abas novas **Revisão** e **Saúde** devem aparecer;
3. **Divergências de ST**: as notas de **junho e julho** que estavam "sem
   enquadramento" devem voltar a auditar depois do passo 4.4.

## 3. Primeira rodada da automação (estreia — fazer uma vez)

### 3.1 Carga inicial: UM comando deixa a base cheia

Na VM:

```bash
cd ~/nexos_v2/backend && docker compose -f docker-compose.prod.yml exec worker celery -A app.core.celery_app call fiscal.carga_inicial_matrizes
```

O que ele faz (idempotente — rodar de novo não duplica nada):

1. **Alíquotas** das 7 UFs + **FCP** geral do RJ — os valores verificados com
   base legal (os mesmos de `docs/seeds/`), pulando qualquer linha que já
   exista (cadastro manual tem sempre prioridade);
2. **MVAs de MG** (≈1.080 pares) e **Protocolos UF→MG** (≈2.800 acordos
   escopados por NCM) extraídos do Anexo VII do RICMS/2023 — propostos e
   **aprovados em nome da "carga inicial (robô)"**, com trilha completa.

Regras de segurança que valem sempre:

- Linha cadastrada **na mão nunca é tocada** pelo robô (ex.: a MVA 35% de
  tintas continua intacta);
- **Rejeitar** uma proposta vale para sempre — ela não volta à fila;
- Item sem margem publicada ou ambíguo na fonte **não vira proposta**;
- Depois da carga inicial, as rodadas mensais voltam ao normal: **mudança
  nova cai na aba Revisão** para aprovação humana.

### 3.3 Pares interestaduais (o que mais destrava o motor)

**Matrizes Fiscais → Saúde** → tabela **"Pares interestaduais da carteira"**:

- Par **vermelho** ("Não avaliado — trava o motor") = tem nota de verdade
  travada ali, ordenado por dinheiro em jogo;
- Para cada par: confira no CONFAZ/RICMS se existe protocolo/convênio para
  os produtos movimentados → botão **"Cadastrar protocolo"** (já vem com o
  par preenchido). Há acordo? situação **ATIVO** com o número. Não há?
  situação **"SEM ACORDO"** — o registro explícito também destrava (vira
  antecipação do destinatário).

### 3.4 Reauditar o que estava travado

**Divergências de ST → "Reprocessar Pendentes"** — as notas travadas por
matriz faltante são reavaliadas com a base nova.

## 4. Rotina do dia a dia (o ciclo do ST)

1. **Importar XMLs** (como sempre) — o motor audita sozinho, fail-closed;
2. **Divergências de ST**: o ranking mostra **quem cobrar primeiro** (maior
   valor cobrável por fornecedor);
3. **Carta PDF**: antes de gerar, o sistema pede a **ciência da legislação**
   (fica registrado quem confirmou) — e a carta sai com a data da última
   verificação da base. Gerar a carta **já marca os itens como "Cobrada"**;
4. **Triagem do desfecho**: no item (🏷), registre **Justificada** (fornecedor
   apresentou base normativa — baixa) ou **Aceita** (cliente assume/recolhe);
5. **Filtro "Em aberto"** responde "o que ainda falta cobrar?" num clique. O
   Excel exportado respeita o filtro e carrega a triagem de cada item.

## 5. O que roda sozinho (e onde aparece)

| Robô | Quando | O que faz | Onde aparece |
|---|---|---|---|
| CEST/CONFAZ (7 UFs) | Dia 1º, 04h | Relação NCM×CEST do Convênio 142/2018 → propostas de enquadramento | Aba **Revisão** (chip na aba) |
| MVA de MG | Dia 2, 04h30 | Anexo VII do RICMS/2023 → propostas de MVA (novas e mudanças) | Aba **Revisão** |
| Radar de Protocolos | Segunda, 05h | Vigia o índice de Protocolos ICMS do CONFAZ; mudou → avisa | Webhook de alertas (se configurado) + log |
| Reconferência | 1º de jan e jul, 06h | Alíquotas/FCP não conferidas no semestre viram "Reconferência" | Aba **Revisão** — aprovar = "continua valendo" |

Nenhum robô escreve direto nas matrizes: **tudo passa pela fila de Revisão**.

## 6. Painéis de controle (o que olhar por semana)

- **Matrizes → Revisão**: o chip com número = propostas esperando. Diff
  vigente × proposto, aprova/rejeita individual ou em lote;
- **Matrizes → Saúde**: % da base verificada em 90 dias (farol), a data que
  sai no aviso da carta, e os pares interestaduais pendentes;
- **Matrizes → Cobertura**: o que a carteira movimenta × o que as matrizes
  cobrem — a fila de cadastro por valor.

## 7. Perguntas rápidas

- **"Por que o aviso de legislação antes da carta?"** — Os valores saem das
  matrizes cadastradas; a lei muda. A confirmação fica na trilha (quem/quando)
  e protege o escritório se questionarem um recolhimento.
- **"Regra envelhecida é regra errada?"** — Não. É regra que ninguém confere
  há tempo. Editar, reimportar ou aprovar proposta renova o carimbo.
- **"Rejeitei uma proposta por engano"** — Propostas rejeitadas não voltam.
  Cadastre/edite a regra manualmente pelo CRUD da matriz.
- **"A triagem some se eu reprocessar?"** — Não. Ela vive em tabela própria,
  ancorada na nota+item, e sobrevive à reauditoria.
- **Disparos manuais** (na VM, sem esperar a agenda):

```bash
cd ~/nexos_v2/backend
docker compose -f docker-compose.prod.yml exec worker celery -A app.core.celery_app call fiscal.sync_cest_confaz
docker compose -f docker-compose.prod.yml exec worker celery -A app.core.celery_app call fiscal.sync_mva_mg
docker compose -f docker-compose.prod.yml exec worker celery -A app.core.celery_app call fiscal.monitor_protocolos_confaz
docker compose -f docker-compose.prod.yml exec worker celery -A app.core.celery_app call fiscal.reconferir_aliquotas
```
