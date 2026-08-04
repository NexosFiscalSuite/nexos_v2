# Proposta técnica — Automação da base de dados do motor de ICMS-ST

**Data:** 04/08/2026 · **Status:** proposta para aprovação (nenhum código alterado)

---

## 1. Sumário executivo

Hoje as cinco matrizes fiscais que alimentam o motor de ST (Enquadramento,
MVA, Protocolos, Alíquotas e FCP) são preenchidas manualmente pela equipe —
via tela de curadoria ou planilha CSV. A proposta é evoluir para um modelo de
**curadoria assistida**: robôs (crawlers) monitoram as fontes oficiais,
detectam mudanças e geram **propostas de atualização** que um curador aprova
com um clique, vendo o diff e o documento de origem. A aprovação humana é
mantida de propósito — ela é o que preserva a regra nº 2 do projeto
(fail-closed: incerteza nunca vira cálculo silencioso).

Não existe API oficial nacional e machine-readable para MVA/enquadramento de
ST — essa é a restrição central. Por isso a meta realista não é "100%
sincronizado em tempo real", e sim: **base automatizada com atualização
periódica + detecção de mudança nas fontes + aviso de legislação vigente em
todo ponto de emissão** (carta de cobrança, export, e futura guia).

O projeto já tem a fundação: `fiscal/crawlers/` (contrato `Extractor` com
fetch/parse separados, extrator CONFAZ do Convênio 142/2018, upsert
idempotente e job mensal no Celery beat). A proposta generaliza essa fundação
em vez de criar algo novo.

---

## 2. Diagnóstico — como a base funciona hoje

### 2.1 As cinco matrizes (globais, sem tenant, com vigência temporal)

| Tabela | Conteúdo | Chave | Fonte real da regra |
|---|---|---|---|
| `matriz_enquadramento_st` | Regime ST/TN/ST_ENTRADA por NCM×CEST×UF | uf, ncm, cest, vigência | Convênio 142/2018 + adesão estadual (RICMS) |
| `matriz_mva` | MVA original por NCM×CEST×UF | ncm, cest, uf, vigência | Atos estaduais (MG: Portarias SUTRI; SP: Portarias CAT/SRE) |
| `matriz_protocolo_st` | Acordos interestaduais (par UF→UF) | uf_orig, uf_dest, nº acordo, vigência | Protocolos/Convênios CONFAZ |
| `matriz_aliquota` | Alíquota modal + FCP integrado por UF | uf, vigência | Leis estaduais (ex.: AL 19%→20,5% em 01/04/2026) |
| `matriz_fcp` | FCP por UF×NCM | uf, ncm, vigência | Leis estaduais |

Pontos fortes que a automação deve preservar:

- **Vigência temporal (ADR-0002)** — nova regra é nova linha de vigência,
  nunca sobrescrita; a busca filtra pela data de emissão da nota.
- **`base_legal` por linha** — vai para a `MemoriaCalculo` e para a carta.
- **Fail-closed** — par UF não curado trava com `ERRO_PROTOCOLO_NAO_AVALIADO`;
  MVA ambígua trava; nada é calculado por palpite.
- **Fallback NCM 8→6→4 e CEST vazio** — resolvidos na leitura, não no dado.

### 2.2 Alimentação atual

1. **CRUD manual** (`matrizes_routers.py` + `MatrizesFiscais.jsx`), com freio
   opcional de curadoria (`NEXOS_MATRIZ_CURADORES`).
2. **Import/export CSV em lote** (`matrizes_bulk.py`) — upsert por chave
   incluindo vigência; o export vazio serve de template.
3. **Crawler CONFAZ (embrião já existente)** — `fiscal/crawlers/` baixa a
   relação NCM×CEST do Convênio 142/2018 e faz upsert direto na matriz de
   Enquadramento da UF-alvo (`crawler_uf_alvo`, hoje MG), todo dia 1º às 04h
   UTC. O próprio código já avisa: a lista CONFAZ é o UNIVERSO nacional; a
   adesão estadual é subconjunto — o resultado é sugestão, não verdade.
   Pendência registrada no código: confirmar a URL estável do CSV antes de
   ligar em produção.

### 2.3 Lacunas

- Só 1 das 5 matrizes tem alguma automação, para 1 UF, e **gravando direto**
  na tabela oficial (sem fila de revisão — o "é sugestão" está só no
  `base_legal`, invisível no fluxo).
- Nenhuma detecção de mudança: o job reprocessa tudo todo mês, sem saber se a
  fonte mudou, e sem guardar cópia do que baixou (auditoria da origem).
- Nenhum monitoramento de "frescor": não há como saber que uma MVA cadastrada
  há 14 meses nunca mais foi conferida.
- Nenhum aviso de legislação vigente nos pontos de emissão (carta de
  cobrança ST, export XLSX, telas de auditoria).

---

## 3. Fontes de dados avaliadas

A avaliação honesta por matriz — o que dá para automatizar, com que grau de
confiança, e de onde:

| Matriz | Fonte oficial | Formato | Automação viável |
|---|---|---|---|
| Enquadramento (universo CEST) | CONFAZ — Convênio 142/2018 | CSV/planilha pública | **Alta** — já implementada (crawler existente) |
| Enquadramento (adesão por UF) | RICMS de cada UF (MG: Anexos do RICMS/2023) | HTML/PDF | **Média** — scraping por UF, uma UF por vez |
| Protocolos/Convênios | Portal CONFAZ (índice por ano, com situação vigente/denunciado) | HTML | **Média-alta** — estrutura estável, escopo restrito aos pares UF de interesse |
| Publicação de novos atos | DOU via **INLABS** (Imprensa Nacional) | XML diário, oficial, gratuito (requer cadastro) | **Alta para DETECÇÃO** — monitor de termos ("Convênio ICMS", "Protocolo ICMS") que gera alerta, não dado |
| Alíquotas modais (27 UFs) | Leis estaduais (com noventena — muda com meses de antecedência) | Diversos | **Baixa para extração, alta para monitoramento** — volume minúsculo (~27 linhas, poucas mudanças/ano); alerta + confirmação manual resolve |
| MVA | Atos estaduais (MG: Portarias SUTRI) | PDF/HTML | **Baixa-média** — extração assistida de PDF com revisão obrigatória, OU provedor comercial |
| FCP | Leis estaduais | Diversos | Igual às alíquotas: monitorar + confirmar |
| Pauta/PMPF (roadmap futuro) | Atos COTEPE/PMPF (CONFAZ, quinzenal) | PDF/planilha | **Média** — publicação regular; entra na fase final |
| Tudo acima, terceirizado | Provedores comerciais (Systax, Econet, IOB, LegisWeb) | API paga | **Alta** — custo mensal; entra como adaptador opcional, decisão de negócio |

Duas conclusões práticas:

1. **Detecção de mudança é automatizável em quase tudo; extração confiável do
   dado, não.** O desenho certo separa as duas coisas: robô detecta e propõe,
   humano aprova.
2. **O escopo real do escritório é pequeno.** A Sol não precisa das 27 UFs ×
   todos os NCMs: precisa dos pares UF→UF e NCMs que de fato aparecem nas
   notas dos clientes. O sistema já tem esses dados — a priorização deve ser
   dirigida por uso (query sobre `nota_item`).

---

## 4. Arquitetura proposta

### 4.1 Princípio: robô propõe, curador aprova, motor só lê o aprovado

```
Fontes oficiais          fiscal/crawlers/               Curadoria            Motor de ST
─────────────────        ─────────────────────          ──────────────       ────────────
CONFAZ CSV  ──fetch──►   Extractor (fetch/parse)                             (INALTERADO:
CONFAZ HTML ──fetch──►   FonteSnapshot (hash+cópia)                          ports, loaders,
INLABS XML  ──fetch──►   diff vs. matriz vigente   ──►  PropostaAtualizacao  engine puro)
SEFAZ-UF    ──fetch──►   (só propõe se mudou)           tela de revisão            ▲
Provedor(API opcional)                                  aprova/rejeita  ──►  matriz_* ──┘
                                                        (trilha audit/)
```

O motor puro (`domain/st/`), os ports e os loaders **não mudam uma linha**.
A automação acontece inteira a montante das tabelas `matriz_*`.

### 4.2 Componentes novos (backend/app/modules/fiscal/crawlers/)

**a) `FonteSnapshot` (tabela nova)** — cada execução de crawler grava: fonte,
URL, hash SHA-256 do conteúdo bruto, cópia do bruto (storage já existente),
timestamp e resumo do parse. Serve para (1) só disparar proposta quando o
hash mudou, (2) auditoria da origem ("de onde veio esse 40%?"), (3) degradar
com dignidade — se o parse quebrar porque o portal mudou o layout, o sistema
alerta "fonte mudou e não consegui ler" em vez de falhar em silêncio.

**b) `PropostaAtualizacao` (tabela nova)** — a fila de revisão:

```
tipo_matriz  (mva | enquadramento | protocolo | aliquota | fcp)
acao         (INSERIR | ENCERRAR_VIGENCIA | NOVA_VIGENCIA)
payload      (JSON com a linha proposta)
linha_atual_id (nullable — o que seria substituído)
fonte_snapshot_id, base_legal_sugerida
status       (PENDENTE | APROVADA | REJEITADA)
revisado_por, revisado_em, motivo_rejeicao
```

Aprovação grava na `matriz_*` com a mesma semântica de vigência do CRUD
atual e registra na trilha (`audit/`) — mesmo padrão da confirmação de
frete/CT-e que já existe. Rejeição fica registrada e **suprime re-proposta
idêntica** (o hash da proposta rejeitada não volta à fila).

**c) Tela "Revisão de Atualizações" (frontend)** — extensão da
`MatrizesFiscais.jsx`: lista de pendências com diff lado a lado (vigente ×
proposto), link para o documento-fonte, aprovação individual ou em lote por
fonte. Balões clicáveis no padrão do app, texto para leigos.

**d) Novos extratores (mesmo contrato `Extractor` já existente)**
- `ConfazProtocolosExtractor` — índice de protocolos/convênios do portal
  CONFAZ, filtrado aos pares UF com notas no sistema; propõe inclusão,
  denúncia (encerrar vigência) e alteração de acordo.
- `InlabsDouMonitor` — XML diário do DOU; busca termos ("Convênio ICMS",
  "Protocolo ICMS", NCMs de interesse). Não extrai dado: gera **alerta**
  na fila ("saiu o Convênio ICMS 87/2026 citando NCM 3208 — verificar").
  É o "radar de legislação" que cobre o que os crawlers estruturados não leem.
- `SefazMgMvaExtractor` (fase posterior) — Portarias SUTRI: extração
  assistida de PDF. Toda saída vira proposta com grau de confiança; nunca
  aprovação automática.

**e) Migração do job CEST/CONFAZ existente** — passa a escrever na fila de
propostas em vez de direto na matriz (com diff contra a vigência atual, a
primeira carga pode ser aprovada em lote). Resolve a pendência de go-live
(URL estável) no mesmo passo.

**f) `ProvedorMatrizesPort` (adaptador opcional)** — port para provedor
comercial (Systax/Econet/LegisWeb). Se um dia a Sol contratar, o provedor
vira só mais uma fonte que alimenta a MESMA fila de propostas — a
arquitetura não muda. Decisão de custo fica desacoplada da decisão técnica.

### 4.3 Saúde da base ("radar de frescor")

- Campo novo `ultima_verificacao_em` nas tabelas `matriz_*` (default =
  `created_at`). Aprovar proposta OU o curador confirmar "continua valendo"
  renova o carimbo sem criar vigência nova.
- Job semanal marca linhas "envelhecidas" (ex.: MVA sem verificação há mais
  de N meses, alíquota sem verificação desde a última virada de ano) e
  alimenta um painel "Saúde das Matrizes": % da base verificada nos últimos
  90 dias, pendências na fila, fontes com erro de leitura.
- Alíquotas modais e FCP (volume minúsculo): job semestral gera pendência de
  reconferência por UF usada — é revisão de 27 linhas, minutos de trabalho,
  e elimina o risco tipo "AL mudou e ninguém viu".

### 4.4 Aviso de legislação vigente antes da emissão (requisito do pedido)

Aplicado em **todos os pontos de saída** do ST (carta de cobrança PDF,
export XLSX de divergências, tela de auditoria — e futura guia, se vier):

1. **No backend**: a resposta da carta/export ganha um bloco
   `aviso_legislacao` com (a) a data-base das matrizes usadas no cálculo
   (derivada dos `matriz_id` já gravados na `MemoriaCalculo` →
   `ultima_verificacao_em` mais antiga entre elas) e (b) o texto do aviso.
2. **No PDF (carta_base.py)**: rodapé padronizado, no tom sem acusação do
   projeto: *"Valores apurados com base nas matrizes fiscais vigentes,
   verificadas até DD/MM/AAAA. Antes do recolhimento, confirme se houve
   alteração na legislação aplicável (MVA, alíquotas, protocolos e
   convênios)."*
3. **No frontend**: modal de confirmação antes de gerar a carta/export —
   mesmo padrão da confirmação "não há CT-e": o clique de "estou ciente,
   verifiquei a legislação" grava quem/quando na trilha de auditoria.
   Se alguma matriz usada estiver "envelhecida" (radar do 4.3), o modal
   destaca isso em vez do texto genérico.

Isso transforma o aviso de um texto decorativo em um **controle com trilha**:
fica provado que o usuário foi alertado, com data e responsável.

---

## 5. Impactos

**Arquitetura** — mudança aditiva: duas tabelas novas, extratores novos no
módulo que já existe, um campo novo nas matrizes, endpoints de revisão. O
motor puro, os ports, os loaders, a RLS e o modelo de vigência ficam
intocados. Os goldens do motor não são afetados (nenhuma regra de cálculo
muda).

**Manutenção** — o trabalho da equipe muda de natureza: de digitar dados a
revisar diffs. O risco operacional migra dos erros de digitação (hoje) para a
manutenção dos parsers (amanhã). Mitigação: o contrato fetch/parse já isola o
I/O, os testes rodam o parser contra amostras fixas sem rede
(`test_crawler_confaz.py` já faz isso), e a quebra de layout degrada para
alerta — nunca para dado errado nem falha silenciosa.

**Confiabilidade** — sobe por quatro vias: (1) fonte auditável linha a linha
(snapshot + base_legal + trilha de aprovação); (2) detecção de mudança tira a
dependência de "alguém ficar sabendo"; (3) radar de frescor expõe o que está
velho em vez de fingir que está tudo certo; (4) o fail-closed continua sendo
a última linha de defesa — se a base estiver incompleta, o motor trava com
erro catalogado, como hoje.

**Custo** — fase própria (crawlers): só tempo de desenvolvimento; fontes
públicas gratuitas (INLABS requer cadastro). Fase provedor comercial
(opcional): assinatura mensal — decisão de negócio separada, viabilizada
pelo port.

---

## 6. Estratégia de implementação

Fases pequenas, cada uma com valor próprio, na ordem que reduz risco mais
rápido. Esforço relativo: P (dias), M (≈1 semana), G (>1 semana).

| Fase | Entrega | Esforço | Observações |
|---|---|---|---|
| **1. Fundação** | Tabelas `FonteSnapshot` + `PropostaAtualizacao`, migração Alembic, tela de revisão com diff, migração do job CEST/CONFAZ para a fila (e confirmação da URL estável — pendência de go-live) | **M-G** | Destrava todas as demais; primeira carga aprovável em lote |
| **2. Aviso + saúde** | Aviso de legislação (carta, export, modal com trilha), `ultima_verificacao_em`, painel Saúde das Matrizes, job de staleness | **M** | Atende o requisito do aviso; valor imediato mesmo sem novos crawlers |
| **3. Protocolos + radar DOU** | `ConfazProtocolosExtractor` (pares UF em uso), `InlabsDouMonitor` (alertas) | **M** | Ataca o maior fail-closed do motor (`ERRO_PROTOCOLO_NAO_AVALIADO`) |
| **4. Alíquotas/FCP assistidas** | Job semestral de reconferência por UF + pendências prontas para confirmar | **P** | 27 linhas; esforço mínimo, elimina risco real (caso AL) |
| **5. MVA** | Extração assistida das Portarias SUTRI-MG (PDF→proposta com confiança) e/ou ativação do `ProvedorMatrizesPort` | **G** | Decidir com base no custo do provedor × esforço do parser; priorizar por uso real (NCMs das notas) |
| **6. Pauta/PMPF** | Extrator dos Atos COTEPE/PMPF | **M** | Amarra com o roadmap grande do motor já pendente |

**Riscos e mitigações**

| Risco | Mitigação |
|---|---|
| Portal muda layout/URL e o parser quebra | fetch/parse separados; teste com amostra fixa; hash detecta mudança; quebra vira alerta, nunca dado errado |
| Extração propõe valor errado | Nada entra sem aprovação humana com diff + documento-fonte; rejeição suprime re-proposta; goldens do motor seguem como rede de segurança |
| Fila de revisão vira gargalo/ruído | Só propõe quando o hash da fonte muda; aprovação em lote por fonte; priorização por uso real |
| Rate-limit/bloqueio dos portais | Cadência mensal/semanal (não tempo real); User-Agent identificado (já feito); padrão de pausa progressiva + retry 429 já existente (OpenCNPJ) |
| Falsa sensação de "base sempre certa" | Aviso pré-emissão com trilha + painel de frescor dizem explicitamente o que foi verificado e quando |
| Dependência de provedor pago | Port isola o fornecedor; trocar ou sair não afeta o resto |

**Boas práticas asseguradas** — jobs idempotentes (chave de upsert com
vigência, já é o padrão); commit do job antes do `.delay` (padrão do
projeto); sessão por unidade de trabalho no worker; tabelas globais fora da
RLS, mas escrita restrita a curadores (`NEXOS_MATRIZ_CURADORES` passa a
valer também para aprovar propostas); pytest com amostras fixas por fonte;
nenhuma regressão nos goldens.

---

## 7. Decisões em aberto (para o João)

1. **UFs prioritárias** além de MG (posso levantar pela base de notas quais
   pares UF→UF aparecem de verdade).
2. **Provedor comercial**: quer que eu levante custo/condições de Systax,
   Econet e LegisWeb para comparar com o esforço da Fase 5, ou seguimos 100%
   com fontes públicas por ora?
3. **Cadência dos crawlers**: mensal (como o job CEST atual) é suficiente, ou
   protocolos/DOU valem checagem semanal?
4. **Texto final do aviso** na carta — o rascunho da seção 4.4 segue o tom
   sem acusação; ajustar à vontade.
