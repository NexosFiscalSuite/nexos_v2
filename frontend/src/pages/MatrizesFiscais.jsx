import { useState, useEffect, useCallback, useRef } from 'react'
import BalaoAjuda from '../components/BalaoAjuda'
import Dropdown from '../components/Dropdown'
import ErroCarga from '../components/ErroCarga'
import ResumoImportModal from '../components/ResumoImportModal'
import SelectUf from '../components/SelectUf'
import { api, saveBlob } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'
import { UF_QUALQUER } from '../constants/ufs'

const pct = (v) => (v == null || v === '' ? '—' : `${Number(v).toFixed(2)}%`)
const dataBr = (s) => (s ? s.split('-').reverse().join('/') : '—')
const vigencia = (m) =>
  `${dataBr(m.data_inicio_vigencia)} ${m.data_fim_vigencia ? `– ${dataBr(m.data_fim_vigencia)}` : '(em aberto)'}`
const dataCadastro = (m) =>
  m.created_at ? new Date(m.created_at).toLocaleDateString('pt-BR') : '—'

// Paginação no SERVIDOR: a base auto-alimentada (CONFAZ × 7 UFs) tem dezenas
// de milhares de linhas — a tela busca uma página por vez.
const PAGE_SIZE = 50
// Números de página com janela: 1 … 4 [5] 6 … 20 (mesmo padrão de Empresas).
function paginasVisiveis(atual, total) {
  const nums = []
  for (let i = 1; i <= total; i++) {
    if (i === 1 || i === total || Math.abs(i - atual) <= 2) nums.push(i)
    else if (nums[nums.length - 1] !== '…') nums.push('…')
  }
  return nums
}

const REGIME_OPTS = [
  { value: 'ST', label: 'ST — Substituição Tributária' },
  { value: 'TN', label: 'TN — Tributação Normal' },
  { value: 'ST_ENTRADA', label: 'ST na Entrada (antecipação)' },
]

const badge = (txt, tone = 'info') => (
  <span className="badge" style={{
    background: `var(--${tone}-bg)`, color: `var(--${tone}-text)`,
  }}>{txt}</span>
)

// Como a UF de origem aparece na listagem: "*" é regra geral, não um estado.
const badgeOrigem = (uf) => badge(
  !uf || uf === UF_QUALQUER ? 'Qualquer' : uf,
  'warn',
)

// Ajuda do campo "UF de origem" da MVA — a MVA muda conforme o estado de onde
// a mercadoria sai, então a tela precisa explicar o que o coringa significa.
const AJUDA_UF_ORIGEM = {
  titulo: 'Origem da mercadoria: regra geral ou regra do par',
  texto: (
    <>
      A MVA pode variar conforme o estado de onde a mercadoria sai.
      Deixe em <strong>“Qualquer origem”</strong> quando a mesma margem valer
      para todos os fornecedores, venham de onde vierem — é a regra geral e o
      padrão da tela. Escolha um estado quando aquela origem tiver margem
      própria: aí vale só para o par origem → destino, e essa regra específica
      tem preferência sobre a geral.
    </>
  ),
}

// Linha de apoio abaixo do seletor: diz, em texto corrido, o que a escolha
// atual significa — o balão fica para quem quiser o detalhe.
const dicaUfOrigem = (v) => {
  if (!v) return 'Escolha a origem da mercadoria — ou “Qualquer origem”, que é a regra geral.'
  if (v === UF_QUALQUER) return 'Regra geral: vale para mercadoria vinda de qualquer estado. É o padrão.'
  return `Regra específica: vale só quando a mercadoria sai de ${v}, e tem preferência sobre a regra geral.`
}

// ── Alíquota: a do estado (GERAL) × a do produto (NCM) ──
// Até aqui a alíquota interna era só por UF. Produto com alíquota própria na
// lei (cesta básica, medicamento) era calculado pela modal do estado e a ST
// saía maior do que a devida. "GERAL" é a regra do estado — o padrão e o que
// já existia; um NCM cria a regra do produto, que vence a geral (8→6→4→GERAL).
const NCM_GERAL = 'GERAL'
const ehGeral = (v) => String(v ?? '').trim().toUpperCase() === NCM_GERAL

// Na listagem, "GERAL" não é um NCM — vira rótulo, como o "Qualquer" da origem.
const badgeNcmAliquota = (m) => (ehGeral(m.ncm) ? badge('Geral', 'info') : <span className="mono">{m.ncm}</span>)

const AJUDA_NCM_ALIQUOTA = {
  titulo: 'Alíquota do estado ou alíquota daquele produto',
  texto: (
    <>
      Quase todo produto paga a alíquota geral do estado — é a linha
      {' '}<strong>“GERAL”</strong>, o padrão da tela e o que já existia aqui.
      Só que alguns produtos têm alíquota própria na lei: cesta básica e
      medicamento, por exemplo, costumam ficar abaixo da geral. Para esses,
      cadastre uma linha com o <strong>NCM do produto</strong>: ela tem
      preferência sobre a geral na hora do cálculo (a busca tenta 8 dígitos,
      depois 6, depois 4 e só então usa a geral). Sem essa linha, o produto é
      calculado pela alíquota cheia do estado e a ST fica maior do que a devida.
    </>
  ),
}

const dicaNcmAliquota = (v) => {
  if (ehGeral(v)) return 'Vale para todo produto do estado que não tenha linha própria. É o padrão.'
  if (!v) return 'Informe o NCM do produto — 4, 6 ou 8 dígitos.'
  return `Vale só para o NCM ${v} neste estado, e tem preferência sobre a alíquota geral.`
}

const AJUDA_RED_BC_ST = {
  titulo: 'Redução da base de cálculo da ST',
  texto: (
    <>
      Alguns produtos têm, por lei do estado de destino, a base da ST reduzida
      em um percentual. Até agora o sistema enxergava só a redução que veio
      declarada no XML — ou seja, repetia a conta do fornecedor. Com o
      percentual da norma cadastrado aqui, a conta passa a ser a da lei: se o
      que veio na nota for diferente, a diferença aparece como divergência,
      para mais ou para menos. Em branco = sem redução.
      <br /><br />
      A redução é sempre de um produto, então só entra em linha
      com <strong>NCM</strong>. Numa linha <strong>“GERAL”</strong> ela valeria
      para todo produto do estado, o que não existe na lei — por isso o campo
      fica desligado ali.
    </>
  ),
}

const DICA_RED_BC_ST =
  'Percentual de redução previsto na lei do destino para este NCM. Em branco = sem redução.'

// Motivo do bloqueio (texto curto) ou null quando o campo está liberado.
const bloqueioRedBcSt = (form) => (
  ehGeral(form?.ncm)
    ? 'A alíquota geral do estado não tem redução de base — ela valeria para todo produto daqui. '
      + 'Em “Vale para”, escolha “Um produto (NCM)” e o campo libera.'
    : null
)

// ── Campos comuns de vigência (todas as matrizes herdam) ──
const VIGENCIA_CAMPOS = [
  { key: 'data_inicio_vigencia', label: 'Início da vigência', type: 'date', required: true },
  { key: 'data_fim_vigencia', label: 'Fim da vigência (vazio = em aberto)', type: 'date' },
]

const ABAS = [
  {
    id: 'mva', label: 'MVA', icon: 'ti-percentage',
    api: { list: api.matrizesMva, create: api.criarMatrizMva, update: api.editarMatrizMva, remove: api.removerMatrizMva },
    descricao: 'MVA Original por NCM + CEST + UF de origem → UF de destino — a margem que o motor aplica na base da ST',
    empty: { icon: 'ti-percentage', title: 'Nenhuma matriz de MVA', sub: 'Cadastre a MVA Original por NCM, CEST e UF de destino. A origem pode ficar em “Qualquer origem” quando a margem vale para todos os fornecedores.' },
    colunas: [
      { key: 'ncm', label: 'NCM', mono: true },
      { key: 'cest', label: 'CEST', mono: true },
      { key: 'uf_origem', label: 'UF Origem', render: (m) => badgeOrigem(m.uf_origem) },
      { key: 'uf_destino', label: 'UF Destino', render: (m) => badge(m.uf_destino) },
      { key: 'mva_original', label: 'MVA Original', align: 'right', strong: true, render: (m) => pct(m.mva_original) },
      { key: 'base_legal', label: 'Base Legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
      { key: 'created_at', label: 'Cadastro', muted: true, small: true, render: dataCadastro },
    ],
    campos: [
      { key: 'ncm', label: 'NCM', required: true, placeholder: '40111000' },
      { key: 'cest', label: 'CEST', required: true, placeholder: '0107500' },
      // A MVA varia com o estado remetente: sem a origem, a mesma margem era
      // aplicada a todo fornecedor e o cálculo saía errado nos pares que têm
      // margem própria. Padrão "*" = vale para qualquer origem.
      { key: 'uf_origem', label: 'UF de origem', uf: true, coringa: true, required: true,
        padrao: UF_QUALQUER, ajuda: AJUDA_UF_ORIGEM, dica: dicaUfOrigem },
      { key: 'uf_destino', label: 'UF de destino', uf: true, required: true },
      { key: 'mva_original', label: 'MVA Original (%)', type: 'number', required: true, placeholder: '42.00' },
      { key: 'base_legal', label: 'Base Legal', full: true, placeholder: 'Decreto 48.589/2023' },
      ...VIGENCIA_CAMPOS,
    ],
  },
  {
    id: 'enquadramento', label: 'Enquadramento', icon: 'ti-list-check',
    api: { list: api.matrizesEnquadramento, create: api.criarMatrizEnquadramento, update: api.editarMatrizEnquadramento, remove: api.removerMatrizEnquadramento },
    descricao: 'Define se o NCM/CEST é Substituição Tributária na UF de destino — o portão de entrada do motor',
    empty: { icon: 'ti-list-check', title: 'Nenhum enquadramento', sub: 'Diga ao motor quais produtos são ST (ou Normais) em cada UF de destino.' },
    colunas: [
      { key: 'ncm', label: 'NCM', mono: true },
      { key: 'cest', label: 'CEST', mono: true },
      { key: 'uf_destino', label: 'UF', render: (m) => badge(m.uf_destino) },
      { key: 'regime', label: 'Regime', render: (m) => badge(m.regime, m.regime === 'ST' ? 'ok' : 'warn') },
      { key: 'segmento', label: 'Segmento', muted: true },
      { key: 'base_legal', label: 'Base Legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
      { key: 'created_at', label: 'Cadastro', muted: true, small: true, render: dataCadastro },
    ],
    campos: [
      { key: 'ncm', label: 'NCM', required: true, placeholder: '40111000' },
      { key: 'cest', label: 'CEST', required: true, placeholder: '0107500' },
      { key: 'uf_destino', label: 'UF destino', uf: true, required: true },
      { key: 'regime', label: 'Regime', type: 'select', options: REGIME_OPTS, required: true },
      { key: 'segmento', label: 'Segmento', placeholder: 'Autopeças' },
      { key: 'base_legal', label: 'Base Legal', placeholder: 'Protocolo ICMS 41/2008' },
      ...VIGENCIA_CAMPOS,
    ],
  },
  {
    id: 'fcp', label: 'FCP', icon: 'ti-coin',
    api: { list: api.matrizesFcp, create: api.criarMatrizFcp, update: api.editarMatrizFcp, remove: api.removerMatrizFcp },
    descricao: 'Fundo de Combate à Pobreza por UF (e NCM) — o adicional que o motor soma à ST',
    empty: { icon: 'ti-coin', title: 'Nenhuma alíquota de FCP', sub: 'Cadastre o FCP-ST por UF. Use NCM "GERAL" para valer em toda a UF.' },
    colunas: [
      { key: 'uf_destino', label: 'UF', render: (m) => badge(m.uf_destino) },
      { key: 'ncm', label: 'NCM', mono: true },
      { key: 'aliq_fcp_st', label: 'FCP-ST', align: 'right', strong: true, render: (m) => pct(m.aliq_fcp_st) },
      { key: 'aliq_fcp_interno', label: 'FCP interno', align: 'right', muted: true, render: (m) => pct(m.aliq_fcp_interno) },
      { key: 'base_legal', label: 'Base Legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
      { key: 'created_at', label: 'Cadastro', muted: true, small: true, render: dataCadastro },
    ],
    campos: [
      { key: 'uf_destino', label: 'UF', uf: true, required: true },
      { key: 'ncm', label: 'NCM (ou GERAL)', placeholder: 'GERAL' },
      { key: 'aliq_fcp_st', label: 'Alíquota FCP-ST (%)', type: 'number', required: true, placeholder: '2.00' },
      { key: 'aliq_fcp_interno', label: 'FCP interno (%)', type: 'number', placeholder: '2.00' },
      { key: 'base_legal', label: 'Base Legal', full: true, placeholder: 'Lei 14.470/2002' },
      ...VIGENCIA_CAMPOS,
    ],
  },
  {
    id: 'aliquotas', label: 'Alíquotas', icon: 'ti-receipt-tax',
    api: { list: api.matrizesAliquotas, create: api.criarMatrizAliquota, update: api.editarMatrizAliquota, remove: api.removerMatrizAliquota },
    descricao: 'Alíquota interna do ICMS na UF de destino (com FCP integrado): a geral do estado e as alíquotas próprias por NCM, como cesta básica e medicamento — vigentes na data de emissão da nota',
    empty: { icon: 'ti-receipt-tax', title: 'Nenhuma alíquota cadastrada', sub: 'Cadastre a alíquota geral de cada UF (linha “GERAL”) e, quando o produto tiver alíquota própria na lei, uma linha com o NCM dele. Sem a geral, o motor não audita notas para a UF.' },
    colunas: [
      { key: 'uf_destino', label: 'UF', render: (m) => badge(m.uf_destino) },
      { key: 'ncm', label: 'NCM', render: badgeNcmAliquota },
      { key: 'aliq_modal', label: 'Alíquota', align: 'right', strong: true, render: (m) => pct(m.aliq_modal) },
      { key: 'aliq_fcp_integrado', label: 'FCP integrado', align: 'right', muted: true, render: (m) => pct(m.aliq_fcp_integrado) },
      // Só a linha de NCM pode ter redução — na geral a coluna fica vazia.
      { key: 'p_red_bc_st', label: 'Redução da base', align: 'right', muted: true,
        render: (m) => (Number(m.p_red_bc_st) > 0 ? pct(m.p_red_bc_st) : '—') },
      { key: 'base_legal', label: 'Base Legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
      { key: 'created_at', label: 'Cadastro', muted: true, small: true, render: dataCadastro },
    ],
    campos: [
      { key: 'uf_destino', label: 'UF destino', uf: true, required: true },
      // Nasce em GERAL: a regra do estado é o padrão e o que já existia.
      { key: 'ncm', label: 'Vale para', type: 'ncm-geral', required: true,
        padrao: NCM_GERAL, ajuda: AJUDA_NCM_ALIQUOTA, dica: dicaNcmAliquota },
      { key: 'aliq_modal', label: 'Alíquota interna (%)', type: 'number', required: true, placeholder: '18.00' },
      { key: 'aliq_fcp_integrado', label: 'FCP integrado (%)', type: 'number', placeholder: '0.00' },
      // Redução de base é do produto: fica visível sempre (para o usuário saber
      // que existe), mas desligada com o motivo à vista enquanto for GERAL.
      { key: 'p_red_bc_st', label: 'Redução da base da ST (%)', type: 'number', placeholder: '0.00',
        omitirSeVazio: true, bloqueio: bloqueioRedBcSt, ajuda: AJUDA_RED_BC_ST, dica: DICA_RED_BC_ST },
      { key: 'base_legal', label: 'Base Legal', full: true, placeholder: 'Lei 9.776/2025 (AL)' },
      ...VIGENCIA_CAMPOS,
    ],
  },
  {
    id: 'protocolos', label: 'Protocolos', icon: 'ti-license',
    api: { list: api.matrizesProtocolos, create: api.criarMatrizProtocolo, update: api.editarMatrizProtocolo, remove: api.removerMatrizProtocolo },
    descricao: 'Protocolos e Convênios que ativam a ST interestadual — define o par UF origem → destino com acordo',
    empty: { icon: 'ti-license', title: 'Nenhum protocolo cadastrado', sub: 'Cadastre os acordos (Protocolos/Convênios ICMS) que ativam a ST entre a UF de origem e a de destino.' },
    colunas: [
      { key: 'uf_origem', label: 'UF Origem', render: (m) => badge(m.uf_origem, 'warn') },
      { key: 'uf_destino', label: 'UF Destino', render: (m) => badge(m.uf_destino) },
      { key: 'ncm', label: 'NCM', mono: true, render: (m) => m.ncm || 'par inteiro' },
      { key: 'numero_acordo', label: 'Acordo', strong: true },
      { key: 'situacao', label: 'Situação', render: (m) => badge(
          m.situacao === 'SEM_ACORDO' ? 'SEM ACORDO' : (m.situacao || 'ATIVO'),
          m.situacao === 'ATIVO' || !m.situacao ? 'ok' : (m.situacao === 'SEM_ACORDO' ? 'warn' : 'err'),
        ) },
      { key: 'base_legal', label: 'Base Legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
      { key: 'created_at', label: 'Cadastro', muted: true, small: true, render: dataCadastro },
    ],
    campos: [
      { key: 'uf_origem', label: 'UF Origem', uf: true, required: true },
      { key: 'uf_destino', label: 'UF Destino', uf: true, required: true },
      { key: 'numero_acordo', label: 'Acordo', required: true, placeholder: 'Protocolo ICMS 41/2008' },
      { key: 'situacao', label: 'Situação', type: 'select', required: true, options: [
        { value: 'ATIVO', label: 'ATIVO — acordo vigente (ativa a ST)' },
        { value: 'SEM_ACORDO', label: 'SEM ACORDO — registro de que NÃO há acordo (antecipação)' },
        { value: 'DENUNCIADO', label: 'DENUNCIADO — acordo encerrado' },
        { value: 'INATIVO', label: 'INATIVO — acordo suspenso' },
      ] },
      { key: 'ncm', label: 'NCM (vazio = par inteiro)', placeholder: '40117000' },
      { key: 'base_legal', label: 'Base Legal', placeholder: 'Decreto estadual que ratifica' },
      ...VIGENCIA_CAMPOS,
    ],
  },
  {
    id: 'revisao', label: 'Revisão', icon: 'ti-inbox', custom: true,
    descricao: 'Propostas dos robôs de auto-alimentação — nada entra nas matrizes sem aprovação da curadoria',
  },
  {
    id: 'saude', label: 'Saúde', icon: 'ti-activity-heartbeat', custom: true,
    descricao: 'O frescor da base: quanto foi verificado nos últimos 90 dias e o que está envelhecendo',
  },
  {
    id: 'cobertura', label: 'Cobertura', icon: 'ti-radar-2', custom: true,
    descricao: 'O que a carteira movimenta × o que as matrizes cobrem — a fila de curadoria, ordenada por valor',
  },
]

// ── Saúde: linhas com UF fora do padrão ─────────────────────────────────────
// Os campos de UF eram digitados à mão até a virada para lista fechada. O que
// ficou gravado antes disso continua no banco: "Minas Gerais", "mg", "XX". O
// motor procura a regra pela sigla de duas letras que vem no XML, então uma
// linha dessas aparece na tela, parece cadastrada e NUNCA é aplicada.
const ROTULO_CAMPO_UF = { uf_origem: 'UF de origem', uf_destino: 'UF de destino' }
const comoEstaGravado = (v) => (v == null || v === '' ? 'em branco' : `“${v}”`)

const AJUDA_UF_FORA_PADRAO = {
  titulo: 'Por que uma UF escrita “errada” apaga a regra',
  texto: (
    <>
      Na nota fiscal o estado vem sempre como sigla de duas letras — MG, SP, RJ.
      É por ela que o motor procura a regra na matriz. Enquanto este campo era
      digitado à mão, dava para gravar “Minas Gerais”, “mg” ou até “XX”, e essas
      linhas ficaram no banco.
      <br /><br />
      O problema não é estético: a linha continua aparecendo na tela, com cara de
      cadastro pronto, e o motor simplesmente não a encontra. A nota é auditada
      como se a regra não existisse — o cálculo sai errado sem ninguém perceber
      que faltou alguma coisa.
      <br /><br />
      A correção é escolher a sigla no seletor e salvar. Quando dá para deduzir
      qual é (“Minas Gerais” só pode ser MG), a tela já sugere; quando não dá,
      quem decide é você.
    </>
  ),
}

function UfsForaDoPadrao({ dados, onCorrigir }) {
  const total = dados?.total || 0
  if (!total) return null
  const amostra = dados.amostra || []
  const limite = dados.limite_amostra || amostra.length
  return (
    <div className="card" style={{ padding: 0, marginBottom: 18, borderLeft: '3px solid var(--err-text)' }}>
      <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-2)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 600 }}>Linhas com o estado fora do padrão</span>
          {badge(`${total.toLocaleString('pt-BR')} ${total === 1 ? 'linha' : 'linhas'}`, 'err')}
          <BalaoAjuda titulo={AJUDA_UF_FORA_PADRAO.titulo}>{AJUDA_UF_FORA_PADRAO.texto}</BalaoAjuda>
        </div>
        <div style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55, marginTop: 6 }}>
          Estas regras estão cadastradas, aparecem na tela e o motor não consegue
          encontrá-las: ele procura o estado pela sigla de duas letras da nota, e
          aqui está gravada outra coisa. Na prática a nota é calculada como se a
          regra não existisse — erro silencioso, com cara de resolvido.
        </div>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead>
            <tr>
              <th>Matriz</th><th>Campo</th><th>Como está gravado</th>
              <th>Sigla certa</th><th></th>
            </tr>
          </thead>
          <tbody>
            {amostra.map(it => (
              <tr key={`${it.matriz}-${it.id}-${it.campo}`}>
                <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{TIPOS_PROPOSTA[it.matriz] || it.matriz}</td>
                <td style={{ color: 'var(--text-3)' }}>{ROTULO_CAMPO_UF[it.campo] || it.campo}</td>
                <td className="mono">{comoEstaGravado(it.valor)}</td>
                <td>
                  {it.sugestao
                    ? badge(it.sugestao, 'ok')
                    : <span style={{ color: 'var(--text-4)', fontSize: 12 }}>não dá para deduzir — você decide</span>}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button className="btn btn-secondary btn-sm" style={{ whiteSpace: 'nowrap' }}
                    title={it.sugestao
                      ? `Abre a linha na aba ${TIPOS_PROPOSTA[it.matriz] || it.matriz} já com ${it.sugestao} escolhido — você confere e salva`
                      : `Abre a linha na aba ${TIPOS_PROPOSTA[it.matriz] || it.matriz} para você escolher o estado`}
                    onClick={() => onCorrigir?.(it)}>
                    <i className="ti ti-pencil" /> Abrir para corrigir
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-4)', borderTop: '1px solid var(--border-2)' }}>
        {total > amostra.length
          ? `Mostrando as ${amostra.length} primeiras de ${total.toLocaleString('pt-BR')} — o teto da amostra é ${limite}. Corrija estas e recarregue a aba para ver as próximas.`
          : 'Nenhuma correção é feita sozinha: cada linha só muda quando você abre, confere e salva.'}
      </div>
    </div>
  )
}

// ── Saúde: radar de frescor da base (Fase 2) + pares interestaduais (Fase 3) ──
function SaudePanel({ onCadastrarPar, onCorrigirUf }) {
  const { toasts } = useToast()
  const [dados, setDados] = useState(null)
  const [pares, setPares] = useState(null)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try {
      const [saude, prs] = await Promise.all([api.saudeMatrizes(), api.paresInterestaduais()])
      setDados(saude)
      setPares(prs)
    }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { carregar() }, [carregar])

  if (loading) return <div className="center-loader"><div className="spinner" /></div>
  if (erro) return <ErroCarga mensagem={erro} onRetry={carregar} />

  const g = dados?.geral || {}
  const tomPct = (p) => (p == null ? 'var(--text-3)' : p >= 90 ? 'var(--ok-text)' : p >= 60 ? 'var(--warn-text)' : 'var(--err-text)')
  const dataHora = (s) => (s ? new Date(s).toLocaleDateString('pt-BR') : '—')
  // Servidor sem o radar de UF (versão anterior) simplesmente não mostra a
  // coluna — a aba continua inteira em vez de encher a tela de traços.
  const temRadarUf = dados?.ufs_invalidas != null

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(200px, 1fr))', gap: 16, marginBottom: 18 }}>
        <div className="card">
          <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>Verificado nos últimos {g.janela_dias || 90} dias</div>
          <div className="tnum" style={{ fontSize: 34, fontWeight: 800, marginTop: 8, color: tomPct(g.pct_verificado_90d) }}>
            {g.pct_verificado_90d == null ? '—' : `${g.pct_verificado_90d}%`}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>das {Number(g.vigentes || 0).toLocaleString('pt-BR')} regras vigentes hoje</div>
        </div>
        <div className="card">
          <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>Última atualização da base</div>
          <div className="tnum" style={{ fontSize: 34, fontWeight: 800, marginTop: 8 }}>{dataHora(g.ultima_atualizacao)}</div>
          <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>é a data que sai no aviso da carta de ST</div>
        </div>
        <div className="card">
          <div style={{ fontSize: 11, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 600 }}>Propostas aguardando revisão</div>
          <div className="tnum" style={{ fontSize: 34, fontWeight: 800, marginTop: 8, color: g.propostas_pendentes > 0 ? 'var(--warn-text)' : 'var(--ok-text)' }}>
            {Number(g.propostas_pendentes || 0).toLocaleString('pt-BR')}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 4 }}>dos robôs de auto-alimentação (aba Revisão)</div>
        </div>
      </div>

      <UfsForaDoPadrao dados={dados?.ufs_invalidas} onCorrigir={onCorrigirUf} />

      <div className="card" style={{ padding: 0 }}>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead>
              <tr>
                <th>Matriz</th>
                <th style={{ textAlign: 'right' }}>Regras vigentes</th>
                <th style={{ textAlign: 'right' }}>Verificadas (90d)</th>
                <th>Frescor</th>
                {temRadarUf && <th>Estado fora do padrão</th>}
                <th>Verificação mais antiga</th>
                <th>Mais recente</th>
              </tr>
            </thead>
            <tbody>
              {(dados?.matrizes || []).map(m => (
                <tr key={m.tipo}>
                  <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{TIPOS_PROPOSTA[m.tipo] || m.tipo}</td>
                  <td className="tnum" style={{ textAlign: 'right' }}>{Number(m.vigentes).toLocaleString('pt-BR')}</td>
                  <td className="tnum" style={{ textAlign: 'right' }}>{Number(m.verificadas_90d).toLocaleString('pt-BR')}</td>
                  <td>
                    {m.pct_90d == null
                      ? <span style={{ color: 'var(--text-4)', fontSize: 12 }}>sem regras</span>
                      : badge(`${m.pct_90d}%`, m.pct_90d >= 90 ? 'ok' : m.pct_90d >= 60 ? 'warn' : 'err')}
                  </td>
                  {temRadarUf && (
                    <td>
                      {m.ufs_invalidas > 0
                        ? badge(`${Number(m.ufs_invalidas).toLocaleString('pt-BR')} sem efeito`, 'err')
                        : <span style={{ color: 'var(--text-4)', fontSize: 12 }}>nenhuma</span>}
                    </td>
                  )}
                  <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{dataHora(m.verificacao_mais_antiga)}</td>
                  <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{dataHora(m.ultima_atualizacao)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-4)', borderTop: '1px solid var(--border-2)' }}>
          Verificar = alguém cadastrou, editou, reimportou a planilha ou aprovou uma proposta da linha.
          Regra envelhecida não é regra errada — é regra que ninguém confere há tempo.
        </div>
      </div>

      {/* Pares interestaduais (Fase 3): movimento real × curadoria de protocolos */}
      {(pares?.pares || []).length > 0 && (
        <div className="card" style={{ padding: 0, marginTop: 18 }}>
          <div style={{ padding: '12px 16px', fontWeight: 600, borderBottom: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', gap: 10 }}>
            <span>Pares interestaduais da carteira</span>
            {pares.nao_avaliados > 0 && badge(`${pares.nao_avaliados} travando o motor`, 'err')}
            <span style={{ fontWeight: 400, color: 'var(--text-4)', fontSize: 12 }}>
              — par sem curadoria de protocolo deixa as notas interestaduais sem auditar
            </span>
          </div>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Par (origem → destino)</th>
                  <th style={{ textAlign: 'right' }}>Notas</th>
                  <th style={{ textAlign: 'right' }}>Valor movimentado</th>
                  <th>Situação</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {pares.pares.map(p => (
                  <tr key={`${p.uf_origem}-${p.uf_destino}`}>
                    <td>
                      {badge(p.uf_origem, 'warn')}
                      <i className="ti ti-arrow-right" style={{ margin: '0 6px', color: 'var(--text-4)', fontSize: 13 }} />
                      {badge(p.uf_destino)}
                    </td>
                    <td className="tnum" style={{ textAlign: 'right' }}>{Number(p.notas).toLocaleString('pt-BR')}</td>
                    <td className="tnum" style={{ textAlign: 'right', fontWeight: 600 }}>{brl(p.valor)}</td>
                    <td>
                      {!p.curado
                        ? badge('Não avaliado — trava o motor', 'err')
                        : p.acordos_ativos > 0
                          ? badge(`Curado · ${p.acordos_ativos} acordo(s) ativo(s)`, 'ok')
                          : badge('Curado — sem acordo (antecipação)', 'info')}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      {!p.curado && (
                        <button className="btn btn-secondary btn-sm"
                          title="Abre o cadastro de protocolo já preenchido com o par"
                          onClick={() => onCadastrarPar?.(p)}>
                          <i className="ti ti-plus" /> Cadastrar protocolo
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: '10px 16px', fontSize: 12, color: 'var(--text-4)', borderTop: '1px solid var(--border-2)' }}>
            Não há acordo no par? Cadastre com situação “SEM ACORDO” — o registro explícito também
            é curadoria e libera o motor (vira antecipação do destinatário).
          </div>
        </div>
      )}
    </div>
  )
}

// ── Revisão: fila de propostas da auto-alimentação (robô propõe, curador decide) ──
const ACOES_PROPOSTA = {
  INSERIR: { label: 'Nova regra', tone: 'ok' },
  ATUALIZAR: { label: 'Alteração', tone: 'warn' },
  NOVA_VIGENCIA: { label: 'Nova vigência', tone: 'warn' },
  ENCERRAR_VIGENCIA: { label: 'Encerrar vigência', tone: 'err' },
  REVALIDAR: { label: 'Reconferência', tone: 'info' },
}
const TIPOS_PROPOSTA = {
  enquadramento: 'Enquadramento', mva: 'MVA', fcp: 'FCP',
  aliquotas: 'Alíquotas', protocolos: 'Protocolos',
}
const CAMPOS_DIFF = {
  regime: 'Regime', segmento: 'Segmento', mva_original: 'MVA Original',
  aliq_modal: 'Alíquota modal', aliq_fcp_integrado: 'FCP integrado',
  aliq_fcp_st: 'FCP-ST', aliq_fcp_interno: 'FCP interno',
  p_red_bc_st: 'Redução da base da ST',
  numero_acordo: 'Acordo', situacao: 'Situação', base_legal: 'Base legal',
  data_inicio_vigencia: 'Início da vigência', data_fim_vigencia: 'Fim da vigência',
}
const fmtDiff = (v) => {
  if (v == null || v === '') return '—'
  const s = String(v)
  return /^\d{4}-\d{2}-\d{2}$/.test(s) ? dataBr(s) : s
}
// ── MVA aprendida das próprias notas ────────────────────────────────────────
// Só MG publica a margem em fonte oficial. Nas demais UFs a MVA é digitada uma
// a uma, e quem precisa cadastrar tudo à mão acaba usando o aplicativo oficial
// em vez desta tela. Saída: o robô junta o percentual de MVA que os
// fornecedores já declaram nas notas e, quando VÁRIOS fornecedores
// independentes convergem no mesmo número, sugere na fila de revisão.
//
// A diferença que a tela precisa deixar gritante: proposta de fonte oficial
// vem com a norma no bolso (base legal preenchida); esta NÃO tem norma
// nenhuma. É um ponto de partida bem embasado, não uma regra publicada.
const FONTE_APRENDIDA = 'notas-do-escritorio'
const ehAprendida = (p) => Boolean(p?.evidencia)
  || String(p?.fonte || '').toLowerCase().startsWith(FONTE_APRENDIDA)

// A evidência é o que permite julgar o número — sem ela o curador aprovaria no
// escuro. Todas as chaves são opcionais: o painel degrada campo a campo se o
// servidor mandar menos do que o previsto.
function lerEvidencia(ev) {
  if (!ev || typeof ev !== 'object') return null
  const num = (...ks) => {
    for (const k of ks) if (ev[k] != null && ev[k] !== '') return Number(ev[k])
    return null
  }
  // ATENÇÃO à ordem das chaves: no contrato do backend a margem de cada faixa
  // vem em `mva`, e `valor` ali é DINHEIRO (soma dos itens). Ler `valor`
  // primeiro imprimiria "3000,00%" de margem na tabela — número absurdo numa
  // tela fiscal, e do tipo que destrói a confiança no resto.
  const faixa = (d) => ({
    valor: d.mva ?? d.margem ?? d.valor ?? null,
    notas: d.notas ?? null,
    fornecedores: d.fornecedores ?? null,
  })
  const dist = Array.isArray(ev.distribuicao)
    ? ev.distribuicao.map(faixa)
    : (ev.distribuicao && typeof ev.distribuicao === 'object'
      ? Object.entries(ev.distribuicao).map(([valor, notas]) => (
        { valor, notas: Number(notas), fornecedores: null }))
      : [])
  const per = ev.periodo && typeof ev.periodo === 'object' ? ev.periodo : {}
  return {
    fornecedores: num('fornecedores', 'qtd_fornecedores'),
    notas: num('notas', 'qtd_notas'),
    valor: ev.mva ?? ev.valor ?? ev.mva_original ?? null,
    concordancia: num('concordancia', 'pct_concordancia'),
    distribuicao: dist,
    inicio: per.primeira_emissao || per.inicio || per.de || ev.periodo_inicio || null,
    fim: per.ultima_emissao || per.fim || per.ate || ev.periodo_fim || null,
  }
}

// "3 fornecedores diferentes, 17 notas, todas com 42.00%"
function fraseEvidencia(e) {
  if (!e) return null
  const partes = []
  if (e.fornecedores != null) {
    partes.push(`${e.fornecedores} ${e.fornecedores === 1 ? 'fornecedor' : 'fornecedores diferentes'}`)
  }
  if (e.notas != null) partes.push(`${e.notas} ${e.notas === 1 ? 'nota' : 'notas'}`)
  if (e.valor != null) {
    partes.push(e.concordancia != null && e.concordancia < 100
      ? `${e.concordancia}% delas com ${pct(e.valor)}`
      : `todas com ${pct(e.valor)}`)
  }
  return partes.length ? partes.join(', ') : null
}

const periodoEvidencia = (e) => (
  e?.inicio || e?.fim ? `notas emitidas de ${dataBr(e.inicio)} a ${dataBr(e.fim)}` : null
)

// O que a tela mostra depois de gravar as propostas. Cada linha explica em
// português por que aquele grupo NÃO virou proposta — o silêncio seria pior.
const RESUMO_APRENDIDA = [
  { keys: ['criadas', 'criados'], tone: 'ok', label: 'entraram na fila de revisão',
    dica: 'aguardando sua aprovação nesta mesma aba' },
  { keys: ['suprimidas', 'suprimidas_por_rejeicao'], tone: 'info', label: 'não voltaram',
    dica: 'você já tinha rejeitado essa mesma sugestão antes' },
  { keys: ['puladas_ja_na_matriz', 'puladas', 'puladas_linha_existente', 'ja_existentes'],
    tone: 'info', label: 'puladas',
    dica: 'já existe regra de MVA cadastrada para esse produto e par de estados' },
  { keys: ['ambiguas', 'descartadas', 'descartadas_ambiguidade'], tone: 'warn', label: 'descartadas',
    dica: 'os fornecedores declararam margens diferentes — sem convergência, o robô não chuta' },
]
const leResumo = (r, keys) => {
  for (const k of keys) if (r?.[k] != null) return Number(r[k])
  return null
}

// Campos em que a proposta difere do vigente (INSERIR: tudo que ela define).
function mudancasDe(p) {
  const de = p.linha_atual || {}
  const para = p.payload || {}
  return Object.keys(CAMPOS_DIFF)
    .filter(k => k in para && String(para[k] ?? '') !== String(de[k] ?? ''))
    .map(k => ({ campo: CAMPOS_DIFF[k], de: de[k], para: para[k] }))
}

// ── Cobertura: fila de curadoria dirigida pelos próprios XMLs ──
const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const STATUS_COBERTURA = {
  SEM_ENQUADRAMENTO: { label: 'Sem enquadramento', tone: 'err' },
  SEM_ALIQUOTA: { label: 'Sem alíquota na UF', tone: 'err' },
  ST_SEM_MVA: { label: 'ST sem MVA', tone: 'warn' },
  TN: { label: 'TN (fora do motor)', tone: 'info' },
  OK: { label: 'Auditável', tone: 'ok' },
}

function CoberturaPanel() {
  const { toasts, toast } = useToast()
  const [dados, setDados] = useState(null)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [filtroUf, setFiltroUf] = useState('')
  const [page, setPage] = useState(1)
  const [lacunas, setLacunas] = useState(null)
  const [baixando, setBaixando] = useState(false)
  const [carregandoBase, setCarregandoBase] = useState(false)

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try {
      setDados(await api.coberturaMatrizes({
        uf: filtroUf || undefined, page, page_size: PAGE_SIZE,
      }))
    }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [filtroUf, page])

  useEffect(() => { carregar() }, [carregar])

  // Resumo das lacunas de MVA — o número que diz quanto falta carregar antes
  // de o motor poder recusar cálculo sem margem cadastrada. Falha aqui não
  // derruba a Cobertura: é informação adicional, não a tela.
  useEffect(() => {
    let vivo = true
    api.lacunasMva({ uf: filtroUf || undefined, page_size: 1 })
      .then(r => { if (vivo) setLacunas(r?.resumo || null) })
      .catch(() => { if (vivo) setLacunas(null) })
    return () => { vivo = false }
  }, [filtroUf])

  async function baixarLacunas() {
    setBaixando(true)
    try {
      const { blob, filename } = await api.exportarLacunasMva({ uf: filtroUf || undefined })
      saveBlob(blob, filename)
      toast('Planilha baixada. Preencha a coluna da margem e suba em “Importar planilha”.', 'ok')
    }
    catch (e) { toast(e.message, 'error') }
    finally { setBaixando(false) }
  }

  async function carregarBaseMg() {
    setCarregandoBase(true)
    try {
      const r = await api.cargaInicialMatrizes()
      toast(r?.mensagem || 'Carga iniciada.', 'ok')
    }
    catch (e) { toast(e.message, 'error') }
    finally { setCarregandoBase(false) }
  }

  if (loading) return <div className="center-loader"><div className="spinner" /></div>
  if (erro) return <ErroCarga mensagem={erro} onRetry={carregar} />
  const resumo = dados?.resumo || {}
  const grupos = dados?.grupos || []
  const total = dados?.total ?? resumo.grupos ?? 0
  const totalPaginas = dados?.total_pages ?? Math.max(1, Math.ceil(total / PAGE_SIZE))
  const primeiro = total ? (page - 1) * PAGE_SIZE + 1 : 0
  const ultimo = Math.min(page * PAGE_SIZE, total)

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
        <SelectUf todas value={filtroUf} style={{ width: 210 }}
          onChange={v => { setFiltroUf(v); setPage(1) }} />
        <div style={{ display: 'flex', gap: 18, alignItems: 'baseline' }}>
          <span style={{ color: 'var(--text-3)', fontSize: 13 }}>
            {total.toLocaleString('pt-BR')} grupos · {brl(resumo.valor_total)}
          </span>
          <span style={{ fontWeight: 700, fontSize: 18, color: (resumo.pct_valor_coberto ?? 100) >= 90 ? 'var(--ok-text)' : 'var(--err-text)' }}>
            {resumo.pct_valor_coberto ?? 100}% do valor coberto
          </span>
        </div>
      </div>

      {lacunas?.lacunas > 0 && (
        <div className="card" style={{
          marginBottom: 14, padding: '14px 16px', display: 'flex', gap: 16,
          alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap',
          borderLeft: '3px solid var(--primary)',
        }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 13.5, marginBottom: 3 }}>
              Faltam <span className="tnum">{lacunas.lacunas.toLocaleString('pt-BR')}</span> margens
              de MVA para as notas já importadas
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55 }}>
              São <span className="tnum">{brl(lacunas.valor)}</span> em mercadoria sem margem
              cadastrada para o par de estados — sem ela, o ST sai calculado só sobre o valor
              da operação, abaixo do devido. Para MG, o robô preenche sozinho a partir do
              Anexo VII do RICMS. Nas demais UFs não há fonte automatizada: baixe a lista,
              que já vem no formato do “Importar planilha” e ordenada pelo que pesa mais.
            </div>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <button className="btn btn-primary" onClick={carregarBaseMg} disabled={carregandoBase}
              style={{ whiteSpace: 'nowrap' }}>
              <i className={`ti ${carregandoBase ? 'ti-loader-2' : 'ti-download'}`} />
              {carregandoBase ? 'Iniciando…' : 'Carregar base de MG (Anexo VII)'}
            </button>
            <button className="btn" onClick={baixarLacunas} disabled={baixando}
              style={{ whiteSpace: 'nowrap' }}>
              <i className={`ti ${baixando ? 'ti-loader-2' : 'ti-file-download'}`} />
              {baixando ? 'Gerando…' : 'Baixar lacunas'}
            </button>
          </div>
        </div>
      )}

      {grupos.length === 0 ? (
        <div className="empty-state">
          <i className="ti ti-radar-2" />
          <p className="empty-title">Nada a analisar</p>
          <p className="empty-subtitle">Importe XMLs para medir a cobertura das matrizes sobre a carteira real.</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>UF</th><th>NCM</th><th>CEST</th>
                  <th style={{ textAlign: 'right' }}>Itens</th>
                  <th style={{ textAlign: 'right' }}>Valor movimentado</th>
                  <th>Situação</th><th>Regime</th><th>Última emissão</th>
                </tr>
              </thead>
              <tbody>
                {grupos.map((g, i) => {
                  const st = STATUS_COBERTURA[g.status] || { label: g.status, tone: 'info' }
                  return (
                    <tr key={`${g.uf}-${g.ncm}-${g.cest}-${i}`}>
                      <td>{badge(g.uf)}</td>
                      <td className="mono">{g.ncm}</td>
                      <td className="mono">{g.cest || '—'}</td>
                      <td style={{ textAlign: 'right' }}>{g.itens}</td>
                      <td style={{ textAlign: 'right', fontWeight: 600 }}>{brl(g.valor)}</td>
                      <td>{badge(st.label, st.tone)}</td>
                      <td style={{ color: 'var(--text-3)' }}>{g.regime || '—'}</td>
                      <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{dataBr(g.data_ref)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {totalPaginas > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, padding: 12, borderTop: '1px solid var(--border-2)', flexWrap: 'wrap' }}>
              <span style={{ color: 'var(--text-3)', fontSize: 12.5 }}>
                Mostrando {primeiro.toLocaleString('pt-BR')}–{ultimo.toLocaleString('pt-BR')} de {total.toLocaleString('pt-BR')} grupos
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)} title="Página anterior">
                  <i className="ti ti-chevron-left" />
                </button>
                {paginasVisiveis(page, totalPaginas).map((n, i) => n === '…'
                  ? <span key={`e${i}`} style={{ padding: '0 6px', color: 'var(--text-4)' }}>…</span>
                  : (
                    <button key={n} onClick={() => setPage(n)} className="btn btn-sm"
                      style={{
                        minWidth: 32, justifyContent: 'center', border: 'none',
                        background: n === page ? 'var(--primary)' : 'transparent',
                        color: n === page ? 'var(--primary-contrast)' : 'var(--text-2)', fontWeight: n === page ? 700 : 500,
                      }}>{n}</button>
                  ))}
                <button className="btn btn-ghost btn-sm" disabled={page === totalPaginas} onClick={() => setPage(p => p + 1)} title="Próxima página">
                  <i className="ti ti-chevron-right" />
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// Bloco de evidência: o que sustenta o número sugerido. É ele que transforma
// "aprovar um percentual" em "aprovar um percentual que 3 fornecedores
// independentes vêm declarando há meses".
function BlocoEvidencia({ evidencia, compacto = false }) {
  const e = lerEvidencia(evidencia)
  if (!e) return null
  const frase = fraseEvidencia(e)
  const periodo = periodoEvidencia(e)
  if (compacto) {
    return (
      <div style={{ fontSize: 11.5, color: 'var(--text-4)', marginTop: 3 }}>
        <i className="ti ti-bulb" style={{ marginRight: 4 }} />{frase || 'sem detalhe da apuração'}
      </div>
    )
  }
  return (
    <div style={{
      marginTop: 14, padding: '12px 14px', background: 'var(--surface-2)',
      borderRadius: 'var(--radius)',
    }}>
      <div style={{ fontSize: 11, textTransform: 'uppercase', letterSpacing: '0.5px', fontWeight: 700, color: 'var(--text-4)' }}>
        De onde saiu este número
      </div>
      <div style={{ fontSize: 13.5, fontWeight: 600, marginTop: 6 }}>{frase || 'Apuração sem detalhe informado.'}</div>
      {periodo && <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3 }}>{periodo}</div>}
      {e.distribuicao.length > 1 && (
        <div className="tbl-wrap" style={{ marginTop: 10 }}>
          <table className="tbl">
            <thead>
              <tr>
                <th>Margem declarada</th>
                <th style={{ textAlign: 'right' }}>Notas</th>
                <th style={{ textAlign: 'right' }}>Fornecedores</th>
              </tr>
            </thead>
            <tbody>
              {e.distribuicao.map((d, i) => (
                <tr key={`${d.valor}-${i}`}>
                  <td className="tnum" style={{ fontWeight: String(d.valor) === String(e.valor) ? 700 : 400 }}>
                    {pct(d.valor)}
                  </td>
                  <td className="tnum" style={{ textAlign: 'right' }}>{d.notas ?? '—'}</td>
                  <td className="tnum" style={{ textAlign: 'right' }}>{d.fornecedores ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// Aviso fixo de toda proposta aprendida: ela NÃO tem base legal.
function AvisoSemBaseLegal({ children }) {
  return (
    <div style={{
      border: '1px solid var(--warn-text)', borderRadius: 'var(--radius)',
      background: 'var(--warn-bg)', color: 'var(--warn-text)',
      padding: '11px 14px', fontSize: 12.5, lineHeight: 1.6,
    }}>
      <strong><i className="ti ti-alert-triangle" style={{ marginRight: 5 }} />
      Esta sugestão não tem base legal.</strong>{' '}
      Ela não veio de norma publicada: é a margem que os próprios fornecedores
      vêm declarando nas notas do escritório. Isso é um bom ponto de partida —
      não é prova de que a lei do estado diz isso. Quem confirma a norma é você.
      {children}
    </div>
  )
}

const previaChave = (it) => {
  const p = it?.payload || it || {}
  return it?.chave_resumo || [
    p.uf_destino, p.uf_origem && p.uf_origem !== UF_QUALQUER ? `de ${p.uf_origem}` : null,
    p.ncm && `NCM ${p.ncm}`, p.cest && `CEST ${p.cest}`,
  ].filter(Boolean).join(' · ')
}
const previaMva = (it) => (it?.payload?.mva_original ?? it?.mva_original ?? null)
const previaValor = (it) => (it?.valor ?? it?.valor_mercadoria ?? it?.impacto ?? null)

// Gatilho do aprendizado. O fluxo é PRÉVIA → confirmação → resumo, nunca
// "aperta e grava": o GET não escreve nada, então o curador vê o volume e a
// qualidade das evidências ANTES de encher a fila de revisão. É a mesma regra
// do resto do módulo — nada entra sem alguém olhar.
function AprenderMvaModal({ onFechar, onCriou }) {
  const [previa, setPrevia] = useState(null)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [gerando, setGerando] = useState(false)
  const [erroGerar, setErroGerar] = useState(null)
  const [resumo, setResumo] = useState(null)

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try { setPrevia(await api.previaMvaAprendida({ page, page_size: 15 })) }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [page])
  useEffect(() => { carregar() }, [carregar])

  const itens = previa?.items || []
  const total = previa?.total ?? itens.length
  const totalPaginas = previa?.total_pages ?? Math.max(1, Math.ceil(total / 15))

  async function gerar() {
    setGerando(true)
    setErroGerar(null)
    // Falha do POST NÃO derruba a prévia: o curador continua vendo o que ia ser
    // proposto e pode tentar de novo.
    try { setResumo(await api.gerarMvaAprendida({})); onCriou?.() }
    catch (e) { setErroGerar(e.message) }
    finally { setGerando(false) }
  }

  return (
    <div className="modal-overlay" onClick={onFechar}>
      <div className="modal" style={{ maxWidth: 860 }} onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Aprender a MVA com as notas já importadas</h2>
          <button className="btn btn-icon" onClick={onFechar}><i className="ti ti-x" /></button>
        </div>
        <div className="modal-body">
          {resumo ? (
            <>
              <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6, marginTop: 0 }}>
                Pronto. Veja o que aconteceu com cada grupo — o que não virou
                proposta tem motivo, e o motivo está aqui:
              </p>
              <div className="tbl-wrap">
                <table className="tbl">
                  <tbody>
                    {RESUMO_APRENDIDA.map(l => {
                      const n = leResumo(resumo, l.keys)
                      if (n == null) return null
                      return (
                        <tr key={l.keys[0]}>
                          <td className="tnum" style={{ fontWeight: 700, fontSize: 18, width: 90 }}>
                            {n.toLocaleString('pt-BR')}
                          </td>
                          <td>
                            {badge(l.label, l.tone)}
                            <div style={{ fontSize: 12, color: 'var(--text-3)', marginTop: 3 }}>{l.dica}</div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              {resumo.mensagem && (
                <p style={{ fontSize: 12.5, color: 'var(--text-3)', marginTop: 12 }}>{resumo.mensagem}</p>
              )}
            </>
          ) : loading ? (
            <div className="center-loader"><div className="spinner" /></div>
          ) : erro ? (
            <ErroCarga mensagem={erro} onRetry={carregar} />
          ) : (
            <>
              <p style={{ fontSize: 13, color: 'var(--text-2)', lineHeight: 1.6, marginTop: 0 }}>
                Só Minas Gerais publica a margem em fonte oficial. Nos outros
                estados, esta é a saída para não digitar tudo à mão: o sistema lê
                a margem que os fornecedores já informam nas notas e, quando
                vários deles — sem combinar entre si — chegam ao mesmo número,
                traz a sugestão para cá.
              </p>
              <AvisoSemBaseLegal>
                {' '}Por isso nada é gravado na matriz agora: o que este botão faz
                é colocar as sugestões na fila de revisão, uma a uma, para você
                aprovar ou descartar.
              </AvisoSemBaseLegal>
              <p style={{ fontSize: 13, marginTop: 14, marginBottom: 8 }}>
                <strong className="tnum">{Number(total).toLocaleString('pt-BR')}</strong>
                {total === 1 ? ' sugestão encontrada' : ' sugestões encontradas'}
                {total > 0 ? ' — da que mais movimenta dinheiro para a que menos movimenta:' : '.'}
              </p>
              {total === 0 ? (
                <div className="empty-state">
                  <i className="ti ti-bulb-off" />
                  <p className="empty-title">Nada a aprender por enquanto</p>
                  <p className="empty-subtitle">
                    Não houve convergência suficiente entre fornecedores nas notas já
                    importadas. Importe mais notas e tente de novo.
                  </p>
                </div>
              ) : (
                <div className="tbl-wrap">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Produto e estados</th>
                        <th style={{ textAlign: 'right' }}>Margem sugerida</th>
                        <th>Em que isso se apoia</th>
                        <th style={{ textAlign: 'right' }}>Movimento</th>
                      </tr>
                    </thead>
                    <tbody>
                      {itens.map((it, i) => (
                        <tr key={`${previaChave(it)}-${i}`}>
                          <td className="mono" style={{ fontSize: 12.5 }}>{previaChave(it)}</td>
                          <td className="tnum" style={{ textAlign: 'right', fontWeight: 700 }}>{pct(previaMva(it))}</td>
                          <td style={{ fontSize: 12, color: 'var(--text-3)' }}>
                            {fraseEvidencia(lerEvidencia(it.evidencia)) || '—'}
                          </td>
                          <td className="tnum" style={{ textAlign: 'right' }}>
                            {previaValor(it) == null ? '—' : brl(previaValor(it))}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {totalPaginas > 1 && (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, marginTop: 10 }}>
                  <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                    <i className="ti ti-chevron-left" />
                  </button>
                  <span className="tnum" style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
                    página {page} de {totalPaginas}
                  </span>
                  <button className="btn btn-ghost btn-sm" disabled={page === totalPaginas} onClick={() => setPage(p => p + 1)}>
                    <i className="ti ti-chevron-right" />
                  </button>
                </div>
              )}
            </>
          )}
        </div>
        <div className="modal-footer">
          {erroGerar && (
            <span style={{ marginRight: 'auto', fontSize: 12.5, color: 'var(--err-text)' }}>
              <i className="ti ti-alert-circle" style={{ marginRight: 5 }} />{erroGerar}
            </span>
          )}
          <button type="button" className="btn btn-ghost" onClick={onFechar}>
            {resumo ? 'Ver a fila' : 'Cancelar'}
          </button>
          {!resumo && !erro && !loading && total > 0 && (
            <button type="button" className="btn btn-primary" disabled={gerando} onClick={gerar}>
              <i className={`ti ${gerando ? 'ti-loader-2' : 'ti-inbox'}`} />
              {gerando ? 'Enviando…' : `Enviar as ${Number(total).toLocaleString('pt-BR')} para a fila`}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

function RevisaoPanel({ onMudou }) {
  const { toasts, toast } = useToast()
  const [dados, setDados] = useState({ items: [], total: 0 })
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [status, setStatus] = useState('PENDENTE')
  const [tipo, setTipo] = useState('')
  const [uf, setUf] = useState('')
  const [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false)
  const [detalhe, setDetalhe] = useState(null)
  const [aprender, setAprender] = useState(false)
  // Trava da proposta aprendida: sem norma por trás, aprovar só depois de o
  // curador dizer, com todas as letras, que conferiu a lei do estado.
  const [confirmouNorma, setConfirmouNorma] = useState(false)
  useEffect(() => { setConfirmouNorma(false) }, [detalhe])

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try {
      setDados(await api.propostasMatrizes({
        status, tipo: tipo || undefined, uf: uf || undefined, page, page_size: PAGE_SIZE,
      }))
    } catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [status, tipo, uf, page])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setPage(1) }, [status, tipo, uf])
  const total = dados.total || 0
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))

  async function agir(fn, msg) {
    setBusy(true)
    try { await fn(); toast(msg, 'ok'); setDetalhe(null); await carregar(); onMudou?.() }
    catch (e) { toast(e.message, 'error') }
    finally { setBusy(false) }
  }
  const aprovar = (p) => agir(() => api.aprovarProposta(p.id), 'Proposta aprovada e aplicada na matriz.')
  const rejeitar = (p) => {
    const motivo = window.prompt('Motivo da rejeição (opcional — a proposta não voltará à fila):')
    if (motivo === null) return
    agir(() => api.rejeitarProposta(p.id, motivo), 'Proposta rejeitada — não voltará à fila.')
  }
  // O lote não sabe separar aprendidas de oficiais (o servidor filtra por
  // matriz/UF). Se houver aprendida à vista, o aviso é explícito: aprovar tudo
  // leva junto sugestão sem norma.
  const temAprendidaNaTela = dados.items.some(ehAprendida)
  const aprovarTudo = () => {
    const alerta = temAprendidaNaTela
      ? '\n\nATENÇÃO: há sugestões aprendidas das notas neste filtro. Elas não têm '
        + 'base legal e o lote não sabe separá-las. Se quiser conferir a norma uma a '
        + 'uma, cancele e aprove pela lista.'
      : ''
    if (!confirm(`Aprovar as ${total.toLocaleString('pt-BR')} propostas do filtro atual?${alerta}`)) return
    agir(async () => {
      const r = await api.aprovarPropostasLote({ tipo_matriz: tipo || null, uf: uf || null })
      if (r.falhas?.length) {
        toast(`${r.falhas.length} não puderam ser aplicadas (conflito de vigência) — seguem na fila.`, 'error')
      }
    }, 'Lote revisado.')
  }

  if (loading) return <div className="center-loader"><div className="spinner" /></div>
  if (erro) return <ErroCarga mensagem={erro} onRetry={carregar} />

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14, flexWrap: 'wrap' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <div style={{ width: 170 }}>
            <Dropdown value={status} onChange={setStatus} options={[
              { value: 'PENDENTE', label: 'Pendentes' },
              { value: 'APROVADA', label: 'Aprovadas' },
              { value: 'REJEITADA', label: 'Rejeitadas' },
            ]} />
          </div>
          <div style={{ width: 190 }}>
            <Dropdown value={tipo} onChange={setTipo} options={[
              { value: '', label: 'Todas as matrizes' },
              ...Object.entries(TIPOS_PROPOSTA).map(([value, label]) => ({ value, label })),
            ]} />
          </div>
          <SelectUf todas value={uf} onChange={setUf} style={{ width: 200 }} />
          {total > 0 && (
            <span className="tnum" style={{ color: 'var(--text-3)', fontSize: 13 }}>
              {total.toLocaleString('pt-BR')} {total === 1 ? 'proposta' : 'propostas'}
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-secondary" disabled={busy} onClick={() => setAprender(true)}
            title="Procura, nas notas já importadas, margens em que vários fornecedores convergem">
            <i className="ti ti-bulb" /> Aprender MVA das notas
          </button>
          {status === 'PENDENTE' && total > 0 && (
            <button className="btn btn-primary" disabled={busy} onClick={aprovarTudo}>
              <i className="ti ti-checks" /> Aprovar tudo (filtro atual)
            </button>
          )}
        </div>
      </div>

      {dados.items.length === 0 ? (
        <div className="empty-state">
          <i className="ti ti-inbox" />
          <p className="empty-title">{status === 'PENDENTE' ? 'Fila limpa' : 'Nada por aqui'}</p>
          <p className="empty-subtitle">
            {status === 'PENDENTE'
              ? 'Nenhuma proposta dos robôs aguardando revisão. Quando uma fonte oficial mudar, ela aparece aqui.'
              : 'Nenhuma proposta com esse status no filtro atual.'}
          </p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Ação</th><th>Matriz</th><th>Chave</th><th>Mudança</th>
                  <th>Fonte</th><th>Criada</th><th></th>
                </tr>
              </thead>
              <tbody>
                {dados.items.map(p => {
                  const acao = ACOES_PROPOSTA[p.acao] || { label: p.acao, tone: 'info' }
                  const muda = mudancasDe(p)
                  const aprendida = ehAprendida(p)
                  return (
                    <tr key={p.id} style={{ cursor: 'pointer' }} onClick={() => setDetalhe(p)}>
                      <td>{badge(acao.label, acao.tone)}</td>
                      <td>{badge(TIPOS_PROPOSTA[p.tipo_matriz] || p.tipo_matriz)}</td>
                      <td className="mono" style={{ fontSize: 13 }}>{p.chave_resumo}</td>
                      <td style={{ color: 'var(--text-2)', fontSize: 13 }}>
                        {p.acao === 'REVALIDAR'
                          ? 'Confirme que os valores continuam valendo'
                          : (<>{muda.slice(0, 2).map(m => `${m.campo}: ${fmtDiff(m.de)} → ${fmtDiff(m.para)}`).join(' · ')}
                            {muda.length > 2 ? ` · +${muda.length - 2}` : ''}</>)}
                        {aprendida && <BlocoEvidencia evidencia={p.evidencia} compacto />}
                      </td>
                      <td style={{ color: 'var(--text-3)', fontSize: 12 }}>
                        {aprendida ? badge('Aprendida das notas · sem base legal', 'warn') : p.fonte}
                        {aprendida && (
                          <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 3 }}>{p.fonte}</div>
                        )}
                      </td>
                      <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{dataCadastro(p)}</td>
                      <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                        {p.status === 'PENDENTE' ? (
                          <>
                            <button className="btn btn-icon" disabled={busy}
                              title={aprendida
                                ? 'Conferir antes de aprovar — sugestão sem base legal'
                                : 'Aprovar'}
                              onClick={ev => { ev.stopPropagation(); if (aprendida) setDetalhe(p); else aprovar(p) }}>
                              <i className={`ti ${aprendida ? 'ti-eye-check' : 'ti-check'}`}
                                style={{ color: aprendida ? 'var(--warn-text)' : 'var(--ok-text)' }} />
                            </button>
                            <button className="btn btn-icon" title="Rejeitar" disabled={busy}
                              onClick={ev => { ev.stopPropagation(); rejeitar(p) }}>
                              <i className="ti ti-x" style={{ color: 'var(--err-text)' }} />
                            </button>
                          </>
                        ) : (
                          <span style={{ color: 'var(--text-3)', fontSize: 12 }}>{p.revisado_por || '—'}</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {totalPaginas > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: 12, borderTop: '1px solid var(--border-2)' }}>
              <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <i className="ti ti-chevron-left" />
              </button>
              {paginasVisiveis(page, totalPaginas).map((n, i) => n === '…'
                ? <span key={`e${i}`} style={{ padding: '0 6px', color: 'var(--text-4)' }}>…</span>
                : (
                  <button key={n} onClick={() => setPage(n)} className="btn btn-sm"
                    style={{
                      minWidth: 32, justifyContent: 'center', border: 'none',
                      background: n === page ? 'var(--primary)' : 'transparent',
                      color: n === page ? 'var(--primary-contrast)' : 'var(--text-2)', fontWeight: n === page ? 700 : 500,
                    }}>{n}</button>
                ))}
              <button className="btn btn-ghost btn-sm" disabled={page === totalPaginas} onClick={() => setPage(p => p + 1)}>
                <i className="ti ti-chevron-right" />
              </button>
            </div>
          )}
        </div>
      )}

      {detalhe && (
        <div className="modal-overlay" onClick={() => setDetalhe(null)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{(ACOES_PROPOSTA[detalhe.acao] || {}).label || detalhe.acao} · {TIPOS_PROPOSTA[detalhe.tipo_matriz] || detalhe.tipo_matriz}</h2>
              <button className="btn btn-icon" onClick={() => setDetalhe(null)}><i className="ti ti-x" /></button>
            </div>
            <div className="modal-body">
              <p className="mono" style={{ marginBottom: 4 }}>{detalhe.chave_resumo}</p>
              <p style={{ color: 'var(--text-3)', fontSize: 13, marginBottom: 14 }}>
                Fonte: {detalhe.fonte} · proposta em {dataCadastro(detalhe)}
                {detalhe.status !== 'PENDENTE' && (
                  <> · {detalhe.status === 'APROVADA' ? 'aprovada' : 'rejeitada'} por {detalhe.revisado_por || '—'}
                    {detalhe.motivo_rejeicao ? ` — “${detalhe.motivo_rejeicao}”` : ''}</>
                )}
              </p>
              {ehAprendida(detalhe) && (
                <div style={{ marginBottom: 14 }}>
                  <AvisoSemBaseLegal>
                    {' '}Compare com a norma do estado de destino antes de aprovar. Depois
                    de aprovada, abra a linha na aba MVA e preencha a Base legal — ela
                    entra em branco, e é ela que a carta de ST cita.
                  </AvisoSemBaseLegal>
                </div>
              )}
              <div className="tbl-wrap">
                {detalhe.acao === 'REVALIDAR' ? (
                  <table className="tbl">
                    <thead><tr><th>Campo</th><th>Valor vigente</th></tr></thead>
                    <tbody>
                      {Object.keys(CAMPOS_DIFF).filter(k => k in (detalhe.payload || {})).map(k => (
                        <tr key={k}>
                          <td style={{ color: 'var(--text-3)' }}>{CAMPOS_DIFF[k]}</td>
                          <td style={{ fontWeight: 600 }}>{fmtDiff(detalhe.payload[k])}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <table className="tbl">
                    <thead><tr><th>Campo</th><th>Vigente</th><th>Proposto</th></tr></thead>
                    <tbody>
                      {mudancasDe(detalhe).map(m => (
                        <tr key={m.campo}>
                          <td style={{ color: 'var(--text-3)' }}>{m.campo}</td>
                          <td>{fmtDiff(m.de)}</td>
                          <td style={{ fontWeight: 600 }}>{fmtDiff(m.para)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
              {detalhe.acao === 'REVALIDAR' && (
                <p style={{ fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.55, marginTop: 12, marginBottom: 0 }}>
                  Confirmar renova a data de verificação sem mudar nada. Se a legislação
                  mudou, rejeite e ajuste pelo cadastro — encerrando a vigência antiga e
                  criando uma nova.
                </p>
              )}
              {ehAprendida(detalhe) && (
                <>
                  <BlocoEvidencia evidencia={detalhe.evidencia} />
                  {detalhe.status === 'PENDENTE' && (
                    <label style={{
                      display: 'flex', alignItems: 'flex-start', gap: 10, marginTop: 14,
                      fontSize: 12.5, lineHeight: 1.55, cursor: 'pointer',
                    }}>
                      <input type="checkbox" checked={confirmouNorma} style={{ width: 18, height: 18, marginTop: 1 }}
                        onChange={e => setConfirmouNorma(e.target.checked)} />
                      <span>
                        Conferi a norma do estado de destino e confirmo que esta é a
                        margem que vale hoje para este produto.
                      </span>
                    </label>
                  )}
                </>
              )}
            </div>
            {detalhe.status === 'PENDENTE' && (
              <div className="modal-footer">
                <button className="btn btn-ghost" disabled={busy} onClick={() => rejeitar(detalhe)}>Rejeitar</button>
                <button className="btn btn-primary" onClick={() => aprovar(detalhe)}
                  disabled={busy || (ehAprendida(detalhe) && !confirmouNorma)}
                  title={ehAprendida(detalhe) && !confirmouNorma
                    ? 'Marque a confirmação acima: esta sugestão não tem base legal'
                    : undefined}>
                  {detalhe.acao === 'REVALIDAR' ? 'Confirmar — continua valendo' : 'Aprovar e aplicar'}
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {aprender && (
        <AprenderMvaModal
          onFechar={() => setAprender(false)}
          onCriou={() => { carregar(); onMudou?.() }} />
      )}
    </div>
  )
}

// Formulário em branco: `padrao` deixa um campo já preenchido (a UF de origem
// da MVA nasce em "*", que é a regra geral).
function vazioDe(campos) {
  return Object.fromEntries(campos.map(c => [
    c.key,
    c.padrao !== undefined ? c.padrao : (c.type === 'select' ? (c.options[0]?.value || '') : ''),
  ]))
}

// "GERAL" é palavra mágica: em vez de exigir que o curador a digite (e descubra
// sozinho que ela existe), a tela oferece a escolha e só mostra a caixa do NCM
// quando ela faz sentido. O valor gravado continua sendo "GERAL" ou o NCM.
function CampoNcmGeral({ campo, value, onChange }) {
  const [especifico, setEspecifico] = useState(() => !ehGeral(value))

  const opcao = (ativo, rotulo, ao) => (
    <button type="button" onClick={ao} className="btn btn-sm"
      style={{
        border: 'none', flex: 1, justifyContent: 'center',
        background: ativo ? 'var(--surface)' : 'transparent',
        color: ativo ? 'var(--text-1)' : 'var(--text-3)',
        boxShadow: ativo ? 'var(--shadow-sm)' : 'none',
        fontWeight: ativo ? 600 : 500,
      }}>{rotulo}</button>
  )

  return (
    <div>
      <div style={{ display: 'flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, gap: 3 }}>
        {opcao(!especifico, 'Todo o estado', () => { setEspecifico(false); onChange(NCM_GERAL) })}
        {opcao(especifico, 'Um produto (NCM)', () => { setEspecifico(true); onChange(ehGeral(value) ? '' : value) })}
      </div>
      {especifico && (
        <input value={ehGeral(value) ? '' : (value || '')} maxLength={8} required={campo.required}
          placeholder="30049099" style={{ marginTop: 8 }}
          onChange={e => onChange(e.target.value.replace(/\D/g, ''))} />
      )}
    </div>
  )
}

function CampoInput({ campo, value, onChange, bloqueado }) {
  // UF vira lista fechada em TODAS as abas por este único caminho — nada de
  // texto livre virando "Minas Gerais"/"mg" dentro da matriz.
  if (campo.uf)
    return <SelectUf value={value} onChange={onChange} required={campo.required} coringa={campo.coringa} />
  if (campo.type === 'ncm-geral')
    return <CampoNcmGeral campo={campo} value={value} onChange={onChange} />
  if (campo.type === 'select')
    return <Dropdown value={value} onChange={onChange} options={campo.options} placeholder="Selecione…" />
  if (campo.type === 'date')
    return <input type="date" value={value || ''} onChange={e => onChange(e.target.value)} required={campo.required} />
  if (campo.type === 'number')
    return <input type="number" step="0.01" min="0" value={bloqueado ? '' : value} disabled={bloqueado}
      onChange={e => onChange(e.target.value)} placeholder={bloqueado ? '—' : campo.placeholder}
      required={campo.required && !bloqueado} />
  return (
    <input value={value} placeholder={campo.placeholder} required={campo.required}
      onChange={e => onChange(e.target.value)} />
  )
}

// As matrizes não têm busca por id — a linha a corrigir é procurada nas
// primeiras páginas da própria listagem. O teto é baixo de propósito: a base de
// MVA tem dezenas de milhares de linhas e varrer tudo atrás de um id seria pior
// para o usuário do que avisar que ele precisa filtrar.
const PAGINAS_BUSCA_FOCO = 10
async function procurarLinha(aba, id) {
  for (let p = 1; p <= PAGINAS_BUSCA_FOCO; p++) {
    let r
    try { r = await aba.api.list({ page: p, page_size: PAGE_SIZE }) }
    catch { return null }
    const itens = r?.items || (Array.isArray(r) ? r : [])
    const achada = itens.find(m => String(m.id) === String(id))
    if (achada) return achada
    const paginas = r?.total_pages ?? Math.ceil((r?.total || 0) / PAGE_SIZE)
    if (!itens.length || p >= paginas) return null
  }
  return null
}

function CrudMatriz({ aba, prefill, foco }) {
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  // Filtros combináveis (UF + NCM + CEST). `filtros` acompanha a digitação;
  // `filtrosAtivos` é o que consulta o servidor, após a pausa na digitação.
  const [filtros, setFiltros] = useState({ uf: '', ncm: '', cest: '' })
  const [filtrosAtivos, setFiltrosAtivos] = useState({ uf: '', ncm: '', cest: '' })
  const [modal, setModal] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(() => vazioDe(aba.campos))
  const [saving, setSaving] = useState(false)

  // Deep-link das Divergências: abre o cadastro já preenchido (só campos da aba).
  useEffect(() => {
    if (!prefill) return
    const chaves = new Set(aba.campos.map(c => c.key))
    const valido = Object.fromEntries(
      Object.entries(prefill).filter(([k]) => chaves.has(k))
    )
    setEditId(null)
    setForm({ ...vazioDe(aba.campos), ...valido })
    setModal(true)
  }, [prefill, aba])

  // Correção de estado fora do padrão (aba Saúde): abre a linha existente com
  // a sigla sugerida já escolhida no seletor. NADA é gravado aqui — o curador
  // confere o resto do cadastro e salva, que é o único jeito de mudar dado
  // fiscal nesta tela.
  const [avisoFoco, setAvisoFoco] = useState(null)
  useEffect(() => {
    if (!foco) { setAvisoFoco(null); return undefined }
    let vivo = true
    setAvisoFoco({ etapa: 'procurando', foco })
    procurarLinha(aba, foco.id).then(linha => {
      if (!vivo) return
      if (!linha) { setAvisoFoco({ etapa: 'nao-achou', foco }); return }
      const preenchidos = Object.fromEntries(
        Object.entries(linha).filter(([, v]) => v !== null && v !== undefined)
      )
      setEditId(linha.id)
      setForm({
        ...vazioDe(aba.campos), ...preenchidos,
        data_fim_vigencia: linha.data_fim_vigencia || '',
        // Sem sugestão o campo abre em branco (o valor torto não casa com
        // nenhuma opção da lista) e o seletor exige a escolha.
        [foco.campo]: foco.sugestao || '',
      })
      setModal(true)
      setAvisoFoco({ etapa: 'achou', foco })
    })
    return () => { vivo = false }
  }, [foco, aba])

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try {
      const r = await aba.api.list({
        uf: filtrosAtivos.uf || undefined,
        ncm: filtrosAtivos.ncm || undefined,
        cest: filtrosAtivos.cest || undefined,
        page, page_size: PAGE_SIZE,
      })
      setLista(r?.items || (Array.isArray(r) ? r : []))
      setTotal(r?.total ?? 0)
    }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [aba, filtrosAtivos, page])

  useEffect(() => { carregar() }, [carregar])
  // Espera a digitação parar antes de consultar; referência estável quando
  // nada mudou evita busca duplicada na montagem.
  useEffect(() => {
    const t = setTimeout(() => setFiltrosAtivos(prev => (
      prev.uf === filtros.uf && prev.ncm === filtros.ncm && prev.cest === filtros.cest
        ? prev : filtros
    )), 300)
    return () => clearTimeout(t)
  }, [filtros])
  useEffect(() => { setPage(1) }, [filtrosAtivos])
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const setFiltro = (k, limpar) => (e) => {
    const v = limpar ? e.target.value.replace(/\D/g, '') : e.target.value.toUpperCase()
    setFiltros(f => ({ ...f, [k]: v }))
  }
  const temNcm = aba.colunas.some(c => c.key === 'ncm')
  const temCest = aba.colunas.some(c => c.key === 'cest')

  function abrirNova() { setEditId(null); setForm(vazioDe(aba.campos)); setModal(true) }
  function abrirEdicao(m) {
    // Campo nulo vindo do servidor (linha de MVA antiga, sem uf_origem) não
    // pode apagar o padrão — senão a regra geral abre como campo em branco.
    const preenchidos = Object.fromEntries(
      Object.entries(m).filter(([, v]) => v !== null && v !== undefined)
    )
    setEditId(m.id)
    setForm({ ...vazioDe(aba.campos), ...preenchidos, data_fim_vigencia: m.data_fim_vigencia || '' })
    setModal(true)
  }

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form, data_fim_vigencia: form.data_fim_vigencia || null }
      // Campo desligado (redução de base numa linha GERAL) e numérico opcional
      // em branco saem do corpo — o servidor aplica o padrão dele (0) em vez de
      // receber "" ou um valor herdado que aquela linha não aceita.
      for (const c of aba.campos) {
        const vazio = payload[c.key] === '' || payload[c.key] == null
        if ((c.bloqueio && c.bloqueio(form)) || (c.omitirSeVazio && vazio)) delete payload[c.key]
      }
      if (editId) { await aba.api.update(editId, payload); toast('Regra atualizada.', 'ok') }
      else { await aba.api.create(payload); toast('Regra cadastrada.', 'ok') }
      setModal(false); setEditId(null); await carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  async function remover(m) {
    if (!confirm('Remover esta regra da matriz?')) return
    try { await aba.api.remove(m.id); toast('Regra removida.', 'ok'); await carregar() }
    catch (e) { toast(e.message, 'error') }
  }

  // Mudar um campo pode desligar outro (voltar o NCM para GERAL desliga a
  // redução de base). O valor que deixou de valer é limpo na hora — nada de
  // enviar em silêncio um número que aquela linha não aceita.
  const setCampo = (k) => (v) => setForm(f => {
    const prox = { ...f, [k]: v }
    for (const c of aba.campos) {
      if (c.bloqueio && c.bloqueio(prox) && prox[c.key] !== '') prox[c.key] = ''
    }
    return prox
  })

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <SelectUf todas value={filtros.uf} style={{ width: 200 }}
            onChange={v => setFiltros(f => ({ ...f, uf: v }))} />
          {temNcm && (
            <input value={filtros.ncm} onChange={setFiltro('ncm', true)} maxLength={8}
              placeholder="NCM (prefixo)…" style={{ width: 150 }} />
          )}
          {temCest && (
            <input value={filtros.cest} onChange={setFiltro('cest', true)} maxLength={7}
              placeholder="CEST (prefixo)…" style={{ width: 150 }} />
          )}
          {total > 0 && (
            <span className="tnum" style={{ color: 'var(--text-3)', fontSize: 13 }}>
              {total.toLocaleString('pt-BR')} {total === 1 ? 'regra' : 'regras'}
            </span>
          )}
        </div>
        <button className="btn btn-primary" onClick={abrirNova}><i className="ti ti-plus" /> Nova regra</button>
      </div>

      {avisoFoco && (
        <div className="card" style={{
          marginBottom: 14, padding: '12px 16px', borderLeft: '3px solid var(--primary)',
          display: 'flex', gap: 14, alignItems: 'flex-start', justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: 12.5, lineHeight: 1.6 }}>
            {avisoFoco.etapa === 'procurando' && (
              <>Procurando a regra nº <span className="tnum">{avisoFoco.foco.id}</span> nesta matriz…</>
            )}
            {avisoFoco.etapa === 'achou' && (
              <>
                <strong>Regra nº <span className="tnum">{avisoFoco.foco.id}</span> aberta para correção.</strong>
                {' '}O campo <strong>{ROTULO_CAMPO_UF[avisoFoco.foco.campo] || avisoFoco.foco.campo}</strong>
                {' '}estava gravado como <span className="mono">{comoEstaGravado(avisoFoco.foco.valor)}</span>,
                que o motor não reconhece.
                {avisoFoco.foco.sugestao
                  ? <> Já deixamos <strong>{avisoFoco.foco.sugestao}</strong> escolhido: confira o
                    restante do cadastro e salve para valer.</>
                  : <> Não dá para deduzir o estado certo — escolha no seletor e salve.</>}
              </>
            )}
            {avisoFoco.etapa === 'nao-achou' && (
              <>
                A regra nº <span className="tnum">{avisoFoco.foco.id}</span> não está entre as
                primeiras <span className="tnum">{(PAGINAS_BUSCA_FOCO * PAGE_SIZE).toLocaleString('pt-BR')}</span>
                {' '}linhas desta matriz. Use os filtros de NCM/CEST acima para chegar até ela — o
                campo <strong>{ROTULO_CAMPO_UF[avisoFoco.foco.campo] || avisoFoco.foco.campo}</strong>
                {' '}está gravado como <span className="mono">{comoEstaGravado(avisoFoco.foco.valor)}</span>
                {avisoFoco.foco.sugestao ? <> e deveria ser <strong>{avisoFoco.foco.sugestao}</strong>.</> : '.'}
              </>
            )}
          </div>
          <button className="btn btn-icon" title="Dispensar aviso" onClick={() => setAvisoFoco(null)}>
            <i className="ti ti-x" />
          </button>
        </div>
      )}

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : erro ? (
        <ErroCarga mensagem={erro} onRetry={carregar} />
      ) : lista.length === 0 ? (
        <div className="empty-state">
          <i className={`ti ${aba.empty.icon}`} />
          <p className="empty-title">{aba.empty.title}</p>
          <p className="empty-subtitle">{aba.empty.sub}</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  {aba.colunas.map(c => <th key={c.key} style={{ textAlign: c.align || 'left' }}>{c.label}</th>)}
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {lista.map(m => (
                  <tr key={m.id} style={{ cursor: 'pointer' }} onClick={() => abrirEdicao(m)}>
                    {aba.colunas.map(c => (
                      <td key={c.key} className={c.mono ? 'mono' : undefined} style={{
                        textAlign: c.align || 'left',
                        fontWeight: c.strong ? 600 : undefined,
                        fontSize: c.small ? 12 : undefined,
                        color: c.strong ? 'var(--text-1)' : c.muted ? 'var(--text-3)' : undefined,
                      }}>
                        {c.render ? c.render(m) : (m[c.key] || '—')}
                      </td>
                    ))}
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button className="btn btn-icon" title="Editar" onClick={ev => { ev.stopPropagation(); abrirEdicao(m) }}><i className="ti ti-pencil" /></button>
                      <button className="btn btn-icon" title="Remover" onClick={ev => { ev.stopPropagation(); remover(m) }}><i className="ti ti-trash" style={{ color: 'var(--err-text)' }} /></button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {totalPaginas > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: 12, borderTop: '1px solid var(--border-2)' }}>
              <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <i className="ti ti-chevron-left" />
              </button>
              {paginasVisiveis(page, totalPaginas).map((n, i) => n === '…'
                ? <span key={`e${i}`} style={{ padding: '0 6px', color: 'var(--text-4)' }}>…</span>
                : (
                  <button key={n} onClick={() => setPage(n)} className="btn btn-sm"
                    style={{
                      minWidth: 32, justifyContent: 'center', border: 'none',
                      background: n === page ? 'var(--primary)' : 'transparent',
                      color: n === page ? 'var(--primary-contrast)' : 'var(--text-2)', fontWeight: n === page ? 700 : 500,
                    }}>{n}</button>
                ))}
              <button className="btn btn-ghost btn-sm" disabled={page === totalPaginas} onClick={() => setPage(p => p + 1)}>
                <i className="ti ti-chevron-right" />
              </button>
            </div>
          )}
        </div>
      )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editId ? 'Editar regra' : 'Nova regra'} · {aba.label}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  {aba.campos.map(campo => {
                    // Campo condicionado (ex.: redução de base, que só vale em
                    // linha de NCM): fica visível e desligado, com o motivo à
                    // vista — o usuário não descobre a regra levando um erro.
                    const motivo = campo.bloqueio ? campo.bloqueio(form) : null
                    return (
                      <div className="field" key={campo.key} style={campo.full ? { gridColumn: '1 / -1' } : undefined}>
                        <label style={motivo ? { color: 'var(--text-4)' } : undefined}>
                          {campo.label}
                          {campo.ajuda && (
                            <BalaoAjuda titulo={campo.ajuda.titulo}>{campo.ajuda.texto}</BalaoAjuda>
                          )}
                        </label>
                        <CampoInput campo={campo} value={form[campo.key]} bloqueado={!!motivo}
                          onChange={setCampo(campo.key)} />
                        {(motivo || campo.dica) && (
                          <div style={{ fontSize: 11.5, color: 'var(--text-4)', marginTop: 4, lineHeight: 1.5 }}>
                            {motivo || (typeof campo.dica === 'function'
                              ? campo.dica(form[campo.key], form)
                              : campo.dica)}
                          </div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Salvando…' : 'Salvar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

// Deep-link vindo das Divergências de ST: ?aba=mva&ncm=…&cest=…&uf_destino=…
// abre a aba certa com o modal de cadastro pré-preenchido (lido UMA vez).
function lerDeepLink() {
  const q = new URLSearchParams(window.location.search)
  const aba = q.get('aba')
  if (!aba || !ABAS.some(a => a.id === aba && !a.custom)) return null
  const prefill = {}
  for (const k of ['ncm', 'cest', 'uf_destino', 'uf_origem']) {
    if (q.get(k)) prefill[k] = q.get(k)
  }
  // Limpa a URL para o F5/aba trocada não reabrir o modal.
  window.history.replaceState({}, '', window.location.pathname)
  return { aba, prefill }
}

export default function MatrizesFiscais() {
  const { toasts, toast } = useToast()
  const [deepLink] = useState(lerDeepLink)
  const [tab, setTab] = useState(deepLink?.aba || 'mva')
  const [bulkVersion, setBulkVersion] = useState(0)   // bump → remonta o grid após import
  const [bulkBusy, setBulkBusy] = useState(false)
  const [resultado, setResultado] = useState(null)    // resumo da importação (modal)
  const fileRef = useRef(null)
  const aba = ABAS.find(a => a.id === tab)

  // Fase 3: "Cadastrar protocolo" da aba Saúde abre o CRUD de Protocolos com
  // o par origem→destino já preenchido (mesmo mecanismo do deep-link).
  const [prefillPar, setPrefillPar] = useState(null)
  const cadastrarPar = useCallback((p) => {
    setFocoUf(null)
    setPrefillPar({ uf_origem: p.uf_origem, uf_destino: p.uf_destino })
    setTab('protocolos')
  }, [])

  // "Abrir para corrigir" da aba Saúde: leva à aba da matriz e pede que a linha
  // seja aberta para edição com a sigla certa. `{ id, matriz, campo, valor, sugestao }`.
  const [focoUf, setFocoUf] = useState(null)
  const corrigirUf = useCallback((item) => {
    setPrefillPar(null)
    setFocoUf(item)
    setTab(item.matriz)
  }, [])

  // Contador de propostas pendentes (chip da aba Revisão).
  const [pendencias, setPendencias] = useState(0)
  const atualizarPendencias = useCallback(async () => {
    try { setPendencias((await api.propostasResumo())?.total_pendentes || 0) }
    catch { /* silencioso: o chip é informativo */ }
  }, [])
  useEffect(() => { atualizarPendencias() }, [atualizarPendencias])

  async function exportar() {
    setBulkBusy(true)
    try {
      const { blob, filename } = await api.exportarMatriz(tab)
      saveBlob(blob, filename)
      toast('Planilha exportada (vazia = template com os cabeçalhos).', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setBulkBusy(false) }
  }

  async function importar(e) {
    const file = e.target.files?.[0]
    e.target.value = ''                 // permite reimportar o mesmo arquivo
    if (!file) return
    setBulkBusy(true)
    try {
      const r = await api.importarMatriz(tab, file)
      setBulkVersion(v => v + 1)
      if (r.erros?.length) {
        setResultado(r)   // abre o modal com o relatório de erros
      } else {
        toast(`Importação concluída: ${r.inseridos} novas, ${r.atualizados} atualizadas.`, 'ok')
      }
    } catch (e2) { toast(e2.message, 'error') }
    finally { setBulkBusy(false) }
  }

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <input ref={fileRef} type="file" accept=".csv" onChange={importar} style={{ display: 'none' }} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Matrizes Fiscais</h1>
          <p className="page-breadcrumb">{aba.descricao}</p>
        </div>
        {!aba.custom && (
          <div style={{ display: 'flex', gap: 8 }}>
            <button className="btn btn-secondary" disabled={bulkBusy} onClick={exportar}>
              <i className="ti ti-file-spreadsheet" /> Exportar Planilha
            </button>
            <button className="btn btn-secondary" disabled={bulkBusy} onClick={() => fileRef.current?.click()}>
              <i className="ti ti-upload" /> Importar Planilha
            </button>
          </div>
        )}
      </div>

      {/* Abas: as fontes que o motor de ICMS-ST consome */}
      <div data-tour="matrizes-abas" style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, marginBottom: 18 }}>
        {ABAS.map(a => (
          <button key={a.id} data-tour={`matrizes-tab-${a.id}`} className="btn btn-sm"
            onClick={() => { setPrefillPar(null); setFocoUf(null); setTab(a.id) }}
            style={{ border: 'none', background: tab === a.id ? 'var(--surface)' : 'transparent', color: tab === a.id ? 'var(--text-1)' : 'var(--text-3)', boxShadow: tab === a.id ? 'var(--shadow-sm)' : 'none' }}>
            <i className={`ti ${a.icon}`} /> {a.label}
            {a.id === 'revisao' && pendencias > 0 && (
              <span className="tnum" style={{
                marginLeft: 6, background: 'var(--primary)', color: 'var(--primary-contrast)',
                borderRadius: 999, fontSize: 11, fontWeight: 700, padding: '1px 7px',
              }}>{pendencias > 99 ? '99+' : pendencias}</span>
            )}
          </button>
        ))}
      </div>

      <div data-tour={`matrizes-painel-${aba.id}`}>
        {aba.id === 'revisao'
          ? <RevisaoPanel key={`${tab}:${bulkVersion}`} onMudou={atualizarPendencias} />
          : aba.id === 'saude'
            ? <SaudePanel key={`${tab}:${bulkVersion}`} onCadastrarPar={cadastrarPar}
                onCorrigirUf={corrigirUf} />
            : aba.custom
              ? <CoberturaPanel key={`${tab}:${bulkVersion}`} />
              : <CrudMatriz key={`${tab}:${bulkVersion}`} aba={aba}
                  foco={focoUf?.matriz === tab ? focoUf : null}
                  prefill={(tab === 'protocolos' && prefillPar)
                    || (deepLink?.aba === tab ? deepLink.prefill : null)} />}
      </div>
      {resultado && <ResumoImportModal r={resultado} onClose={() => setResultado(null)} />}
    </div>
  )
}
