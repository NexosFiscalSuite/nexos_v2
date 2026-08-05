# Manual de uso — Nexos Fiscal (Sol Contabilidade)

**Passo a passo da plataforma, tarefa por tarefa.** Atualizado em 05/08/2026.
Escrito para quem vai usar no dia a dia — sem jargão onde dá.

---

## 1. Primeiros passos

1. Acesse **fiscal.solsistema.com.br** e entre com seu e-mail e senha;
2. No **primeiro acesso**, o sistema oferece um **tour guiado de 2 minutos**
   — vale fazer. Para refazer depois, clique no **?** no canto superior direito;
3. Os dois controles que valem para o sistema inteiro ficam no **topo direito**:
   - **Competência** (ex.: Jul/26) — todas as telas mostram esse mês;
   - **Empresa** — escolha o cliente que você vai trabalhar. Sem empresa
     selecionada, as telas de notas/divergências pedem para escolher;
4. O menu fica na **barra lateral** (recolha pela setinha na borda). Seu nome
   e e-mail aparecem no rodapé dela.

## 2. Trabalho de rotina — o caminho feliz

O ciclo mensal de um cliente, do começo ao fim:

### 2.1 Importar os XMLs

1. Menu **Upload** → arraste os arquivos (XML solto ou **.zip** com vários);
2. A importação roda em segundo plano — acompanhe a barra de progresso.
   Pode sair da tela; quando voltar, o resultado estará lá;
3. Notas repetidas são ignoradas sozinhas (pode reimportar sem medo).

### 2.2 Conferir as notas

Menu **Documentos Fiscais → Notas**:

- **Busca livre** (nº da NF, chave, nome, CNPJ) + filtros por tipo e situação;
- Clique numa nota para ver os detalhes, **baixar XML/DANFE**, ajustar o
  **tipo de item** ou o CFOP quando o De/Para não resolveu;
- Ações em lote: selecione várias notas para cancelar/reativar, trocar CFOP
  ou baixar em .zip.

### 2.3 Conformidade (quebras de sequência)

Menu **Conformidade**: mostra os números de nota que **faltam** na sequência
de emissão. Para cada quebra: localize a nota (cancelada? não emitida?) e
registre a **ciência** com a classificação — fica documentado quem tratou.

### 2.4 Divergências de ICMS-ST — o coração do sistema

Menu **Divergências ST**. O motor recalcula o ST de cada item e aponta o que
não bate. A tela se lê de cima para baixo:

1. **Abas Entradas × Saídas** — fornecedores que erraram na retenção ×
   erros na emissão própria do cliente;
2. **Cards do dinheiro em jogo** (ST a recolher, a favor, antecipações, não
   auditáveis) — **clique num card para filtrar** a lista por aquela situação;
3. **Ranking de fornecedores** — quem cobrar primeiro, pelo valor;
4. **Lista de notas** — clique para expandir os itens. Em cada item:
   - O **selo colorido** diz a situação; **clique no selo** para abrir o
     balão com a explicação em português e a **ação sugerida**;
   - **"Abrir memória de cálculo"** mostra a conta completa (base, MVA,
     alíquotas, frete, base legal) — é o que você usa para defender o número;
   - Ações rápidas no próprio balão, conforme o caso: **Cadastrar matriz**
     (abre o cadastro já preenchido), **Não há acordo** (registra a ausência
     de protocolo no par de UFs), **Importar CT-e** / **Não há CT-e** (gate
     do frete — a confirmação fica registrada no seu usuário).

### 2.5 Cobrar o fornecedor (carta) e registrar o desfecho (triagem)

1. No **ranking**, clique em **Carta PDF** no fornecedor desejado;
2. O sistema pede a **ciência da legislação** (os valores saem das Matrizes;
   confirme que não houve mudança recente na norma). Sua confirmação fica
   registrada — e a carta sai com a data da última verificação da base;
3. A carta lista item a item (sem antecipações, que são obrigação do
   cliente) e **marca os itens como "Cobrada"** automaticamente;
4. Quando o fornecedor responder, registre o desfecho no item (ícone **🏷**):
   - **Justificada** — apresentou base normativa; o apontamento baixa;
   - **Aceita** — o cliente assume e recolhe;
   - Errou? Volte para **Em aberto**;
5. O filtro **Triagem** ("Em aberto", "Cobradas"…) responde *"o que ainda
   falta cobrar?"* num clique. **Exportar Excel** leva o filtro junto.

### 2.6 Fechar o período

- **Reprocessar Pendentes** — depois de cadastrar matrizes/CT-e que
  faltavam, reaudita as notas travadas;
- **Diagnóstico (PDF)** — o retrato executivo de TODO o período do cliente
  (conformidade e dinheiro em jogo por competência) — bom para reunião;
- **Relatórios** (Documentos Fiscais → Relatórios) — o gerador avançado com
  modelos próprios do escritório.

## 3. Matrizes Fiscais — a base de regras do motor

Menu **Cadastros → Matrizes Fiscais**. São as regras GLOBAIS (valem para
todos os clientes). As abas:

| Aba | O que é | Quando mexer |
|---|---|---|
| **MVA** | Margem por NCM+CEST+UF | Cadastro manual ou aprovação do robô |
| **Enquadramento** | O produto é ST naquela UF? | Idem |
| **FCP** | Fundo de Combate à Pobreza por UF/NCM | Pouco muda |
| **Alíquotas** | Alíquota interna de cada UF | Pouco muda |
| **Protocolos** | Acordos entre UFs que ativam a ST interestadual | Sempre que a aba Saúde apontar par pendente |
| **Revisão** | Fila de propostas dos robôs | **Toda semana** (veja 3.1) |
| **Saúde** | Frescor da base + pares interestaduais | Toda semana |
| **Cobertura** | O que a carteira movimenta × o que está cadastrado | Ao importar cliente novo |

Recursos comuns a todas: filtros combináveis (UF + NCM + CEST), paginação,
**Exportar/Importar Planilha** (o export vazio serve de modelo), e **vigência**
— taxa mudou? **Encerre a vigência da linha antiga e crie uma nova**; nunca
edite o valor por cima (o motor usa a regra vigente na data de cada nota).

> Quer entender **como o motor usa cada matriz no cálculo**? Veja o
> apêndice na seção 7 — o passo a passo completo, com exemplo numérico.

### 3.1 Aba Revisão — aprovar o que os robôs propõem

Os robôs (CEST do CONFAZ, MVA de MG, reconferência semestral) **nunca gravam
direto**: cada mudança vira uma proposta aqui. O chip na aba mostra quantas
esperam.

1. Filtre por matriz/UF; clique na proposta para ver o **diff** (vigente ×
   proposto) e a fonte;
2. **Aprovar** aplica na matriz (com sua identificação). **Aprovar tudo
   (filtro atual)** faz em lote — conflitos não travam, viram relatório;
3. **Rejeitar** (com motivo) vale para sempre — a mesma proposta não volta;
4. Propostas **"Reconferência"** (chegam a cada semestre): é só confirmar que
   a alíquota/FCP **continua valendo** — nada muda, o carimbo renova. Se a
   lei mudou, rejeite e ajuste pelo cadastro com vigência nova.

### 3.2 Aba Saúde — o radar

- **Cartões**: % da base verificada nos últimos 90 dias (verde/âmbar/
  vermelho), a data que sai no aviso da carta e as propostas pendentes;
- **Tabela por matriz**: "regra envelhecida não é regra errada — é regra que
  ninguém confere há tempo";
- **Pares interestaduais**: par **vermelho** = notas reais travadas
  (`protocolo não avaliado`), ordenado por valor. Clique **Cadastrar
  protocolo** (já vem preenchido). Não há acordo entre as UFs? Cadastre com
  situação **"SEM ACORDO"** — o registro explícito também destrava.

## 4. Cadastros do dia a dia

- **Clientes e Fornecedores** (menu Cadastros): a lista de contrapartes da
  empresa selecionada. A **lupa** busca os dados pela Receita ao digitar o
  CNPJ. O selo **"revisar"** marca cadastro que veio incompleto do XML;
- **IBS/CBS 2026** (menu próprio): a verificação da Reforma Tributária no
  ano-teste — mesma lógica de selos/balões das divergências, com carta própria.

## 5. Administração (perfil admin)

- **Empresas**: os clientes do escritório. Cadastro individual (lupa da
  Receita), **em lote via planilha** e **atualização em massa pela Receita**;
- **Acessos → Grupos**: quem vê o quê. Usuário comum e supervisor só
  enxergam as empresas dos grupos em que estão; **só admin vê tudo**.
  Supervisor sem grupo não vê empresa nenhuma;
- **Acessos → Usuários**: criar, trocar papel, inativar;
- **Acessos → Auditoria**: a trilha de tudo (quem fez o quê e quando) —
  inclusive aprovações de matrizes, ciências de legislação e triagens.

## 6. Perguntas frequentes

- **"Não auditável" é erro?** — Não. É o motor sendo honesto: falta uma
  regra (matriz/protocolo/CT-e) para calcular com certeza. O balão do selo
  diz exatamente o que falta e tem o botão que resolve;
- **Por que aparece o aviso de legislação antes da carta?** — Os valores
  saem das matrizes cadastradas e a lei muda. Sua confirmação fica na trilha
  e protege o escritório;
- **A triagem some se reprocessar?** — Não, ela sobrevive à reauditoria;
- **Rejeitei uma proposta por engano** — Ela não volta à fila; cadastre a
  regra manualmente pela aba da matriz;
- **Nota antiga não audita** — Confira se existe matriz **vigente na data de
  emissão** da nota (a aba Cobertura ajuda a ver o que falta).

---

## 7. Apêndice — o cálculo do ST por dentro (passo a passo detalhado)

O motor segue sempre a mesma trilha, item a item, nota a nota. A regra de
ouro é **fail-closed**: em qualquer passo, se falta informação para calcular
com certeza, o item **não é calculado por palpite** — ele vira "não
auditável" com um código que diz exatamente o que falta. Todo número que o
motor produz fica gravado na **memória de cálculo** (o botão "Abrir memória
de cálculo" do item), com a base legal das regras usadas.

### Passo 0 — O que o motor lê da nota

Do XML de cada item: **NCM**, **CEST**, CFOP, **CST/CSOSN**, valores
(produto, frete, seguro, IPI, desconto), o grupo de ST declarado (base e
valor retidos), as **UFs** de origem e destino, o regime do emitente (CRT) e
o **modBCST** (como o emitente disse que calculou a base). Dos CT-e
vinculados: o frete "por fora" que precisa entrar na base.

### Passo 1 — Portão de enquadramento (matriz Enquadramento)

Pergunta: **este produto é de Substituição Tributária na UF de destino?**

- O motor busca NCM×CEST×UF na matriz de Enquadramento, do mais específico
  ao mais geral: NCM com **8 dígitos → 6 → 4** (a regra de capítulo cobre o
  que não tem regra própria);
- XML **sem CEST**? O motor tenta pelo NCM. Se todos os CEST daquele NCM têm
  o mesmo regime, segue; se houver regimes diferentes, o portão abre por
  segurança (ST) e a divergência aparece para o analista decidir;
- Resultado: **ST** (segue o cálculo), **TN** (tributação normal — item sai
  do motor), **ST_ENTRADA** (antecipação) — ou, sem linha na matriz, o item
  trava como não auditável ("sem enquadramento").

### Passo 2 — Portão do acordo entre UFs (matriz Protocolos)

Só para operação **interestadual**. Pergunta: **existe protocolo/convênio
que obrigue o emitente a reter o ST para a UF de destino?**

A resposta tem **três estados** — e isso importa:

| Situação na matriz | O que o motor faz |
|---|---|
| Acordo **ATIVO** para o par (e o NCM, se o acordo for por produto) | O emitente devia reter → o motor cobra a retenção |
| **SEM_ACORDO** registrado | Ninguém obriga o emitente → vira **antecipação do destinatário** (obrigação do cliente, não do fornecedor) |
| **Nenhuma linha** para o par | O motor **não adivinha**: trava com "protocolo não avaliado" até a curadoria registrar uma coisa ou outra |

Registrar "não há acordo" é tão importante quanto registrar o acordo — os
dois destravam o motor, com efeitos diferentes.

### Passo 3 — Base do ICMS próprio (e o gate do frete)

Base = **valor do produto + frete + seguro + outras despesas + IPI −
desconto**. Detalhe que muda tudo: se o frete foi por **CT-e separado** e o
cliente é o tomador, esse frete PRECISA entrar na base. Por isso o gate: se
a nota indica frete por conta do destinatário e **não há CT-e vinculado nem
confirmação de que não existe**, o motor trava o item ("frete pendente de
CT-e") em vez de calcular uma base menor em silêncio. Importar o CT-e (ou
confirmar a ausência, que fica registrada) destrava e reaudita sozinho.

### Passo 4 — MVA: original ou ajustada? (matrizes MVA e Alíquotas)

A MVA cadastrada na matriz é a **original** (operação interna). Em operação
**interestadual**, a lei manda **ajustar** a margem para equalizar a carga —
porque o ICMS próprio veio menor (alíquota interestadual de 12% ou 4%) do
que viria numa compra interna:

```
MVA ajustada = [ (1 + MVA original) × (1 − alíquota inter) ÷ (1 − alíquota interna efetiva) ] − 1
```

A "alíquota interna efetiva" sai da matriz de **Alíquotas** (modal + FCP
integrado, quando houver). O **modBCST** do XML diz como o emitente
calculou; quando ele está ausente, a matriz decide a estratégia (margem ×
valor da operação) — e usar MVA ajustada quando não devia é exatamente o
erro "MVA ajustada indevida" que o motor aponta.

### Passo 5 — O ST devido (e o FCP)

```
Base ST   = Base própria × (1 + MVA aplicável)
ICMS-ST   = Base ST × alíquota interna − ICMS próprio destacado
FCP-ST    = Base ST × alíquota de FCP (matriz FCP, por UF/NCM)
```

A dedução do ICMS próprio é **estrita**: deduz o que foi DESTACADO no XML —
se o emitente zerou o próprio, isso aparece como divergência própria ("ICMS
próprio zerado"), não é compensado em silêncio.

### Passo 6 — Confronto com o XML

O motor compara o que **calculou** com o que o emitente **declarou** (base e
valor do ST, FCP), com tolerância de centavos (arredondamento não vira
cobrança). Diferença relevante → item **DIVERGENTE** com o código do
catálogo: valor do ST divergente, base divergente, dedução incorreta, FCP
omitido, ST indevido em revenda (CST 60 — já retido antes), antecipação do
destinatário… Cada código carrega a **ação sugerida** que aparece no balão.

### Exemplo numérico completo (caso real do laboratório)

Autopeça, **SP → MG**, CST 10, item de R$ 731,35 com frete por CT-e
separado de R$ 136,10 rateado entre 2 itens (R$ 68,05 cada). O emitente
declarou o grupo de ST mas **zerou** base e valor:

| Passo | Conta | Resultado |
|---|---|---|
| Enquadramento | NCM 8708.29.19 + CEST 01.075.00 em MG | ST ✔ |
| Protocolo | SP→MG com acordo ATIVO (autopeças) | retenção devida ✔ |
| Base própria | 731,35 + frete CT-e 68,05 | **R$ 799,40** |
| MVA ajustada | (1+0,7178) × (1−0,12) ÷ (1−0,18) − 1 | **84,35 %** |
| Base do ST | 799,40 × 1,8435 | **R$ 1.473,69** |
| ICMS-ST | 1.473,69 × 18 % − ICMS próprio 87,76 | **R$ 177,50** |
| Confronto | XML declarou R$ 0,00 | **DIVERGENTE — R$ 177,50 a recolher** |

É esse R$ 177,50 (por item) que aparece no card "ST a recolher", no ranking
do fornecedor e na carta — com a memória de cálculo inteira anexada.

### As matrizes, uma a uma

**Enquadramento (NCM×CEST×UF)** — o portão de entrada. Alimentada pelo robô
do CONFAZ (Convênio ICMS 142/2018 — o "universo" nacional do CEST) e
refinada pela curadoria: a **adesão de cada UF é decisão do analista** (o
robô nunca sobrepõe uma linha manual — se você marcou TN de propósito, fica
TN). Sem linha → "sem enquadramento".

**Protocolos (UF origem → UF destino)** — o portão interestadual, tri-state
(ATIVO / SEM_ACORDO / sem linha). O acordo pode valer para o **par inteiro**
(NCM vazio) ou **por produto** (uma linha por NCM — é assim que o robô
cadastra a partir da legenda de âmbito do Anexo VII de MG, com a base legal
no formato "Protocolo ICMS 103/12 — Anexo VII, âmbito 2.1"). Situações
DENUNCIADO/INATIVO encerram o efeito do acordo.

**MVA (NCM×CEST×UF)** — a margem **original**; a ajustada é sempre
calculada, nunca cadastrada. Alimentada pelo robô do Anexo VII do RICMS/MG
(1.080 pares) e pela curadoria nas demais UFs. Regra da casa: **margem
específica do escritório prevalece** — linha manual nunca é alterada pelo
robô; mudança detectada na fonte vira proposta de **nova vigência** na aba
Revisão.

**Alíquotas (por UF)** — a alíquota modal interna (débito do ST) e o **FCP
integrado** (que só entra no denominador do ajuste de MVA). É a matriz que
resolve casos como AL 19 % → 20,5 % em 01/04/2026: duas linhas, cada uma com
sua vigência — a nota de março usa 19, a de maio usa 20,5.

**FCP (por UF e NCM)** — o adicional do Fundo de Combate à Pobreza somado ao
ST. `GERAL` vale para a UF inteira (caso do RJ, 2 %); NCM específico vale só
para o produto (casos de PR/SP/RS/GO/DF/MG, que têm FCP por lista de
produtos — curadoria conforme a demanda das notas).

**Vigência em todas elas (a regra de ouro)** — o motor usa a regra **vigente
na data de emissão de cada nota**, nunca "a atual". Por isso taxa que muda
vira **linha nova** (encerra a antiga, abre outra): a MVA da cerveja pode
ser 40 % para a nota de 2025 e 55 % para a de 2026, e as duas auditorias
ficam defensáveis para sempre.
