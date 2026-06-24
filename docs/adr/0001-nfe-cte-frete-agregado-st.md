# ADR-0001: Vínculo N:N entre NF-e e CT-e e agregação de frete para o Motor de ST

**Status:** Aceito
**Data:** 2026-06-24
**Deciders:** Dono do produto / Tech lead (João Vitor)
**Contexto técnico:** backend Python / FastAPI / SQLAlchemy (async) + Celery; módulo `fiscal` com o domínio puro do Motor de Auditoria de ICMS-ST já implementado (`app/modules/fiscal/domain/st`).

---

## Contexto

O Motor de ST audita **por item**, e a base de cálculo do ST inclui o **frete** rateado por item (Seção 4.1 do `CALC_ICMS_ST`; rateio na Seção 3 do `CALC_ICMS_Proprio`). Validamos isso no laboratório: o caso da autopeça (SP→MG) só fechou os R$ 177,50 quando o frete de um **CT-e separado** (R$ 136,10) entrou na base do ST, rateado em R$ 68,05/item.

No mundo real esse frete **não vem dentro da NF-e** — vem em um ou mais **CT-e** distintos. E o relacionamento não é 1:1:

- Uma NF-e pode ter **vários CT-e** vinculados (redespacho, transporte multimodal, subcontratação).
- Um CT-e pode referenciar **várias NF-e** (carga consolidada). No XML, as chaves vinculadas ficam em `infCte/infCTeNorm/infDoc/infNFe/chave` (lista, 1..N).

Logo, na origem dos dados o vínculo é **N:N**. O requisito de negócio "1 NF-e → N CT-e" é um recorte desse N:N.

**Estado atual do código (a evoluir):**
- O parser de CT-e (`parser._parse_cte`) já extrai `vTPrest` (valor da prestação), mas **não** extrai as chaves de NF-e vinculadas.
- CT-e é persistido como `Nota` com `fluxo="cte"` e um item sintético `TRANSP`. **Não há tabela de vínculo** NF-e↔CT-e.
- Importação é **incremental e fora de ordem**: um CT-e pode chegar antes da sua NF-e (já temos o precedente do "evento órfão" em `NotaEvento`).

**Forças em jogo:**
- O frete agregado só é conhecido depois que **todos** os CT-e da NF-e foram importados — e eles chegam em momentos arbitrários.
- O cálculo do ST não pode usar um frete "congelado" no import se um CT-e adicional chegar depois.
- Precisão de centavos: o rateio precisa de compensação de arredondamento (já especificada no `CALC_ICMS_Proprio`, Seção 3).
- Tudo é tenant-scoped (RLS).

---

## Decisão

1. **Modelar o vínculo como N:N** numa tabela de associação dedicada (`nfe_cte_vinculo`), chaveada por **chave de acesso** (não por FK direta de id), para tolerar importação fora de ordem (vínculo "órfão" até a NF-e existir — mesmo padrão de `NotaEvento`).
2. **O parser de CT-e passa a extrair a lista de chaves de NF-e vinculadas** (`infNFe/chave`, 1..N) e registra um vínculo por chave.
3. **A agregação do frete é feita no momento do cálculo** (lazy), não no import: o pipeline soma o `vTPrest` de **todos** os CT-e vinculados àquela chave de NF-e → **Custo de Frete Agregado Total**. Isso garante que um CT-e que chegue depois entre no recálculo.
4. **Rateio proporcional** do frete agregado pelos itens da NF-e, reutilizando o `Fator_Rateio_Item = vProd_item / Σ vProd_itens` com **compensação de centavos no último item** (Seção 3 do `CALC_ICMS_Proprio`).
5. **O Motor de ST permanece puro e ignorante de tudo isso**: ele recebe o `ItemFiscal` já **enriquecido** (`v_frete` = fração do frete agregado). A orquestração (parser → vínculo → agregação → rateio → motor) vive na camada de aplicação, não no domínio.

```
[Parser CT-e] --(chaves NF-e)--> [nfe_cte_vinculo]  (N:N, por chave, tolera órfão)
                                          |
[Auditoria da NF-e] --> soma vTPrest de TODOS os CT-e vinculados = Frete Agregado
                                          |
                          rateio por item (fator vProd_i / Σ vProd) + ajuste de centavos
                                          |
                       ItemFiscal(v_prod=..., v_frete=fração)  -->  StAuditEngine
```

---

## Opções Consideradas

### Opção A — Tabela de vínculo N:N por chave + agregação no cálculo (ESCOLHIDA)
| Dimensão | Avaliação |
|----------|-----------|
| Complexidade | Média |
| Custo | Baixo (1 tabela + 1 serviço de agregação) |
| Escalabilidade | Boa (índice por chave; agregação é um SUM) |
| Familiaridade do time | Alta (mesmo padrão de `NotaEvento` órfão) |

**Prós:** suporta N:N real; tolera import fora de ordem; recálculo sempre correto (CT-e tardio é incluído); domínio do motor permanece puro; rateio reaproveita regra já documentada.
**Contras:** o frete não é um valor "materializado" na NF-e — exige join/agregação a cada cálculo (mitigável com cache/coluna derivada se virar gargalo).

### Opção B — Denormalizar: gravar o frete agregado na NF-e no momento do import
| Dimensão | Avaliação |
|----------|-----------|
| Complexidade | Baixa |
| Custo | Baixo |
| Escalabilidade | Boa (leitura direta) |
| Familiaridade do time | Alta |

**Prós:** cálculo lê um campo pronto.
**Contras:** **fica obsoleto** se um CT-e chegar depois da NF-e (e eles chegam fora de ordem); precisaria de reprocessamento/invalidção; esconde a origem do número (pior para auditoria/defesa fiscal). **Rejeitada** pelo risco de frete desatualizado.

### Opção C — Assumir 1:1 (um CT-e por NF-e)
**Cons:** quebra redespacho/multimodal/carga consolidada — exatamente o cenário real que motivou a ADR. **Rejeitada.**

---

## Trade-off Analysis

O eixo decisivo é **quando** o frete é consolidado. Como os XMLs chegam de forma incremental e fora de ordem, materializar no import (B) produz valores corretos só por acaso (se o último CT-e chegar antes do cálculo). Agregar no momento do cálculo (A) é sempre correto ao custo de uma agregação barata por chave. A pureza do motor é preservada em ambas, mas A mantém a **rastreabilidade** (a memória de cálculo pode listar quais CT-e compuseram o frete) — essencial para a "memória de cálculo aberta" do `REL_Divergencia_ST`.

---

## Consequências

**Fica mais fácil:**
- Auditar redespacho/multimodal sem casos especiais.
- Explicar o frete na memória de cálculo (quais CT-e entraram).
- Reprocessar: como a agregação é lazy, importar um CT-e novo "conserta" o cálculo sem migração de dados.

**Fica mais difícil / a vigiar:**
- Cada auditoria faz uma agregação por chave (monitorar; se virar gargalo, materializar com invalidação por evento de import).
- Definir a política de rateio quando o CT-e referencia **várias** NF-e (o `vTPrest` é do CT-e inteiro): decidir se rateia o CT-e entre as NF-e por valor antes de agregar por NF-e. **A revisitar** na fase de implementação.

**A revisitar:**
- Frete que **não** compõe a base do ST em certas UFs/modalidades (ex.: pauta/PMC — o frete não soma; ver Regra de Ouro da Seção 4.2 do `CALC_ICMS_ST`). A agregação deve ser condicional ao `modBCST`.
- CT-e de devolução/complementar/anulação (tpCTe) não deve somar como frete normal.

---

## Action Items (fase de banco de dados + parsers — NÃO agora)

1. [ ] Parser de CT-e: extrair a lista `infCte/infCTeNorm/infDoc/infNFe/chave` (1..N) + `tpCTe` (normal/complementar/anulação).
2. [ ] Migration: tabela `nfe_cte_vinculo` (`tenant_id`, `chave_nfe`, `chave_cte`, `vtprest`, `tp_cte`), tenant-scoped (RLS), índice por `chave_nfe`.
3. [ ] `ImportService`: ao processar CT-e, gravar um vínculo por chave de NF-e (tolerando NF-e ainda inexistente — vínculo órfão, igual a `NotaEvento`).
4. [ ] Serviço de aplicação `FreteAggregator`: dado `chave_nfe`, somar `vtprest` dos CT-e vinculados (filtrando `tpCTe` que não soma) → Frete Agregado.
5. [ ] `RateioService`: distribuir o Frete Agregado pelos itens (`vProd_i / Σ vProd`) com compensação de centavos no último item (Seção 3 do `CALC_ICMS_Proprio`).
6. [ ] Orquestrador da auditoria: montar `ItemFiscal` com `v_frete` enriquecido e instanciar o `StAuditEngine` (o motor não muda).
7. [ ] Caso de regressão: NF-e com 2 itens + 2 CT-e vinculados, conferindo o rateio e o fechamento de centavos.
8. [ ] Decidir o rateio de CT-e que aponta para múltiplas NF-e (ver Trade-off).

---

## Relação com o que já existe
- O **Motor de ST** (`app/modules/fiscal/domain/st`) **não muda** — ele já recebe `v_frete` por item; esta ADR só define como esse valor é produzido a montante.
- Reaproveita o padrão de **vínculo por chave tolerante a órfão** já usado em `NotaEvento` (cancelamento/CC-e que chegam antes da nota).
- Cumpre as regras de rateio e composição de base documentadas no "Cérebro Tributário" (`CALC_ICMS_Proprio` §3, `CALC_ICMS_ST` §4).
