import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import ErroCarga from '../components/ErroCarga'
import { api } from '../api'
import { useAuth } from '../context/AuthContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const ROLE_OPTS = [
  { value: 'user', label: 'Usuário' },
  { value: 'supervisor', label: 'Supervisor' },
  { value: 'admin', label: 'Administrador' },
]
const ROLE_BADGE = { admin: 'badge-admin', supervisor: 'badge-primary', user: 'badge-user' }
const VAZIO = { email: '', full_name: '', password: '', role: 'user' }

export default function Usuarios() {
  const { user: eu } = useAuth()
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [modal, setModal] = useState(false)
  const [editId, setEditId] = useState(null)   // null = criando; id = editando
  const [form, setForm] = useState(VAZIO)
  const [saving, setSaving] = useState(false)

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try { setLista(await api.listUsers() || []) }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [])

  useEffect(() => { carregar() }, [carregar])

  function abrirNovo() { setEditId(null); setForm(VAZIO); setModal(true) }
  function abrirEdicao(u) {
    setEditId(u.id)
    setForm({ email: u.email, full_name: u.full_name, password: '', role: u.role })
    setModal(true)
  }

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      if (editId) {
        // Senha em branco = mantém a atual (o backend só troca se enviada).
        await api.updateUser(editId, {
          full_name: form.full_name,
          role: form.role,
          ...(form.password ? { password: form.password } : {}),
        })
        toast('Usuário atualizado.', 'ok')
      } else {
        await api.createUser(form)
        toast('Usuário criado.', 'ok')
      }
      setModal(false); setEditId(null); setForm(VAZIO)
      carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  async function alternarAtivo(u) {
    const acao = u.is_active ? 'Inativar' : 'Reativar'
    if (!confirm(`${acao} o usuário ${u.full_name}? ${u.is_active ? 'Ele não conseguirá mais entrar no sistema.' : ''}`)) return
    try {
      await api.updateUser(u.id, { is_active: !u.is_active })
      toast(`Usuário ${u.is_active ? 'inativado' : 'reativado'}.`, 'ok')
      carregar()
    } catch (e) { toast(e.message, 'error') }
  }

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <h1 className="page-title">Usuários</h1>
        <button className="btn btn-primary" onClick={abrirNovo}><i className="ti ti-plus" /> Novo usuário</button>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : erro ? (
        <ErroCarga mensagem={erro} onRetry={carregar} />
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead><tr><th>Nome</th><th>E-mail</th><th>Papel</th><th>Status</th><th></th></tr></thead>
              <tbody>
                {lista.map(u => (
                  <tr key={u.id} style={{ cursor: 'pointer', opacity: u.is_active ? 1 : 0.55 }} onClick={() => abrirEdicao(u)}>
                    <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>
                      {u.full_name}{u.id === eu?.id && <span style={{ color: 'var(--text-4)', fontWeight: 400 }}> (você)</span>}
                    </td>
                    <td className="mono">{u.email}</td>
                    <td><span className={`badge ${ROLE_BADGE[u.role] || 'badge-neutral'}`}>{u.role}</span></td>
                    <td><span className={`badge ${u.is_active ? 'badge-ok' : 'badge-neutral'}`}>{u.is_active ? 'ativo' : 'inativo'}</span></td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button className="btn btn-icon" title="Editar"
                        onClick={ev => { ev.stopPropagation(); abrirEdicao(u) }}>
                        <i className="ti ti-pencil" />
                      </button>
                      {u.id !== eu?.id && (
                        <button className="btn btn-icon" title={u.is_active ? 'Inativar' : 'Reativar'}
                          onClick={ev => { ev.stopPropagation(); alternarAtivo(u) }}>
                          <i className={`ti ${u.is_active ? 'ti-user-off' : 'ti-user-check'}`}
                            style={{ color: u.is_active ? 'var(--err-text)' : 'var(--ok-text)' }} />
                        </button>
                      )}
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
              <h2>{editId ? 'Editar usuário' : 'Novo usuário'}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div className="field">
                  <label>Nome completo</label>
                  <input value={form.full_name} onChange={set('full_name')} required />
                </div>
                <div className="field">
                  <label>E-mail{editId ? ' (não editável)' : ''}</label>
                  <input type="email" value={form.email} onChange={set('email')} required disabled={!!editId} />
                </div>
                <div className="field">
                  <label>{editId ? 'Nova senha (em branco = manter a atual)' : 'Senha'}</label>
                  <input type="password" value={form.password} onChange={set('password')}
                    minLength={8} required={!editId} autoComplete="new-password" />
                </div>
                <div className="field">
                  <label>Papel</label>
                  <Dropdown value={form.role} onChange={v => setForm(f => ({ ...f, role: v }))} options={ROLE_OPTS} />
                </div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Salvando…' : (editId ? 'Salvar' : 'Criar')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
