import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import EmptyState from '../components/EmptyState'
import { api } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useRefresh } from '../context/RefreshContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const TABS = [
  { value: 'quebra', label: 'Quebra de sequência', icon: 'ti-stairs' },
  { value: 'canceladas', label: 'Notas canceladas', icon: 'ti-ban' },
  { value: 'inutilizadas', label: 'Numerações inutilizadas', icon: 'ti-eraser' },
]
const CLASSIF_OPTS = [
  { value: 'cancelada', label: 'Cancelada' },
  { value: 'inutilizada', label: 'Inutilizada' },
  { value: 'outra', label: 'Outra' },
]
const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const faixaKey = (q) => `${q.modelo}|${q.serie}|${q.num_inicio}|${q.num_fim}`

export default function Conformidade() {
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { bumpData, dataVersion } = useRefresh()
  const { toasts, toast } = useToast()

  const [tab, setTab] = useState('quebra')
  const [quebras, setQuebras] = useState([])
  const [canceladas, setCanceladas] = useState([])
  const [inutilizadas, setInutilizadas] = useState([])
  const [loading, setLoading] = useState(false)
  const [sel, setSel] = useState(new Set())          // faixas selecionadas (quebra)
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState({ classificacao: 'cancelada', justificativa: '', auditor_email: '', auditor_password: '' })
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    if (!selectedEmpresa) return
    setLoading(true); setSel(new Set())
    try {
      if (tab === 'quebra') {
        setQuebras((await api.quebras(selectedEmpresa.id, ano, mes)).quebras || [])
      } else if (tab === 'canceladas') {
        const r = await api.notas(selectedEmpresa.id, { status_: 'cancelada', ano, mes, page_size: 200 })
        setCanceladas(r.notas || [])
      } else {
        setInutilizadas(await api.quebraCiencias(selectedEmpresa.id, 'inutilizada') || [])
      }
    } catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
    // dataVersion não é lido no corpo: é o gatilho de refresh global (RefreshContext).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedEmpresa, tab, ano, mes, dataVersion, toast])

  useEffect(() => { carregar() }, [carregar])

  const allSel = quebras.length > 0 && quebras.every(q => sel.has(faixaKey(q)))
  function toggleAll() {
    setSel(() => allSel ? new Set() : new Set(quebras.map(faixaKey)))
  }
  function toggleOne(q) {
    setSel(prev => { const s = new Set(prev); const k = faixaKey(q); s.has(k) ? s.delete(k) : s.add(k); return s })
  }
  function abrirCiencia(umaQ) {
    if (umaQ) setSel(new Set([faixaKey(umaQ)]))
    if (!umaQ && !sel.size) { toast('Selecione ao menos uma faixa.', 'error'); return }
    setModal(true)
  }

  async function confirmar(e) {
    e.preventDefault()
    const faixas = quebras.filter(q => sel.has(faixaKey(q))).map(q => ({
      modelo: q.modelo, serie: q.serie, num_inicio: q.num_inicio, num_fim: q.num_fim,
    }))
    setSaving(true)
    try {
      const r = await api.darCienciaLote(selectedEmpresa.id, { faixas, ...form })
      toast(`Ciência registrada em ${r.afetadas} faixa(s).`, 'ok')
      setModal(false); setForm(f => ({ ...f, justificativa: '', auditor_password: '' })); setSel(new Set()); bumpData()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  if (!selectedEmpresa) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Conformidade</h1></div>
        <EmptyState icon="ti-shield-check" title="Selecione uma empresa no topo"
          subtitle="Identifique quebras de sequência na numeração das notas, documentos cancelados e numerações inutilizadas importadas na competência." />
      </div>
    )
  }

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Conformidade</h1>
          <p className="page-breadcrumb">{selectedEmpresa.razao_social} · {mes}/{ano}</p>
        </div>
      </div>

      {/* Abas */}
      <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, marginBottom: 16 }}>
        {TABS.map(t => (
          <button key={t.value} onClick={() => setTab(t.value)} className="btn btn-sm"
            style={{
              background: tab === t.value ? 'var(--surface)' : 'transparent',
              color: tab === t.value ? 'var(--text-1)' : 'var(--text-3)',
              boxShadow: tab === t.value ? 'var(--shadow-sm)' : 'none', border: 'none',
            }}>
            <i className={`ti ${t.icon}`} /> {t.label}
          </button>
        ))}
      </div>

      {loading ? <div className="center-loader"><div className="spinner" /></div> : (
        <>
          {tab === 'quebra' && (
            quebras.length === 0 ? (
              <div className="empty-state"><i className="ti ti-circle-check" /><p>Nenhuma quebra de sequência nesta competência.</p></div>
            ) : (
              <>
                <div className="card" style={{ padding: 0 }}>
                  <div className="tbl-wrap">
                    <table className="table">
                      <thead><tr>
                        <th style={{ width: 34 }}><input type="checkbox" checked={allSel} onChange={toggleAll} /></th>
                        <th>Modelo</th><th>Série</th><th>Faixa faltante</th><th>Qtd</th><th></th>
                      </tr></thead>
                      <tbody>
                        {quebras.map((q, i) => (
                          <tr key={i} style={{ background: sel.has(faixaKey(q)) ? 'var(--primary-lt)' : undefined }}>
                            <td><input type="checkbox" checked={sel.has(faixaKey(q))} onChange={() => toggleOne(q)} /></td>
                            <td>{q.modelo || '—'}</td>
                            <td>{q.serie || '—'}</td>
                            <td className="mono">{q.num_inicio} – {q.num_fim}</td>
                            <td><span className="badge badge-warn">{q.qtd}</span></td>
                            <td style={{ textAlign: 'right' }}><button className="btn btn-secondary btn-sm" onClick={() => abrirCiencia(q)}><i className="ti ti-check" /> Ciência</button></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div style={{ marginTop: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 12, color: 'var(--text-4)' }}>{sel.size} faixa(s) selecionada(s)</span>
                  <button className="btn btn-primary" disabled={!sel.size} onClick={() => abrirCiencia(null)}>
                    <i className="ti ti-checks" /> Dar ciência em lote
                  </button>
                </div>
              </>
            )
          )}

          {tab === 'canceladas' && (
            canceladas.length === 0 ? (
              <div className="empty-state"><i className="ti ti-ban" /><p>Nenhuma nota cancelada nesta competência.</p></div>
            ) : (
              <div className="card" style={{ padding: 0 }}>
                <div className="tbl-wrap">
                  <table className="table">
                    <thead><tr><th>Modelo</th><th>Número</th><th>Série</th><th>Contraparte</th><th style={{ textAlign: 'right' }}>Valor</th><th>Emissão</th></tr></thead>
                    <tbody>
                      {canceladas.map(n => (
                        <tr key={n.id}>
                          <td>{n.modelo}</td><td className="mono">{n.numero}</td><td className="mono">{n.serie || '—'}</td>
                          <td style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{n.nome_dest || n.nome_emit || '—'}</td>
                          <td className="mono" style={{ textAlign: 'right' }}>{brl(n.valor_total)}</td>
                          <td className="mono">{n.data_emissao || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          )}

          {tab === 'inutilizadas' && (
            inutilizadas.length === 0 ? (
              <div className="empty-state"><i className="ti ti-eraser" /><p>Nenhuma numeração inutilizada registrada.</p></div>
            ) : (
              <div className="card" style={{ padding: 0 }}>
                <div className="tbl-wrap">
                  <table className="table">
                    <thead><tr><th>Modelo</th><th>Série</th><th>Faixa</th><th>Justificativa</th><th>Responsável</th></tr></thead>
                    <tbody>
                      {inutilizadas.map(c => (
                        <tr key={c.id}>
                          <td>{c.modelo}</td><td>{c.serie}</td><td className="mono">{c.num_inicio} – {c.num_fim}</td>
                          <td style={{ maxWidth: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.justificativa || '—'}</td>
                          <td>{c.ciente_nome || '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )
          )}
        </>
      )}

      {/* Modal ciência em lote (login de auditor) */}
      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 460 }}>
            <div className="modal-header">
              <h2>Dar ciência ({sel.size} faixa{sel.size > 1 ? 's' : ''})</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={confirmar}>
              <div className="modal-body">
                <div className="field">
                  <label>Classificação</label>
                  <Dropdown value={form.classificacao} onChange={v => setForm(f => ({ ...f, classificacao: v }))} options={CLASSIF_OPTS} />
                </div>
                <div className="field">
                  <label>Justificativa</label>
                  <textarea value={form.justificativa} onChange={e => setForm(f => ({ ...f, justificativa: e.target.value }))} rows={2} style={{ resize: 'vertical' }} />
                </div>
                <div className="divider" />
                <p style={{ fontSize: 12, color: 'var(--text-3)', marginBottom: 12 }}>
                  <i className="ti ti-lock" /> Confirme com as credenciais do auditor responsável:
                </p>
                <div className="field">
                  <label>E-mail do auditor</label>
                  <input type="email" value={form.auditor_email} onChange={e => setForm(f => ({ ...f, auditor_email: e.target.value }))} required autoComplete="off" />
                </div>
                <div className="field">
                  <label>Senha do auditor</label>
                  <input type="password" value={form.auditor_password} onChange={e => setForm(f => ({ ...f, auditor_password: e.target.value }))} required autoComplete="off" />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Confirmando…' : 'Confirmar ciência'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
