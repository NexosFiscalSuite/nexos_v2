import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import EmptyState from '../components/EmptyState'
import { api, saveBlob } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const FLUXO_OPTS = [
  { value: 'entrada', label: 'Entrada' }, { value: 'saida', label: 'Saída' },
  { value: 'servico', label: 'Serviço' }, { value: 'cte', label: 'CT-e' },
]
const POLL_MS = 1200
const uid = () => `${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
const withUid = (cols) => (cols || []).map(c => ({ ...c, uid: c.uid || uid() }))
const novoForm = () => ({ nome: '', fluxo: 'entrada', totais: false, finalidade: true, calculos: true, capa: [], itens: [] })

export default function Relatorios() {
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { toasts, toast } = useToast()

  const [tags, setTags] = useState([])
  const [modelos, setModelos] = useState([])
  const [loading, setLoading] = useState(false)
  const [gerando, setGerando] = useState(null)

  const [modal, setModal] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(novoForm())
  const [builderTab, setBuilderTab] = useState('capa')
  const [addTag, setAddTag] = useState('')
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    if (!selectedEmpresa) { setModelos([]); return }
    setLoading(true)
    try { setModelos(await api.relModelos(selectedEmpresa.id) || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [selectedEmpresa])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { api.relTags().then(setTags).catch(() => {}) }, [])

  // ── builder helpers ──
  const colsKey = builderTab === 'capa' ? 'capa' : 'itens'
  const cols = form[colsKey]
  const usados = new Set(cols.filter(c => c.tag).map(c => c.tag))
  // Na aba ITENS, além das tags de item, liberamos as tags de capa "herdáveis"
  // (Identificação/Emitente/Destinatário) — viram dados da nota repetidos por linha.
  const GRUPOS_HERDAVEIS = new Set(['Identificação', 'Emitente', 'Destinatário'])
  const disp = builderTab === 'capa'
    ? (t) => t.escopo === 'capa'
    : (t) => t.escopo === 'item' || (t.escopo === 'capa' && GRUPOS_HERDAVEIS.has(t.grupo))
  const disponiveis = tags.filter(t => disp(t) && !usados.has(t.key))
    .map(t => ({ value: t.key, label: `[${t.grupo}] ${t.label}` }))
  const tagLabel = (k) => (tags.find(t => t.key === k)?.label) || k

  function addColuna(key) {
    if (!key) return
    setForm(f => ({ ...f, [colsKey]: [...f[colsKey], { tag: key, label: tagLabel(key), uid: uid() }] }))
    setAddTag('')
  }
  function addAuditCol() {
    setForm(f => ({ ...f, [colsKey]: [...f[colsKey], { audit: true, label: '', uid: uid() }] }))
  }
  function renomear(i, label) { setForm(f => { const a = [...f[colsKey]]; a[i] = { ...a[i], label }; return { ...f, [colsKey]: a } }) }
  function remover(i) { setForm(f => ({ ...f, [colsKey]: f[colsKey].filter((_, x) => x !== i) })) }
  function mover(i, dir) {
    setForm(f => {
      const a = [...f[colsKey]]; const j = i + dir
      if (j < 0 || j >= a.length) return f
      ;[a[i], a[j]] = [a[j], a[i]]
      return { ...f, [colsKey]: a }
    })
  }

  function abrirNovo() { setForm(novoForm()); setEditId(null); setBuilderTab('capa'); setModal(true) }
  function abrirEdit(m) {
    const c = m.config || {}
    // migra auditoria "legada" (campo separado) para colunas inline no fim da capa
    const capaLegacy = (c.auditoria || []).map(n => ({ audit: true, label: n }))
    setForm({
      nome: m.nome, fluxo: m.fluxo, totais: !!c.totais, finalidade: c.finalidade !== false, calculos: c.calculos !== false,
      capa: withUid([...(c.capa || []), ...capaLegacy]), itens: withUid(c.itens || []),
    })
    setEditId(m.id); setBuilderTab('capa'); setModal(true)
  }

  const strip = (cols) => cols.map(({ uid: _u, ...c }) => (c.audit ? { audit: true, label: c.label || 'Auditoria' } : { tag: c.tag, label: c.label }))

  async function salvar(e) {
    e.preventDefault()
    const temDados = [...form.capa, ...form.itens].some(c => !c.audit)
    if (!temDados) { toast('Adicione ao menos uma coluna de dados.', 'error'); return }
    setSaving(true)
    try {
      const cfg = { totais: form.totais, finalidade: form.finalidade, calculos: form.calculos, capa: strip(form.capa), itens: strip(form.itens), auditoria: [] }
      if (editId) await api.relEditarModelo(editId, { nome: form.nome, config: cfg })
      else await api.relCriarModelo(selectedEmpresa.id, { nome: form.nome, fluxo: form.fluxo, ...cfg })
      toast(editId ? 'Modelo atualizado.' : 'Modelo criado.', 'ok')
      setModal(false); carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }
  async function excluir(id) {
    if (!confirm('Excluir este modelo?')) return
    try { await api.relExcluirModelo(id); toast('Excluído.', 'ok'); carregar() } catch (e) { toast(e.message, 'error') }
  }

  async function pollDownload(jobId) {
    try {
      const j = await api.job(jobId)
      if (j.status === 'done') {
        const { blob, filename } = await api.relDownload(jobId)
        saveBlob(blob, filename)
        toast(`Relatório gerado (${j.result?.total_notas ?? 0} notas).`, 'ok'); setGerando(null); return
      }
      if (j.status === 'failed') { toast(j.error || 'Falha ao gerar.', 'error'); setGerando(null); return }
      setTimeout(() => pollDownload(jobId), POLL_MS)
    } catch (e) { toast(e.message, 'error'); setGerando(null) }
  }
  async function gerar(m) {
    setGerando(m.id)
    try { const res = await api.relGerar(selectedEmpresa.id, { modelo_id: m.id, ano, mes }); pollDownload(res.job_id) }
    catch (e) { toast(e.message, 'error'); setGerando(null) }
  }

  if (!selectedEmpresa) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Relatórios</h1></div>
        <div className="empty-state"><i className="ti ti-report" /><p>Selecione uma empresa no topo.</p></div>
      </div>
    )
  }

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div><h1 className="page-title">Relatórios</h1><p className="page-breadcrumb">{selectedEmpresa.razao_social} · {mes}/{ano}</p></div>
        <button className="btn btn-primary" onClick={abrirNovo}><i className="ti ti-plus" /> Novo modelo</button>
      </div>

      {loading ? <div className="center-loader"><div className="spinner" /></div>
        : modelos.length === 0 ? (
          <EmptyState icon="ti-report" title="Nenhum modelo de relatório"
            subtitle="Monte modelos com as colunas que o seu escritório precisa e gere planilhas (Excel/CSV) das notas da competência em um clique." />
        ) : (
            <div className="stat-grid">
              {modelos.map(m => {
                const c = m.config || {}
                return (
                  <div key={m.id} className="card">
                    <div className="card-header">
                      <div>
                        <div className="card-title">{m.nome}</div>
                        <div className="card-sub">{FLUXO_OPTS.find(f => f.value === m.fluxo)?.label || m.fluxo} · {(c.capa || []).length} cap. · {(c.itens || []).length} itens{c.totais ? ' · totais' : ''}</div>
                      </div>
                      <div style={{ display: 'flex', gap: 4 }}>
                        <button className="btn btn-icon" title="Editar" onClick={() => abrirEdit(m)}><i className="ti ti-pencil" /></button>
                        <button className="btn btn-icon" title="Excluir" onClick={() => excluir(m.id)}><i className="ti ti-trash" /></button>
                      </div>
                    </div>
                    <button className="btn btn-primary btn-sm" style={{ marginTop: 12 }} disabled={gerando === m.id} onClick={() => gerar(m)}>
                      {gerando === m.id ? <><span className="login-spin" /> Gerando…</> : <><i className="ti ti-file-spreadsheet" /> Gerar Excel ({mes}/{ano})</>}
                    </button>
                  </div>
                )
              })}
            </div>
          )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 760, maxWidth: '96%' }}>
            <div className="modal-header">
              <h2>{editId ? 'Editar modelo' : 'Novo modelo de relatório'}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 200px', gap: 14 }}>
                  <div className="field"><label>Nome</label><input value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} required /></div>
                  <div className="field"><label>Fluxo</label><Dropdown value={form.fluxo} onChange={v => setForm(f => ({ ...f, fluxo: v }))} options={FLUXO_OPTS} /></div>
                </div>

                {/* Abas do construtor */}
                <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, marginBottom: 12 }}>
                  {[['capa', 'Capa (1 linha = 1 NF)'], ['itens', 'Itens (1 linha = 1 produto)']].map(([v, l]) => (
                    <button type="button" key={v} onClick={() => { setBuilderTab(v); setAddTag('') }} className="btn btn-sm"
                      style={{ background: builderTab === v ? 'var(--surface)' : 'transparent', color: builderTab === v ? 'var(--text-1)' : 'var(--text-3)', boxShadow: builderTab === v ? 'var(--shadow-sm)' : 'none', border: 'none' }}>{l}</button>
                  ))}
                </div>

                <div className="field">
                  <label>Adicionar coluna</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <div style={{ flex: 1 }}>
                      <Dropdown value={addTag} onChange={addColuna} options={[{ value: '', label: 'Escolha uma tag…' }, ...disponiveis]} placeholder="Escolha uma tag…" />
                    </div>
                    <button type="button" className="btn btn-ghost btn-sm" title="Coluna em branco p/ anotação manual (Observações), fundo amarelo. A observação do XML está nas tags do grupo 'Adicionais'." onClick={addAuditCol}><i className="ti ti-highlight" /> Observação</button>
                  </div>
                </div>

                {/* Colunas selecionadas (renomear + reordenar + auditoria inline) */}
                {cols.length === 0 ? <p style={{ fontSize: 12, color: 'var(--text-4)' }}>Nenhuma coluna nesta aba ainda.</p> : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {cols.map((c, i) => (
                      <div key={c.uid} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span style={{ fontSize: 11, color: 'var(--text-4)', width: 22, textAlign: 'right' }}>{i + 1}.</span>
                        <input value={c.label} onChange={e => renomear(i, e.target.value)} placeholder={c.audit ? 'ex.: Observações Fiscais' : ''} style={{ flex: 1 }} />
                        {c.audit
                          ? <span style={{ fontSize: 10, fontWeight: 600, background: '#FFFACD', color: '#7a5c00', padding: '2px 8px', borderRadius: 6, minWidth: 90, textAlign: 'center' }}>auditoria</span>
                          : <span style={{ fontSize: 11, color: 'var(--text-4)', minWidth: 90 }} className="mono">{c.tag}</span>}
                        <button type="button" className="btn btn-icon" onClick={() => mover(i, -1)} disabled={i === 0}><i className="ti ti-chevron-up" /></button>
                        <button type="button" className="btn btn-icon" onClick={() => mover(i, 1)} disabled={i === cols.length - 1}><i className="ti ti-chevron-down" /></button>
                        <button type="button" className="btn btn-icon" onClick={() => remover(i)}><i className="ti ti-x" /></button>
                      </div>
                    ))}
                  </div>
                )}

                <div className="divider" />

                {/* Opções */}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
                    <input type="checkbox" checked={form.calculos} onChange={e => setForm(f => ({ ...f, calculos: e.target.checked }))} /> Colunas de cálculo — Capa: Valor Líquido, Total Nota, Diferença · Itens: Líquido, ICMS Apurado, Diferença ICMS
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
                    <input type="checkbox" checked={form.finalidade} onChange={e => setForm(f => ({ ...f, finalidade: e.target.checked }))} /> Incluir coluna &ldquo;Finalidade&rdquo; (Tipo SPED)
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, cursor: 'pointer' }}>
                    <input type="checkbox" checked={form.totais} onChange={e => setForm(f => ({ ...f, totais: e.target.checked }))} /> Linha de totais no fim (SUBTOTAL, opcional)
                  </label>
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Salvando…' : 'Salvar modelo'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
