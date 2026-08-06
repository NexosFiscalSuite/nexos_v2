# Estado da base de matrizes de ICMS-ST — o que está automatizado e o que não está

**Atualizado em:** 06/08/2026 · Documento irmão de
[`proposta_automacao_matrizes_st.md`](proposta_automacao_matrizes_st.md).

Este documento responde uma pergunta só, sem otimismo: **para quais UFs a base
do motor de ST se alimenta sozinha, e onde ela depende de trabalho manual?**

## Resposta curta

**Só Minas Gerais tem MVA extraída de fonte oficial.** Nas outras seis UFs em
que o escritório tem clientes (SP, PR, RJ, RS, GO, DF), a matriz de MVA está
vazia ou tem apenas o que a curadoria digitou/importou — não existe robô lendo
o RICMS ou as portarias desses estados. Enquanto isso for verdade, ligar o
fail-closed do motor nessas UFs transforma quase todo item de ST em "não
auditável".

O que o sistema faz por conta própria hoje é: (a) manter o **universo NCM×CEST**
das 7 UFs em dia pelo CONFAZ, (b) extrair **MVA e Protocolos de MG** do Anexo
VII do RICMS/2023, (c) **vigiar** as fontes e avisar quando mudam. Extrair MVA
das demais UFs ainda não foi feito.

## Cobertura por matriz e por UF

Legenda: **auto** = robô lê a fonte oficial e propõe · **semeado** = valores
conferidos à mão e embutidos na carga inicial, com reconferência semestral
automática · **manual** = só entra pela tela ou por CSV · **—** = nada.

| Matriz | MG | SP | PR | RJ | RS | GO | DF | Demais 20 UFs |
|---|---|---|---|---|---|---|---|---|
| Enquadramento (NCM×CEST) | auto | auto | auto | auto | auto | auto | auto | manual |
| **MVA** | **auto** | **manual** | **manual** | **manual** | **manual** | **manual** | **manual** | **manual** |
| Protocolos (acordos) | auto (UF→MG) | manual | manual | manual | manual | manual | manual | manual |
| Alíquota modal | semeado | semeado | semeado | semeado | semeado | semeado | semeado | manual |
| FCP | manual | manual | manual | semeado (geral 2%) | manual | manual | manual | manual |
| Pauta/PMPF | não se aplica¹ | — | — | — | — | — | — | — |

¹ MG saiu do PMPF pela Portaria SUTRI 1.518/2025 (efeitos 01/11/2025): a MVA do
Anexo VII passou a ser a base. Nas demais UFs a pauta continua existindo e o
sistema **não** a lê — é um buraco conhecido, não uma decisão.

## Detalhe do que cada automação faz (e não faz)

### Enquadramento — CONFAZ, Convênio ICMS 142/2018
Job mensal (dia 1º). Baixa a relação nacional NCM×CEST e propõe linhas de
regime ST para as 7 UFs alvo. **Limite honesto:** o CONFAZ publica o UNIVERSO
possível; a adesão é de cada estado. Uma proposta aprovada aqui diz "este item
pode estar em ST nesta UF", não "está". Por isso nada entra sem curadoria.

### MVA de MG — SEFAZ-MG, RICMS/2023 Anexo VII, Parte 2
Job mensal (dia 2). Lê as 7 páginas HTML do anexo, ancorado na célula do CEST,
e propõe a margem por NCM×CEST. Desde 06/08/2026 a proposta carrega também a
**UF de origem**, traduzida da coluna "Âmbito de Aplicação": a margem vale na
operação interna (origem MG) e nas entradas das UFs com acordo, menos as
exceções do item. Antes disso tudo caía em "qualquer origem" e o motor podia
aplicar a margem de um par a outro.

**Limites honestos:**
- Item sem margem publicada na fonte fica de fora (não vira 0%, não vira palpite).
- Mesma chave com margens conflitantes na fonte fica de fora (ambíguo).
- Nota de rodapé por item ("* Relativamente ao item…") não é interpretada — o
  curador confere na fonte.
- Código de âmbito que a legenda não define cai em "qualquer origem".
- A data legal exata de uma mudança de margem não é publicada por item: a
  proposta usa o 1º dia do mês da detecção e o curador corrige se souber.

### Protocolos — legenda de âmbito do mesmo Anexo VII
Extrai acordos **UF→MG apenas**, escopados por NCM. Os pares que não terminam
em MG (ex.: MG→SP, SP→RJ) seguem manuais. Além disso há um **radar semanal** do
índice de Protocolos do CONFAZ que só detecta mudança e avisa — não extrai dado.

### Alíquotas e FCP
A carga inicial semeia 8 linhas de alíquota (7 UFs, RJ com duas vigências) e o
FCP geral do RJ, com base legal conferida em fontes cruzadas em 04/08/2026. Um
job semestral (jan/jul) devolve cada linha à fila como REVALIDAR: aprovar
significa "continua valendo" e renova o carimbo de verificação. FCP por produto
(PR FECOP, SP FECOEP, RS AMPARA, GO PROTEGE, MG FEM) é manual por NCM.

## O que falta para "base completa", por UF

Ordem de esforço crescente. Nenhum destes itens pode ser resolvido "estimando"
margem: MVA é dado normativo publicado, e o que não estiver na fonte tem de
faltar visivelmente em vez de virar número.

1. **MG** — perto de completo para ST. Falta: FCP por produto (fonte própria,
   Lei 6.763/75 art. 12-A) e conferência das notas de rodapé do Anexo VII.
2. **SP** — maior volume depois de MG. A MVA vive nas Portarias CAT/SRE, uma
   por segmento, em HTML/PDF separados. É a próxima extração com melhor
   relação custo/benefício, e é trabalho de crawler novo (não sai de graça do
   que já existe).
3. **PR, RJ, RS, GO, DF** — MVA em anexos/portarias estaduais, formatos
   distintos entre si. Enquanto não houver crawler, o caminho é o **relatório
   de lacunas** (abaixo): carrega-se só o que as notas realmente usam.
4. **Protocolos dos pares que não terminam em MG** — hoje 100% manual; o radar
   avisa que mudou, mas quem lê e cadastra é uma pessoa.
5. **Pauta/PMPF fora de MG** — nenhuma leitura. Fase 6 da proposta.

## O caminho que dispensa cadastrar item a item

O relatório de **lacunas de MVA** (`CoberturaService.lacunas_mva`) responde,
para uma empresa/competência: quais pares NCM×CEST×(origem→destino) as notas
importadas usam e a matriz de MVA não cobre — ordenados pelo valor em jogo. A
mesma lista sai em CSV **já no layout do importador de matrizes**, com a coluna
`mva_original` vazia: o escritório preenche só a margem (da fonte oficial da UF)
e sobe o arquivo de volta.

Isso muda a natureza do trabalho: em vez de cadastrar cada item quando ele
falha na auditoria, carrega-se de uma vez o que a carteira realmente movimenta,
começando pelo que pesa mais em dinheiro. É também o que diz quando a base está
pronta o suficiente para ligar o fail-closed do motor: quando o valor sem MVA
cair para perto de zero na competência auditada.

## Regra que não muda

Nenhuma margem entra na base sem fonte. O robô propõe o que leu, o curador
aprova, e o que não existe na fonte oficial aparece como lacuna — nunca como
0%, nunca como estimativa, nunca como "média do segmento".
