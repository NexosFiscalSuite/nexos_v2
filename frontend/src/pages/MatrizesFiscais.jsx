import { useState, useEffect, useCallback, useRef } from 'react'
import Dropdown from '../components/Dropdown'
import ErroCarga from '../components/ErroCarga'
import ResumoImportModal from '../components/ResumoImportModal'
import { api, saveBlob } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

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

// ── Campos comuns de vigência (todas as matrizes herdam) ──
const VIGENCIA_CAMPOS = [
  { key: 'data_inicio_vigencia', label: 'Início da vigência', type: 'date', required: true },
  { key: 'data_fim_vigencia', label: 'Fim da vigência (vazio = em aberto)', type: 'date' },
]

const ABAS = [
  {
    id: 'mva', label: 'MVA', icon: 'ti-percentage',
    api: { list: api.matrizesMva, create: api.criarMatrizMva, update: api.editarMatrizMva, remove: api.removerMatrizMva },
    descricao: 'MVA Original por NCM + CEST + UF de destino — a margem que o motor aplica na base da ST',
    empty: { icon: 'ti-percentage', title: 'Nenhuma matriz de MVA', sub: 'Cadastre a MVA Original por NCM, CEST e UF para o motor calcular a base de ST.' },
    colunas: [
      { key: 'ncm', label: 'NCM', mono: true },
      { key: 'cest', label: 'CEST', mono: true },
      { key: 'uf_destino', label: 'UF', render: (m) => badge(m.uf_destino) },
      { key: 'mva_original', label: 'MVA Original', align: 'right', strong: true, render: (m) => pct(m.mva_original) },
      { key: 'base_legal', label: 'Base Legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
      { key: 'created_at', label: 'Cadastro', muted: true, small: true, render: dataCadastro },
    ],
    campos: [
      { key: 'ncm', label: 'NCM', required: true, placeholder: '40111000' },
      { key: 'cest', label: 'CEST', required: true, placeholder: '0107500' },
      { key: 'uf_destino', label: 'UF destino', uf: true, required: true, placeholder: 'MG' },
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
      { key: 'uf_destino', label: 'UF destino', uf: true, required: true, placeholder: 'MG' },
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
      { key: 'uf_destino', label: 'UF', uf: true, required: true, placeholder: 'MG' },
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
    descricao: 'Alíquota modal do ICMS por UF de destino (com FCP integrado) — vigente na data de emissão da nota',
    empty: { icon: 'ti-receipt-tax', title: 'Nenhuma alíquota cadastrada', sub: 'Cadastre a alíquota modal de cada UF (com vigência). Sem ela, o motor não audita notas para a UF.' },
    colunas: [
      { key: 'uf_destino', label: 'UF', render: (m) => badge(m.uf_destino) },
      { key: 'aliq_modal', label: 'Modal', align: 'right', strong: true, render: (m) => pct(m.aliq_modal) },
      { key: 'aliq_fcp_integrado', label: 'FCP integrado', align: 'right', muted: true, render: (m) => pct(m.aliq_fcp_integrado) },
      { key: 'base_legal', label: 'Base Legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
      { key: 'created_at', label: 'Cadastro', muted: true, small: true, render: dataCadastro },
    ],
    campos: [
      { key: 'uf_destino', label: 'UF destino', uf: true, required: true, placeholder: 'MG' },
      { key: 'aliq_modal', label: 'Alíquota modal (%)', type: 'number', required: true, placeholder: '18.00' },
      { key: 'aliq_fcp_integrado', label: 'FCP integrado (%)', type: 'number', placeholder: '0.00' },
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
      { key: 'uf_origem', label: 'UF Origem', uf: true, required: true, placeholder: 'SP' },
      { key: 'uf_destino', label: 'UF Destino', uf: true, required: true, placeholder: 'MG' },
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
    id: 'cobertura', label: 'Cobertura', icon: 'ti-radar-2', custom: true,
    descricao: 'O que a carteira movimenta × o que as matrizes cobrem — a fila de curadoria, ordenada por valor',
  },
]

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
  const { toasts } = useToast()
  const [dados, setDados] = useState(null)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [filtroUf, setFiltroUf] = useState('')

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try { setDados(await api.coberturaMatrizes({ uf: filtroUf || undefined })) }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [filtroUf])

  useEffect(() => { carregar() }, [carregar])

  if (loading) return <div className="center-loader"><div className="spinner" /></div>
  if (erro) return <ErroCarga mensagem={erro} onRetry={carregar} />
  const resumo = dados?.resumo || {}
  const grupos = dados?.grupos || []

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
        <input value={filtroUf} onChange={e => setFiltroUf(e.target.value.toUpperCase())} maxLength={2}
          placeholder="Filtrar por UF…" style={{ width: 160 }} />
        <div style={{ display: 'flex', gap: 18, alignItems: 'baseline' }}>
          <span style={{ color: 'var(--text-3)', fontSize: 13 }}>
            {resumo.grupos || 0} grupos · {brl(resumo.valor_total)}
          </span>
          <span style={{ fontWeight: 700, fontSize: 18, color: (resumo.pct_valor_coberto ?? 100) >= 90 ? 'var(--ok-text)' : 'var(--err-text)' }}>
            {resumo.pct_valor_coberto ?? 100}% do valor coberto
          </span>
        </div>
      </div>

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
        </div>
      )}
    </div>
  )
}

function vazioDe(campos) {
  return Object.fromEntries(campos.map(c => [c.key, c.type === 'select' ? (c.options[0]?.value || '') : '']))
}

function CampoInput({ campo, value, onChange }) {
  if (campo.type === 'select')
    return <Dropdown value={value} onChange={onChange} options={campo.options} placeholder="Selecione…" />
  if (campo.type === 'date')
    return <input type="date" value={value || ''} onChange={e => onChange(e.target.value)} required={campo.required} />
  if (campo.type === 'number')
    return <input type="number" step="0.01" min="0" value={value} onChange={e => onChange(e.target.value)} placeholder={campo.placeholder} required={campo.required} />
  return (
    <input value={value} maxLength={campo.uf ? 2 : undefined} placeholder={campo.placeholder} required={campo.required}
      onChange={e => onChange(campo.uf ? e.target.value.toUpperCase() : e.target.value)} />
  )
}

function CrudMatriz({ aba, prefill }) {
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [filtroUf, setFiltroUf] = useState('')
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

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try {
      const r = await aba.api.list({ uf: filtroUf || undefined, page, page_size: PAGE_SIZE })
      setLista(r?.items || (Array.isArray(r) ? r : []))
      setTotal(r?.total ?? 0)
    }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [aba, filtroUf, page])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setPage(1) }, [filtroUf])
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))

  function abrirNova() { setEditId(null); setForm(vazioDe(aba.campos)); setModal(true) }
  function abrirEdicao(m) { setEditId(m.id); setForm({ ...vazioDe(aba.campos), ...m, data_fim_vigencia: m.data_fim_vigencia || '' }); setModal(true) }

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form, data_fim_vigencia: form.data_fim_vigencia || null }
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

  const setCampo = (k) => (v) => setForm(f => ({ ...f, [k]: v }))

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, marginBottom: 14 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <input value={filtroUf} onChange={e => setFiltroUf(e.target.value.toUpperCase())} maxLength={2}
            placeholder="Filtrar por UF…" style={{ width: 160 }} />
          {total > 0 && (
            <span className="tnum" style={{ color: 'var(--text-3)', fontSize: 13 }}>
              {total.toLocaleString('pt-BR')} {total === 1 ? 'regra' : 'regras'}
            </span>
          )}
        </div>
        <button className="btn btn-primary" onClick={abrirNova}><i className="ti ti-plus" /> Nova regra</button>
      </div>

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
                      color: n === page ? '#fff' : 'var(--text-2)', fontWeight: n === page ? 700 : 500,
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
                  {aba.campos.map(campo => (
                    <div className="field" key={campo.key} style={campo.full ? { gridColumn: '1 / -1' } : undefined}>
                      <label>{campo.label}</label>
                      <CampoInput campo={campo} value={form[campo.key]} onChange={setCampo(campo.key)} />
                    </div>
                  ))}
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
      <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, marginBottom: 18 }}>
        {ABAS.map(a => (
          <button key={a.id} onClick={() => setTab(a.id)} className="btn btn-sm"
            style={{ border: 'none', background: tab === a.id ? 'var(--surface)' : 'transparent', color: tab === a.id ? 'var(--text-1)' : 'var(--text-3)', boxShadow: tab === a.id ? 'var(--shadow-sm)' : 'none' }}>
            <i className={`ti ${a.icon}`} /> {a.label}
          </button>
        ))}
      </div>

      {aba.custom
        ? <CoberturaPanel key={`${tab}:${bulkVersion}`} />
        : <CrudMatriz key={`${tab}:${bulkVersion}`} aba={aba}
            prefill={deepLink?.aba === tab ? deepLink.prefill : null} />}
      {resultado && <ResumoImportModal r={resultado} onClose={() => setResultado(null)} />}
    </div>
  )
}
