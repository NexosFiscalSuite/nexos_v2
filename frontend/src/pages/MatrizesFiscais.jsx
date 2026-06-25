import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

const VAZIO = {
  ncm: '', cest: '', uf_destino: '', mva_original: '', ato_legal: '',
  data_inicio_vigencia: '', data_fim_vigencia: '',
}

const pct = (v) => (v == null || v === '' ? '—' : `${Number(v).toFixed(2)}%`)
const dataBr = (s) => (s ? s.split('-').reverse().join('/') : '—')

export default function MatrizesFiscais() {
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [filtroUf, setFiltroUf] = useState('')
  const [modal, setModal] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(VAZIO)
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setLista(await api.matrizesMva({ uf: filtroUf || undefined }) || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [toast, filtroUf])

  useEffect(() => { carregar() }, [carregar])

  function abrirNova() { setEditId(null); setForm(VAZIO); setModal(true) }
  function abrirEdicao(m) {
    setEditId(m.id)
    setForm({ ...VAZIO, ...m, data_fim_vigencia: m.data_fim_vigencia || '' })
    setModal(true)
  }

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = { ...form, data_fim_vigencia: form.data_fim_vigencia || null }
      if (editId) { await api.editarMatrizMva(editId, payload); toast('Matriz atualizada.', 'ok') }
      else { await api.criarMatrizMva(payload); toast('Matriz cadastrada.', 'ok') }
      setModal(false); setForm(VAZIO); setEditId(null)
      await carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  async function remover(m) {
    if (!confirm(`Remover a matriz MVA de NCM ${m.ncm} / ${m.uf_destino}?`)) return
    try { await api.removerMatrizMva(m.id); toast('Matriz removida.', 'ok'); await carregar() }
    catch (e) { toast(e.message, 'error') }
  }

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Matrizes Fiscais</h1>
          <p className="page-breadcrumb">MVA Original por NCM + CEST + UF — as regras que o motor de ICMS-ST consome</p>
        </div>
        <button className="btn btn-primary" onClick={abrirNova}><i className="ti ti-plus" /> Nova matriz</button>
      </div>

      <div style={{ marginBottom: 14 }}>
        <input value={filtroUf} onChange={e => setFiltroUf(e.target.value.toUpperCase())} maxLength={2}
          placeholder="Filtrar por UF…" style={{ width: 160 }} />
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : lista.length === 0 ? (
        <div className="empty-state">
          <i className="ti ti-table-options" />
          <p className="empty-title">Nenhuma matriz de MVA cadastrada</p>
          <p className="empty-subtitle">Cadastre a MVA Original por NCM, CEST e UF de destino para o motor de ICMS-ST auditar as notas automaticamente — sem depender de script de seed.</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th>NCM</th><th>CEST</th><th>UF</th>
                  <th style={{ textAlign: 'right' }}>MVA Original</th>
                  <th>Ato legal</th><th>Vigência</th><th></th>
                </tr>
              </thead>
              <tbody>
                {lista.map(m => (
                  <tr key={m.id} style={{ cursor: 'pointer' }} onClick={() => abrirEdicao(m)}>
                    <td className="mono">{m.ncm}</td>
                    <td className="mono">{m.cest}</td>
                    <td><span className="badge">{m.uf_destino}</span></td>
                    <td className="mono" style={{ textAlign: 'right', fontWeight: 600, color: 'var(--text-1)' }}>{pct(m.mva_original)}</td>
                    <td style={{ color: 'var(--text-3)' }}>{m.ato_legal || '—'}</td>
                    <td style={{ color: 'var(--text-3)', fontSize: 12 }}>
                      {dataBr(m.data_inicio_vigencia)} {m.data_fim_vigencia ? `– ${dataBr(m.data_fim_vigencia)}` : '(em aberto)'}
                    </td>
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
              <h2>{editId ? 'Editar matriz de MVA' : 'Nova matriz de MVA'}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 90px', gap: 14 }}>
                  <div className="field">
                    <label>NCM</label>
                    <input value={form.ncm} onChange={set('ncm')} placeholder="40111000" required />
                  </div>
                  <div className="field">
                    <label>CEST</label>
                    <input value={form.cest} onChange={set('cest')} placeholder="0107500" required />
                  </div>
                  <div className="field">
                    <label>UF destino</label>
                    <input value={form.uf_destino} onChange={e => setForm(f => ({ ...f, uf_destino: e.target.value.toUpperCase() }))} maxLength={2} placeholder="MG" required />
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 14 }}>
                  <div className="field">
                    <label>MVA Original (%)</label>
                    <input type="number" step="0.01" min="0" value={form.mva_original} onChange={set('mva_original')} placeholder="42.00" required />
                  </div>
                  <div className="field">
                    <label>Ato legal</label>
                    <input value={form.ato_legal} onChange={set('ato_legal')} placeholder="Decreto 48.589/2023" />
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div className="field">
                    <label>Início da vigência</label>
                    <input type="date" value={form.data_inicio_vigencia} onChange={set('data_inicio_vigencia')} required />
                  </div>
                  <div className="field">
                    <label>Fim da vigência <span style={{ color: 'var(--text-4)', fontWeight: 400 }}>(vazio = em aberto)</span></label>
                    <input type="date" value={form.data_fim_vigencia} onChange={set('data_fim_vigencia')} />
                  </div>
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
