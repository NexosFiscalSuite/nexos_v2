# Seeds das Matrizes Fiscais — 7 UFs do escritório (MG, PR, SP, DF, RS, RJ, GO)

**Gerado em 04/08/2026** a partir de pesquisa nas fontes abaixo. Estes arquivos
NÃO entram sozinhos no sistema: a curadoria importa pela tela **Matrizes
Fiscais → Importar planilha**, revisando antes (fail-closed: dado fiscal só
entra com revisão humana).

## Como importar

1. Matrizes Fiscais → aba **Alíquotas** → Importar → `matriz_aliquotas.csv`
2. Matrizes Fiscais → aba **FCP** → Importar → `matriz_fcp.csv`
3. O **Enquadramento** (NCM×CEST) das 7 UFs é alimentado pelo crawler CONFAZ
   (job mensal, dia 1º 04h UTC). Desde a Fase 1 da automação, o robô PROPÕE e
   a curadoria aprova na aba **Revisão** das Matrizes Fiscais — nada entra
   direto. Para rodar agora, na VM:
   `docker compose -f docker-compose.prod.yml exec worker celery -A app.core.celery_app call fiscal.sync_cest_confaz`

## O que cada arquivo contém

### `matriz_aliquotas.csv` — alíquota modal por UF (verificada em 04/08/2026)

| UF | Modal | FCP integrado | Vigência | Base legal |
|---|---|---|---|---|
| MG | 18% | — | estável (linha desde 01/01/2024) | Lei 6.763/1975, art. 12 |
| SP | 18% | — | estável (linha desde 01/01/2024) | Lei 6.374/1989 (RICMS art. 52, I) |
| PR | 19,5% | — | 18/03/2024 | Lei 21.850/2023 |
| RJ | 18% → 20% | 2% (FECP geral) | virada em 20/03/2024 (2 linhas) | Lei 10.253/2023 + LC 210/2023 |
| RS | 17% | — | estável (linha desde 01/01/2024) | Lei 8.820/1989 (RICMS art. 27, I) |
| GO | 19% | — | 01/04/2024 | Lei 22.460/2023 |
| DF | 20% | — | 21/01/2024 | Lei 7.326/2023 |

- MG/SP/RS: alíquota estável há anos; a vigência 01/01/2024 é o "conhecido
  desde". Nota emitida ANTES disso trava com erro catalogado (fail-closed) —
  se auditarem períodos anteriores, estenda a vigência para trás.
- PR: o FECOP-PR (2%) é POR PRODUTO (água mineral, bebidas, joias, fumo) —
  não integra a modal; entra na matriz de FCP por NCM quando curado.

### `matriz_fcp.csv` — FCP-ST

- Só RJ tem FCP GERAL (2%, FECP). **Atenção às exceções** (cesta básica,
  medicamentos e outros itens têm FECP zero) — cadastrar exceção por NCM com
  alíquota 0 quando aparecer nas notas.
- FCP por produto das demais UFs (PR FECOP, SP FECOEP em bebidas/fumo, RS
  AMPARA, GO PROTEGE, DF, MG FEM) fica para curadoria por NCM conforme a
  demanda das notas — não semeado por ser específico demais para automatizar
  com segurança.

## O que AINDA é manual (próximas fases da proposta)

- **MVA** por NCM×CEST×UF — atos estaduais (MG: Portarias SUTRI; SP: CAT/SRE).
- **Protocolos/Convênios** dos 42 pares entre as 7 UFs — Fase 3 da proposta
  (crawler do índice CONFAZ); até lá, curadoria manual por par usado.

## Fontes consultadas (04/08/2026)

- Alíquotas 2026 (duas tabelas cruzadas): tributodevido.com.br e
  nsdocs.com.br/blog/tabela-icms
- PR 19,5%: substituicaotributaria.com (efeitos 18/03/2024, Lei 21.850/2023);
  FECOP-PR por produto: atendimento.fazenda.pr.gov.br
- RJ 20%+2%: agenciabrasil.ebc.com.br e portal.fazenda.rj.gov.br
  (aliquotas-internas); virada 20/03/2024
- DF 20%: sinj.df.gov.br (Lei 7.326/2023), efeitos 21/01/2024
- GO 19%: Lei 22.460/2023 (efeitos 01/04/2024)
- CEST: página oficial consolidada do Convênio ICMS 142/2018 no CONFAZ
  (confaz.fazenda.gov.br/legislacao/convenios/2018/CV142_18)
