# Nexos Fiscal Suite V2

Ferramenta INTERNA da Sol Contabilidade: auditoria fiscal multi-tenant de
ICMS-ST + Reforma Tributária (IBS/CBS). Em produção em
https://fiscal.solsistema.com.br — o João testa em produção e pede ajustes;
cada pedido segue o ciclo implementar → testar → commitar → pushar → passar
os comandos de deploy.

## Stack e deploy

- **Backend**: FastAPI + PostgreSQL (RLS com FORCE, tenant via
  `app.current_tenant`) + SQLAlchemy async + Alembic + Redis/Celery.
  Venv local em `backend/.venv` (use `.\.venv\Scripts\python.exe` e
  `.\.venv\Scripts\ruff.exe` — `ruff`/`python` não estão no PATH).
- **Frontend**: React + Vite (JSX puro, sem TS) em `frontend/`.
- **Produção**: VM Hyper-V `nexos-ubuntu`, Docker Compose
  (`backend/docker-compose.prod.yml`: api, worker, Caddy, cloudflared).
  O deploy é MANUAL pelo João — sempre terminar entregas com o bloco:

  ```bash
  cd ~/nexos_v2
  git pull
  cd frontend && npm run build
  cd ../backend && docker compose -f docker-compose.prod.yml up -d --build api worker
  ```

  (só frontend → basta o `npm run build`; só backend → basta o compose.)

## Como trabalhar neste repo

- **Checagens antes de commitar**: `ruff check app tests` + `pytest -q` (no
  backend) e `npm run build` + `npm run lint` (no frontend). O hook de
  pre-push roda ruff+pytest e bloqueia push vermelho.
- **Commits**: português sem acento no título, corpo explicando o porquê,
  `Co-Authored-By: Claude ...` no fim. Push direto na `main`.
- **Testes**: pytest asyncio com sqlite em memória (`StaticPool` quando o
  código abre várias sessões). `processing_jobs.result` tem
  `with_variant(JSON, "sqlite")` para permitir testes. Tabelas criadas via
  `Base.metadata.create_all(tables=[...])` só com o necessário.
  Os GOLDENS do motor de ST não podem regredir.
- **JSX**: aspas tipográficas (“ ”) em texto com aspas — o eslint do CI
  barra `react/no-unescaped-entities` (o vite local não roda eslint).
- **PDF (fpdf2)**: tudo passa por `carta_base.py` (`CartaTimbrada`, `_t`
  latin-1 com mapa `_TROCAS` para “—”/“→”, `_brl/_pct/_cnpj`). O timbrado
  mantém o navy da marca Sol (#24477B) mesmo com a paleta nova do app.
- **Front**: paleta roxo claro #8B5FBF (pedido do João em ago/2026 — antes
  azul #0056D2). Layout no padrão do Console do sol-treinamentos-hub
  (pasta vizinha): sidebar em card flutuante sticky recolhível com marca
  compacta e usuário no rodapé, SEM topbar branca — competência/empresa/
  ajuda/sair flutuam no topo direito; cada página tem seu próprio título.
  Fonte Manrope,
  balões clicáveis `.balao-classif` (nunca tooltip de hover), números com
  `.tnum`, textos para leigos (nada de jargão seco).
- **Linguagem com o usuário**: sempre português; explicar o que mudou em
  termos práticos, sem acusação em textos fiscais (ex.: card é
  "ST a recolher", nunca "erro do fornecedor" / "retenção a menor").

## Arquitetura (backend/app/modules)

- `fiscal/` — núcleo. `domain/st/` é o MOTOR PURO de ICMS-ST (sem I/O):
  - Portão de enquadramento NCM×CEST×UF com vigência; fallback CEST-vazio →
    NCM; `explicar_tn` para transparência de TN.
  - Protocolo TRI-STATE (True/False/None → `ERRO_PROTOCOLO_NAO_AVALIADO`);
    situação ATIVO, NCM com prefixo 8→6→4, `"*"` = par inteiro. FAIL-CLOSED
    em tudo: sem certeza → erro catalogado, nunca cálculo silencioso.
  - Estratégias de base: MVA (ajustada quando interestadual) e valor da
    operação; `modBCST` ausente → a matriz decide. Dedução ESTRITA do vICMS
    próprio na saída. FCP, tolerâncias em centavos.
  - `MemoriaCalculo` persistida e versionada com base legal (mva/alíquota) e
    composição do custo (frete, frete_cte, seguro, IPI, desconto...).
  - `errors.py`: catálogo `ErroST` (codigo/mensagem/acao_sugerida), exposto
    em `/auditoria/st/catalogo-erros`; reprocessamento revisita legados.
  - Gate do frete/CT-e: se a empresa é tomadora do frete e não há CT-e
    vinculado nem confirmação, TRAVA o cálculo (`FRETE_PENDENTE_CTE`);
    confirmação "não há CT-e" grava trilha (quem/quando) e reaudita.
  - IBS/CBS: `classificar_item` valida gRed POR PERNA (nominal × efetiva).
- `companies/` — empresas do escritório. Documento aceita CNPJ (14), CPF
  produtor rural (11) e CEI/CNO (12), cada um com DV próprio
  (`shared/domain/value_objects.py::DocumentoFiscal`). Cadastro em lote CSV
  (`empresas_bulk.py`, UF aceita nome por extenso) e atualização pela
  Receita via OpenCNPJ (`application/atualiza_cadastro.py` + worker Celery
  com pausa progressiva 1s/2s/3s e retry de 429; CPF/CEI são pulados —
  não há consulta pública).
- `grupos/` — controle de acesso: SÓ ADMIN vê todas as empresas; supervisor
  e usuário comum veem apenas as dos grupos em que estão (supervisor é
  GrupoMembro com papel "supervisor"). Regra em
  `companies/application/service.py::_FULL_ACCESS`.
- `jobs/` — `processing_jobs` para trabalho assíncrono com polling do front.
- `contrapartes/`, `reporting/`, `audit/` (trilha), `identity/`, `cfop_rules/`.
- Workers Celery: sessão POR unidade de trabalho (`worker_tenant_session`,
  NullPool); job commitado ANTES do `.delay`.
- Parser de XML (`fiscal/domain/parser.py`): lê CNPJ **ou CPF** de
  emit/dest, extrai `tpNF`, `modFrete`, gRed, ST retido. A classificação de
  fluxo (`flow.py`) usa o documento para saber DE QUEM é a nota e o tpNF
  para o SENTIDO econômico (tpNF=0 emitida pelo comprador → venda de quem
  está no destinatário — caso produtor rural).

## Regras de negócio que NÃO podem ser violadas

1. `tenant_id` NUNCA vem de planilha/payload — sempre injetado dos claims.
2. Motor de ST é fail-closed: incerteza vira erro catalogado com ação
   sugerida, jamais resultado calculado por palpite.
3. Semântica sem acusação nas telas/cartas; carta pede base normativa e
   ressalva possível desobrigação do fornecedor.
4. Regime tributário do cliente só muda automaticamente quando a Receita
   confirma Simples/MEI — Presumido × Real é escolha do escritório; campo
   vazio de API nunca apaga dado existente.
5. MVA de tintas 35% (caso citado pelo João): NUNCA aplicar sem "pode"
   explícito dele.
6. Curadoria de matrizes: usuário normal pode criar/editar;
   `NEXOS_MATRIZ_CURADORES` é freio OPCIONAL (env limpa = todos liberados).

## Estado atual (04/08/2026)

Últimos commits (tudo deployado ou aguardando deploy do João):
`cd66717` tpNF desempata fluxo · `3900112` cadastro CEI · `b025eb7`
cadastro CPF produtor rural · `3720b18` supervisor só vê grupos ·
`a4b5f45` seletores de grupo filtrados · `65564d5` atualização de cadastro
pela Receita (individual + lote com job) · `8f86e7e`/`6671d34` busca,
paginação e UF por extenso em Empresas. Suite: 160 passed, 4 skipped.

## Pendências e ofertas em aberto

- **Roadmap grande do relatório de melhorias do motor de ST** (aguarda
  "continua" do João): triagem de divergências (cobrada/justificada/aceita
  em tabela própria), fundação entrada→saída (ressarcimento CST 60,
  PGDAS-D, fluxo MG EFD), alíquota por NCM, DIFAL, pauta/PMPF.
- Ofertas feitas e não aprovadas: aceitar .xlsx direto no import de
  empresas; script de reclassificação de notas antigas (fluxo tpNF) com
  reauditoria; backfill de `mod_frete` para notas antigas; estender o
  diagnóstico automático do balão a outros códigos de erro.
- Operacional (lado do João): limpar `NEXOS_MATRIZ_CURADORES` no .env do
  servidor; conferir grupos dos supervisores após o deploy do `3720b18`
  (supervisor sem grupo não vê empresa nenhuma).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
