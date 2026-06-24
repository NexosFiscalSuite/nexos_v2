import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import { api } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

const ROLE_OPTS = [
  { value: 'user', label: 'Usuário' },
  { value: 'supervisor', label: 'Supervisor' },
  { value: 'admin', label: 'Administrador' },
]
const ROLE_BADGE = { admin: 'badge-admin', supervisor: 'badge-primary', user: 'badge-user' }
const VAZIO = { email: '', full_name: '', password: '', role: 'user' }

export default function Usuarios() {
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(VAZIO)
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setLista(await api.listUsers() || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [toast])

  useEffect(() => { carregar() }, [carregar])

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.createUser(form)
      toast('Usuário criado.', 'ok')
      setModal(false); setForm(VAZIO)
      carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <h1 className="page-title">Usuários</h1>
        <button className="btn btn-primary" onClick={() => setModal(true)}><i className="ti ti-plus" /> Novo usuário</button>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Status</th></tr></thead>
              <tbody>
                {lista.map(u => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{u.full_name}</td>
                    <td className="mono">{u.email}</td>
                    <td><span className={`badge ${ROLE_BADGE[u.role] || 'badge-neutral'}`}>{u.role}</span></td>
                    <td><span className={`badge ${u.is_active ? 'badge-ok' : 'badge-neutral'}`}>{u.is_active ? 'ativo' : 'inativo'}</span></td>
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
              <h2>Novo usuário</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div className="field">
                  <label>Nome completo</label>
                  <input value={form.full_name} onChange={set('full_name')} required />
                </div>
                <div className="field">
                  <label>E-mail</label>
                  <input type="email" value={form.email} onChange={set('email')} required />
                </div>
                <div className="field">
                  <label>Senha</label>
                  <input type="password" value={form.password} onChange={set('password')} minLength={8} required />
                </div>
                <div className="field">
                  <label>Papel</label>
                  <Dropdown value={form.role} onChange={v => setForm(f => ({ ...f, role: v }))} options={ROLE_OPTS} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Salvando…' : 'Criar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
