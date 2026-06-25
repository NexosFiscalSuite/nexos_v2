import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import { api } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

const pct = (v) => (v == null || v === '' ? '—' : `${Number(v).toFixed(2)}%`)
const dataBr = (s) => (s ? s.split('-').reverse().join('/') : '—')
const vigencia = (m) =>
  `${dataBr(m.data_inicio_vigencia)} ${m.data_fim_vigencia ? `– ${dataBr(m.data_fim_vigencia)}` : '(em aberto)'}`

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
      { key: 'ato_legal', label: 'Ato legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
    ],
    campos: [
      { key: 'ncm', label: 'NCM', required: true, placeholder: '40111000' },
      { key: 'cest', label: 'CEST', required: true, placeholder: '0107500' },
      { key: 'uf_destino', label: 'UF destino', uf: true, required: true, placeholder: 'MG' },
      { key: 'mva_original', label: 'MVA Original (%)', type: 'number', required: true, placeholder: '42.00' },
      { key: 'ato_legal', label: 'Ato legal', full: true, placeholder: 'Decreto 48.589/2023' },
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
      { key: 'ato_legal', label: 'Ato legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
    ],
    campos: [
      { key: 'ncm', label: 'NCM', required: true, placeholder: '40111000' },
      { key: 'cest', label: 'CEST', required: true, placeholder: '0107500' },
      { key: 'uf_destino', label: 'UF destino', uf: true, required: true, placeholder: 'MG' },
      { key: 'regime', label: 'Regime', type: 'select', options: REGIME_OPTS, required: true },
      { key: 'segmento', label: 'Segmento', placeholder: 'Autopeças' },
      { key: 'ato_legal', label: 'Ato legal', placeholder: 'Protocolo ICMS 41/2008' },
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
      { key: 'ato_legal', label: 'Ato legal', muted: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
    ],
    campos: [
      { key: 'uf_destino', label: 'UF', uf: true, required: true, placeholder: 'MG' },
      { key: 'ncm', label: 'NCM (ou GERAL)', placeholder: 'GERAL' },
      { key: 'aliq_fcp_st', label: 'Alíquota FCP-ST (%)', type: 'number', required: true, placeholder: '2.00' },
      { key: 'aliq_fcp_interno', label: 'FCP interno (%)', type: 'number', placeholder: '2.00' },
      { key: 'ato_legal', label: 'Ato legal', full: true, placeholder: 'Lei 14.470/2002' },
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
      { key: 'numero_acordo', label: 'Acordo', strong: true },
      { key: 'vigencia', label: 'Vigência', muted: true, small: true, render: vigencia },
    ],
    campos: [
      { key: 'uf_origem', label: 'UF Origem', uf: true, required: true, placeholder: 'SP' },
      { key: 'uf_destino', label: 'UF Destino', uf: true, required: true, placeholder: 'MG' },
      { key: 'numero_acordo', label: 'Acordo', full: true, required: true, placeholder: 'Protocolo ICMS 41/2008' },
      ...VIGENCIA_CAMPOS,
    ],
  },
]

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

function CrudMatriz({ aba }) {
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [filtroUf, setFiltroUf] = useState('')
  const [modal, setModal] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(() => vazioDe(aba.campos))
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setLista(await aba.api.list({ uf: filtroUf || undefined }) || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [aba, filtroUf, toast])

  useEffect(() => { carregar() }, [carregar])

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
        <input value={filtroUf} onChange={e => setFiltroUf(e.target.value.toUpperCase())} maxLength={2}
          placeholder="Filtrar por UF…" style={{ width: 160 }} />
        <button className="btn btn-primary" onClick={abrirNova}><i className="ti ti-plus" /> Nova regra</button>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
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

export default function MatrizesFiscais() {
  const [tab, setTab] = useState('mva')
  const aba = ABAS.find(a => a.id === tab)

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Matrizes Fiscais</h1>
          <p className="page-breadcrumb">{aba.descricao}</p>
        </div>
      </div>

      {/* Abas: as 3 fontes que o motor de ICMS-ST consome */}
      <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, marginBottom: 18 }}>
        {ABAS.map(a => (
          <button key={a.id} onClick={() => setTab(a.id)} className="btn btn-sm"
            style={{ border: 'none', background: tab === a.id ? 'var(--surface)' : 'transparent', color: tab === a.id ? 'var(--text-1)' : 'var(--text-3)', boxShadow: tab === a.id ? 'var(--shadow-sm)' : 'none' }}>
            <i className={`ti ${a.icon}`} /> {a.label}
          </button>
        ))}
      </div>

      <CrudMatriz key={tab} aba={aba} />
    </div>
  )
}
