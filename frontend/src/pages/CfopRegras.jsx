import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import EmptyState from '../components/EmptyState'
import { api } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

const VAZIO = { tipo_item: '', cfop_origem: '', cfop_destino: '', usa_extensao: false, extensao: '', descricao: '' }

export default function CfopRegras() {
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [tipos, setTipos] = useState([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(VAZIO)
  const [editId, setEditId] = useState(null)
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setLista(await api.cfopRegras() || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [toast])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { api.tiposSped().then(setTipos).catch(() => {}) }, [])

  const tipoOpts = tipos.map(t => ({ value: t, label: t }))
  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  function novo() { setForm(VAZIO); setEditId(null); setModal(true) }
  function editar(r) { setForm({ ...VAZIO, ...r }); setEditId(r.id); setModal(true) }

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      if (editId) await api.cfopRegraEditar(editId, form)
      else await api.cfopRegraCriar(form)
      toast(editId ? 'Regra atualizada.' : 'Regra criada.', 'ok')
      setModal(false); carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  async function excluir(id) {
    if (!confirm('Excluir esta regra?')) return
    try { await api.cfopRegraExcluir(id); toast('Regra excluída.', 'ok'); carregar() }
    catch (e) { toast(e.message, 'error') }
  }

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">De/Para CFOP</h1>
          <p className="page-breadcrumb">Atribuição automática do Tipo de Item por CFOP na entrada das notas</p>
        </div>
        <button className="btn btn-primary" onClick={novo}><i className="ti ti-plus" /> Nova regra</button>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : lista.length === 0 ? (
        <EmptyState icon="ti-arrows-exchange" title="Nenhuma regra De/Para cadastrada"
          subtitle="Defina o Tipo de Item por CFOP para que o Nexos classifique automaticamente cada item na importação das notas de entrada — sem trabalho manual." />
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Tipo de Item</th><th>CFOP origem</th><th>CFOP destino</th><th>Extensão</th><th>Descrição</th><th></th></tr></thead>
              <tbody>
                {lista.map(r => (
                  <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => editar(r)}>
                    <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{r.tipo_item}</td>
                    <td className="mono">{r.cfop_origem}</td>
                    <td className="mono">{r.cfop_destino}</td>
                    <td className="mono">{r.usa_extensao ? (r.extensao || '—') : '—'}</td>
                    <td style={{ color: 'var(--text-4)' }}>{r.descricao || '—'}</td>
                    <td style={{ textAlign: 'right' }} onClick={e => e.stopPropagation()}>
                      <button className="btn btn-icon" title="Excluir" onClick={() => excluir(r.id)}><i className="ti ti-trash" /></button>
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
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 460 }}>
            <div className="modal-header">
              <h2>{editId ? 'Editar regra' : 'Nova regra'}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div className="field">
                  <label>Tipo do item</label>
                  <Dropdown value={form.tipo_item} onChange={v => setForm(f => ({ ...f, tipo_item: v }))} options={tipoOpts} placeholder="Selecione…" />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div className="field"><label>CFOP de origem</label><input value={form.cfop_origem} onChange={set('cfop_origem')} placeholder="ex.: 5102" disabled={!!editId} required /></div>
                  <div className="field"><label>CFOP de destino</label><input value={form.cfop_destino} onChange={set('cfop_destino')} placeholder="ex.: 1102" required /></div>
                </div>
                <div className="field">
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, cursor: 'pointer', fontWeight: 400 }}>
                    <input type="checkbox" checked={form.usa_extensao} onChange={e => setForm(f => ({ ...f, usa_extensao: e.target.checked }))} />
                    Usa extensão de CFOP
                  </label>
                </div>
                {form.usa_extensao && (
                  <div className="field"><label>Extensão de CFOP</label><input value={form.extensao || ''} onChange={set('extensao')} placeholder="ex.: 01" /></div>
                )}
                <div className="field"><label>Descrição (opcional)</label><input value={form.descricao || ''} onChange={set('descricao')} /></div>
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
