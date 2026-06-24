import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import { api, getUser } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

const novoForm = () => ({ nome: '', descricao: '', empresa_ids: [], user_ids: [], supervisor_id: '' })

export default function Grupos() {
  const { toasts, toast } = useToast()
  const isAdmin = (getUser()?.role) === 'admin'

  const [lista, setLista] = useState([])
  const [empresas, setEmpresas] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)

  const [modal, setModal] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(novoForm())
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setLista(await api.grupos() || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [toast])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => {
    api.empresas().then(setEmpresas).catch(() => {})
    api.listUsers().then(setUsers).catch(() => {})
  }, [])

  function abrirNovo() { setForm(novoForm()); setEditId(null); setModal(true) }
  async function abrirEdit(id) {
    try {
      const g = await api.grupo(id)
      setForm({
        nome: g.nome, descricao: g.descricao || '',
        empresa_ids: g.empresa_ids || [], user_ids: g.user_ids || [], supervisor_id: g.supervisor_id || '',
      })
      setEditId(id); setModal(true)
    } catch (e) { toast(e.message, 'error') }
  }

  const toggle = (key, id) => setForm(f => {
    const has = f[key].includes(id)
    return { ...f, [key]: has ? f[key].filter(x => x !== id) : [...f[key], id] }
  })

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      const payload = {
        nome: form.nome.trim(), descricao: form.descricao.trim() || null,
        empresa_ids: form.empresa_ids, user_ids: form.user_ids,
        supervisor_id: form.supervisor_id || null,
      }
      if (editId) await api.editarGrupo(editId, payload)
      else await api.criarGrupo(payload)
      toast(editId ? 'Grupo atualizado.' : 'Grupo criado.', 'ok')
      setModal(false); carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }
  async function excluir(id) {
    if (!confirm('Excluir este grupo? Os vínculos de empresas e membros serão removidos.')) return
    try { await api.excluirGrupo(id); toast('Excluído.', 'ok'); carregar() } catch (e) { toast(e.message, 'error') }
  }

  const supOpts = [{ value: '', label: '— sem supervisor —' }, ...users.map(u => ({ value: u.id, label: u.full_name }))]

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Grupos</h1>
          <p className="page-breadcrumb">Controle de acesso: cada grupo define quais empresas seus membros enxergam.</p>
        </div>
        {isAdmin && <button className="btn btn-primary" onClick={abrirNovo}><i className="ti ti-plus" /> Novo grupo</button>}
      </div>

      {loading ? <div className="center-loader"><div className="spinner" /></div>
        : lista.length === 0 ? <div className="empty-state"><i className="ti ti-users-group" /><p>Nenhum grupo. {isAdmin ? 'Crie um para restringir o acesso por empresa.' : 'Peça a um administrador para criar.'}</p></div>
          : (
            <div className="card" style={{ padding: 0 }}>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>Nome</th><th>Descrição</th><th>Empresas</th><th>Membros</th><th>Supervisor</th>{isAdmin && <th style={{ width: 90 }}></th>}</tr></thead>
                  <tbody>
                    {lista.map(g => (
                      <tr key={g.id}>
                        <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{g.nome}</td>
                        <td style={{ color: 'var(--text-3)' }}>{g.descricao || '—'}</td>
                        <td><span className="badge badge-neutral">{g.qtd_empresas}</span></td>
                        <td><span className="badge badge-neutral">{g.qtd_membros}</span></td>
                        <td style={{ color: 'var(--text-3)' }}>{g.supervisor_nome || '—'}</td>
                        {isAdmin && (
                          <td>
                            <div style={{ display: 'flex', gap: 4 }}>
                              <button className="btn btn-icon" title="Editar" onClick={() => abrirEdit(g.id)}><i className="ti ti-pencil" /></button>
                              <button className="btn btn-icon" title="Excluir" onClick={() => excluir(g.id)}><i className="ti ti-trash" /></button>
                            </div>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 680, maxWidth: '96%' }}>
            <div className="modal-header">
              <h2>{editId ? 'Editar grupo' : 'Novo grupo'}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div className="field"><label>Nome</label><input value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} required /></div>
                <div className="field"><label>Descrição</label><input value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} placeholder="opcional" /></div>
                <div className="field"><label>Supervisor do grupo</label><Dropdown value={form.supervisor_id} onChange={v => setForm(f => ({ ...f, supervisor_id: v }))} options={supOpts} /></div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div className="field">
                    <label>Empresas do grupo ({form.empresa_ids.length})</label>
                    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', maxHeight: 200, overflowY: 'auto', padding: 8 }}>
                      {empresas.length === 0 ? <p style={{ fontSize: 12, color: 'var(--text-4)' }}>Nenhuma empresa.</p> : empresas.map(e => (
                        <label key={e.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '3px 0', cursor: 'pointer' }}>
                          <input type="checkbox" checked={form.empresa_ids.includes(e.id)} onChange={() => toggle('empresa_ids', e.id)} />
                          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{e.razao_social}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                  <div className="field">
                    <label>Membros ({form.user_ids.length})</label>
                    <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', maxHeight: 200, overflowY: 'auto', padding: 8 }}>
                      {users.map(u => (
                        <label key={u.id} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, padding: '3px 0', cursor: 'pointer', opacity: u.id === form.supervisor_id ? 0.5 : 1 }}>
                          <input type="checkbox" checked={form.user_ids.includes(u.id) || u.id === form.supervisor_id} disabled={u.id === form.supervisor_id} onChange={() => toggle('user_ids', u.id)} />
                          <span>{u.full_name} {u.id === form.supervisor_id && '(supervisor)'}</span>
                        </label>
                      ))}
                    </div>
                  </div>
                </div>
                <p style={{ fontSize: 11.5, color: 'var(--text-4)', marginTop: 4 }}>Admins e supervisores enxergam todas as empresas. Usuários comuns só veem as empresas dos grupos a que pertencem.</p>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Salvando…' : 'Salvar grupo'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
