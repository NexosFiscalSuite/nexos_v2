# ADR-0002: Temporalidade (vigência) obrigatória nas matrizes fiscais

**Status:** Aceito
**Data:** 2026-06-24
**Deciders:** Dono do produto / Tech lead (João Vitor)
**Relacionado:** [[ADR-0001]] (agregação de frete); módulo `fiscal/domain/st` (motor puro).

---

## Contexto

O motor de ST audita uma nota **pela data em que ela foi emitida**, não por "hoje".
A legislação muda o tempo todo: MVAs, alíquotas internas, adicionais de FCP e as
próprias listas de ST entram e saem. Exemplos reais já mapeados no "Cérebro
Tributário":
- **SP — Portaria SRE 64/2025:** exclui itens da ST a partir de **01/01/2026**.
- **AL — Lei 9.776/2025:** modal 19% → 20,5% a partir de **01/04/2026** (dupla vigência no mesmo ano).
- **MG — FCP de bebidas:** 2% até 2025-12-31, 1% a partir de 2026-01-01.

Uma tabela estática `NCM | MVA` responde "qual a taxa atual?". O motor precisa
responder **"qual era a taxa vigente em `data_emissao`?"** — pergunta diferente.
Auditar uma nota de 2025 com a regra de 2026 gera divergência falsa (ou mascara
uma real).

## Decisão

**Toda matriz de referência fiscal carrega vigência temporal (valid-time):**
- `data_inicio_vigencia DATE NOT NULL`
- `data_fim_vigencia DATE NULL` (NULL = vigente em aberto)

Regras:
1. **Busca sempre filtra pela data da operação** (`data_emissao` da nota):
   `data_op >= data_inicio_vigencia AND (data_fim_vigencia IS NULL OR data_op <= data_fim_vigencia)`.
   Os ports do domínio (`MvaRepository`, `EnquadramentoRepository`, `FcpRepository`)
   **já recebem `data: date`** — o domínio foi desenhado para isto desde o v1.
2. **Encerrar, nunca apagar:** mudança de taxa = setar `data_fim_vigencia` na linha
   antiga e **inserir** uma nova. O histórico é preservado para reauditar notas
   antigas (e para defesa fiscal).
3. **Desempate de busca:** `ORDER BY LENGTH(ncm) DESC` (fallback 8→6→4),
   depois `data_inicio_vigencia DESC`, `LIMIT 1`.
4. **Sem sobreposição:** duas linhas vigentes para a mesma chave na mesma data é
   erro de carga — a rotina de seed/atualização valida antes de inserir.

Escopo: apenas **valid-time** (quando a regra valeu no mundo real). NÃO vamos
implementar transaction-time (quando soubemos disso) no v1 — bitemporalidade
fica como evolução futura se a auditoria exigir "o que o sistema sabia em X".

## Opções Consideradas

### Opção A — Vigência em cada matriz (valid-time) — ESCOLHIDA
**Prós:** responde à pergunta certa (taxa na data da nota); preserva histórico;
alinhada ao que as próprias matrizes do Vault já descrevem. **Contras:** todo
SELECT carrega o filtro de data; índices incluem a data.

### Opção B — Tabela estática "taxa atual" + histórico em log à parte
**Cons:** reauditar nota antiga exige reconstruir o passado a partir do log;
propenso a erro; o motor teria de saber consultar dois lugares. **Rejeitada.**

### Opção C — Versionar por competência (string AAAA-MM)
**Cons:** mudança no meio do mês (ex.: AL 01/04) não cabe; granularidade de mês
é insuficiente. **Rejeitada** em favor de datas.

## Consequências

- **Fica mais fácil:** reauditar qualquer período; aplicar mudanças futuras sem
  destruir o passado; rastrear o ato legal por linha (`ato_legal`).
- **Fica mais difícil / a vigiar:** toda query precisa do filtro de vigência
  (encapsular num helper para não esquecer); índices compostos com data;
  validação de não-sobreposição na carga.
- **A revisitar:** bitemporalidade (transaction-time) caso a fiscalização exija
  "qual regra o sistema aplicou na época do processamento".

## Action Items (Fase 1)

1. [ ] Mixin `VigenciaTemporal` (colunas `data_inicio_vigencia`/`data_fim_vigencia`)
   reutilizado por todas as matrizes.
2. [ ] Helper de query `filtrar_vigencia(stmt, coluna_data, data_op)` para o filtro
   padrão (DRY — uma única implementação da regra).
3. [ ] Índices compostos incluindo `data_inicio_vigencia`.
4. [ ] Seed com vigência explícita (nunca sem `data_inicio_vigencia`).
5. [ ] Teste: auditar a MESMA chave em duas datas diferentes deve retornar taxas
   diferentes (prova viva da vigência).
