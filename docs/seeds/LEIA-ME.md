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

## Planilha de MVA — colunas (com `uf_origem`)

O import/export da matriz de MVA tem **oito** colunas, nesta ordem:

```
ncm;cest;uf_origem;uf_destino;mva_original;base_legal;data_inicio_vigencia;data_fim_vigencia
```

- **`uf_origem`** — de onde a mercadoria vem. Vazia ou `*` significa "vale para
  QUALQUER origem"; uma sigla (`SP`) restringe a margem àquele par. A busca do
  motor prefere a origem exata e só cai no `*` quando não há linha específica,
  então uma regra geral nunca sequestra um par curado.
- **`mva_original`** — número publicado pela norma. Nunca preencha por
  estimativa: sem margem oficial, é melhor a linha faltar (o motor acusa) do
  que existir errada (a carta sai errada).
- Arquivo antigo, sem a coluna `uf_origem`, continua carregando: todas as
  linhas entram como `*`. Pela linha de comando o script avisa antes de gravar.

Carga pelo servidor:

```bash
docker compose -f docker-compose.prod.yml exec api \
  python scripts/carga_matrizes.py mva cargas/2026-06-supervisores/mva_mg_PREENCHER.csv
```

## Atalho: baixar a lista de lacunas já pronta para preencher

Em vez de montar a planilha na mão, use o **relatório de lacunas de MVA**: ele
lista os pares NCM×CEST×(origem→destino) que as notas importadas realmente
usam e a matriz não cobre, ordenados pelo valor em jogo, e exporta no layout
acima com `mva_original` **vazia**. O fluxo é: baixar → preencher só a coluna
da margem (consultando a norma da UF) → subir pelo Importar planilha.

## O que AINDA é manual (próximas fases da proposta)

- **MVA** por NCM×CEST×UF fora de MG — atos estaduais (SP: Portarias CAT/SRE;
  PR, RJ, RS, GO, DF: anexos próprios). MG já vem do Anexo VII do RICMS/2023
  pelo crawler mensal. Panorama por UF em
  [`../estado_base_matrizes_st.md`](../estado_base_matrizes_st.md).
- **Protocolos/Convênios** dos pares que **não** terminam em MG — os UF→MG
  saem da legenda de âmbito do Anexo VII; o resto é curadoria manual por par
  usado, com o radar semanal do índice CONFAZ avisando quando algo muda.

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
