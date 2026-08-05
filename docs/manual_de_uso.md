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
