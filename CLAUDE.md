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
- **Front**: paleta amarelo/laranja Sol #F39200 — o amarelo da logo — com
  texto navy #24477B (`--primary-contrast`) sobre a cor primária, par da
  marca (pedido do João em ago/2026; antes roxo #8B5FBF, antes azul
  #0056D2). Layout no padrão do Console do sol-treinamentos-hub
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

## Estado atual (06/08/2026)

**MVA por par origem→destino (06/08, urgente — o app oficial da Receita estava
mais assertivo que a ferramenta nos testes do João).** Três defeitos corrigidos
juntos: (1) `matriz_mva` só tinha UF de destino, então o motor aplicava a MVA de
outro par — ganhou `uf_origem` (migração 0033; `"*"` = qualquer origem, todo o
legado virou curinga), com busca que prefere a origem EXATA e só cai no curinga
dentro de cada nível de NCM (8→6→4); (2) sem MVA na base o motor assumia 0% em
silêncio quando o modBCST era 6 ou ausente — agora `tem_mva` = EXISTE LINHA (uma
MVA curada em 0,00 é decisão, não ausência) e a falta vira `MVA_NAO_ENCONTRADA`,
**atrás da env `NEXOS_ST_MVA_FAIL_CLOSED` (padrão OFF — ligar só depois de
carregar a base, senão quase todo item fora de MG vira não auditável)**; a trava
histórica do modBCST=4 segue sempre ativa; (3) UF era texto livre nas 5 matrizes
— fonte única em `app/shared/domain/uf.py` (`normalizar_uf` aceita "mg"/"Minas
Gerais", recusa o resto), dropdown em todo o front (`components/SelectUf.jsx`) e
validação nos schemas. Curinga `"*"` vale só na MVA: o protocolo compara origem
por igualdade, sem fallback. A memória de cálculo passou a gravar
`mva_uf_origem`. Relatório de **lacunas de MVA** (`GET /matrizes/lacunas-mva`
+ `/export`, botão na aba Cobertura): o que falta para as notas JÁ importadas,
por origem→destino e ordenado por dinheiro, exportado no MESMO layout do
"Importar planilha" — baixa, preenche só a margem, sobe. O crawler do Anexo VII
passou a extrair a UF de origem da legenda de âmbito (o dado já era lido para os
Protocolos e estava sendo descartado); o hash de proposta mudou, então rejeições
antigas de MVA voltam uma vez à fila. Cobertura real: **só MG tem MVA de fonte
oficial automatizada** — ver docs/estado_base_matrizes_st.md.

**Exceção do Item por FORNECEDOR + envio em lote (06/08).** O cProd é do
fornecedor: dois fornecedores usam o MESMO código para produtos diferentes, e a
exceção casava só pelo código dentro da empresa — vazava de um fornecedor para
outro e desligava o ST do item errado, sem sinal nenhum. Agora
`excecao_enquadramento_st_produto.cnpj_fornecedor` (migração 0034; `""` =
qualquer fornecedor, todo o legado virou genérico) e a busca prefere o CNPJ
exato, caindo no genérico só na ausência de regra do fornecedor. O motor JÁ
passava `cnpj_emitente` ao portão (`engine.py:87`) — só o repositório ignorava;
o índice normaliza o documento na CONSTRUÇÃO, senão cadastro formatado não casa
com o CNPJ limpo do XML. `fonte_regime` também recebe o CNPJ (antes dizia
"EXCECAO_ITEM" para nota de fornecedor sem exceção). Envio em lote em
`api/excecoes_bulk.py`: export/import CSV (`cnpj_empresa` identifica a empresa —
ninguém digita UUID) e **`/candidatos`**, que devolve no MESMO layout os itens
das notas já auditadas que o motor tratou como ST, agrupados por
(fornecedor, código) e ordenados por valor, com `tributado_icms` VAZIO — o
importador IGNORA linha em branco, então nada vira exceção por descuido (uma
exceção errada tira imposto devido). Import reaudita as notas dos pares tocados
(`?reprocessar=false` desliga). `shared/bulk_csv.py` ganhou `LinhaIgnorada`,
`chave_vigencia`, `exportar_valor` e `filtros` — retrocompatível com as 5
matrizes. `excecoes_bulk_router` é registrado ANTES do `matrizes_bulk_router`
em `main.py`, senão `/matrizes/{tipo}/export` engole a rota.

Automação das matrizes (proposta em docs/proposta_automacao_matrizes_st.md):
Fases 1–5 entregues — crawler CONFAZ NCM×CEST (7 UFs: MG,PR,SP,DF,RS,RJ,GO;
vigência-piso 2026-06-01) propõe na FILA de revisão (aba Revisão, nada entra
sem curadoria; rejeição suprime re-proposta por hash); aviso de legislação
pré-emissão com trilha de ciência + `ultima_verificacao_em` nas 5 matrizes;
aba Saúde (frescor 90d + pares interestaduais × curadoria de protocolos);
radar semanal do índice de Protocolos CONFAZ (hash + webhook); reconferência
semestral de alíquotas/FCP (ação REVALIDAR na fila — aprovar renova o
carimbo, hash por ciclo); MVA de MG extraída do Anexo VII do RICMS/2023
(SEFAZ-MG, 7 páginas HTML latin-1, âncora na célula CEST — validado com
1.080 pares reais; mudança em linha auto vira NOVA_VIGENCIA no 1º do mês da
detecção; PMPF extinto em MG pela Portaria SUTRI 1.518/2025); Protocolos
extraídos da LEGENDA de âmbito do mesmo anexo (código → UF + acordo; 2.817
propostas UF→MG escopadas por NCM nos dados reais, base legal no estilo
"Protocolo ICMS 103/12 — Anexo VII, âmbito 2.1"; CHAVE_VIGENCIA do
protocolo agora inclui ncm — vários escopos por acordo; FCP de MG segue
manual, fonte própria Lei 6.763/75 art. 12-A). Paginação em
todas as listas (15–50/página; componente Paginacao). Migrações até 0034.
Suite: 332 passed, 4 skipped. Deploys de 04-06/08 AGUARDANDO o João
(sem acesso ao servidor no momento) — um git pull + build + compose aplica
tudo, migrações rodam sozinhas. Falta da proposta: Fase 6 (pauta/PMPF — com
MG fora do PMPF, relevância caiu; avaliar por UF).

## Pendências e ofertas em aberto

- **Roadmap grande do motor de ST**: triagem de divergências COMPLETA em
  05/08 (tabela `divergencia_triagem`, filtro, carta marca COBRADA, selo por
  item + modal de triagem manual na tela). Restam os blocos maiores:
  fundação entrada→saída (ressarcimento CST 60, PGDAS-D, fluxo MG EFD),
  alíquota por NCM, DIFAL, pauta/PMPF (MG saiu do PMPF em 11/2025).
- Ofertas feitas e não aprovadas: aceitar .xlsx direto no import de
  empresas; script de reclassificação de notas antigas (fluxo tpNF) com
  reauditoria; backfill de `mod_frete` para notas antigas; estender o
  diagnóstico automático do balão a outros códigos de erro; item na aba
  Saúde para "linhas com UF fora do padrão" (o legado gravado por texto
  livre continua no banco — a leitura da API é leniente de propósito para
  o curador conseguir achar e corrigir pela tela).
- Dívidas conhecidas da Exceção do Item (nenhuma é regressão): o
  `ExcecoesItemPanel` de `MatrizesFiscais.jsx` é RESÍDUO — exportado e
  importado por ninguém, sobra de antes de a Exceção virar módulo próprio
  (`/excecao-item`); remover em commit separado. Duas exceções da mesma
  chave com vigências SOBREPOSTAS resolvem por "última ganha", sem
  desempate (a UNIQUE só barra a mesma data de início) — é anterior a
  06/08. `ReprocessService.reprocessar_produto` reaudita por código sem
  olhar o fornecedor: abrangente demais, nunca de menos.
- **MVA aprendida das notas** (proposta em 06/08, não aprovada): juntar o
  `pMVAST` que os fornecedores já mandam, agrupar por NCM/CEST/origem→destino
  e propor na fila quando vários convergirem, com a contagem de notas que
  sustentam o valor. É a resposta de fundo ao "se tiver que cadastrar na mão,
  o usuário prefere o app oficial". Nada entraria sem curadoria.
- Operacional (lado do João), NA ORDEM: **(1) botão "Carregar base de MG
  (Anexo VII)" na aba Cobertura** — o worker `fiscal.carga_inicial_matrizes`
  existia desde a Fase 5 mas NÃO tinha gatilho (só linha de comando no
  servidor, que o João não acessa), então nunca rodou e a matriz de MVA
  chegou vazia em produção; é a causa dos ST calculados a menor;
  (2) carregar as lacunas das demais UFs pelo CSV; (3) só então ligar
  `NEXOS_ST_MVA_FAIL_CLOSED=true`. Também: limpar `NEXOS_MATRIZ_CURADORES`
  no .env; conferir grupos dos supervisores após o deploy do `3720b18`
  (supervisor sem grupo não vê empresa nenhuma).

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
