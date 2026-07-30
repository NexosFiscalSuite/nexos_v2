import { useState, useEffect, useCallback, useRef } from 'react'
import Dropdown from '../components/Dropdown'
import { api, getUser } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

const novoForm = () => ({ nome: '', descricao: '', empresa_ids: [], user_ids: [], supervisor_id: '' })

// Seleção por chips (como no exemplo do escritório): o retângulo mostra só as
// tags removíveis (quebrando linha); adicionar é um campo PRÓPRIO logo abaixo,
// com sugestões clicáveis — sem rolagem lateral.
function ChipsPicker({ itens, selecionados, fixos = [], onAdd, onRemove, placeholder, vazio }) {
  const [busca, setBusca] = useState('')
  const [aberto, setAberto] = useState(false)
  const ref = useRef()

  useEffect(() => {
    const h = (e) => { if (ref.current && !ref.current.contains(e.target)) setAberto(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const porId = new Map(itens.map(i => [i.id, i]))
  const disponiveis = itens.filter(i =>
    !selecionados.includes(i.id) && !fixos.some(f => f.id === i.id) &&
    (!busca || i.label.toLowerCase().includes(busca.toLowerCase()))
  )

  return (
    <div>
      <div className="chips-box">
        {fixos.map(f => (
          <span key={f.id} className="chip-tag chip-fixa" title={f.hint}>
            <span>{f.label}</span>
          </span>
        ))}
        {selecionados.map(id => (
          <span key={id} className="chip-tag" title={porId.get(id)?.label}>
            <span>{porId.get(id)?.label || '…'}</span>
            <button type="button" aria-label="Remover" onClick={() => onRemove(id)}>
              <i className="ti ti-x" />
            </button>
          </span>
        ))}
        {fixos.length + selecionados.length === 0 && <span className="chips-vazio">{vazio}</span>}
      </div>
      <div ref={ref} style={{ position: 'relative', marginTop: 8 }}>
        <input
          value={busca}
          placeholder={placeholder}
          onChange={e => { setBusca(e.target.value); setAberto(true) }}
          onFocus={() => setAberto(true)}
        />
        {aberto && (
          <div className="chips-sugestoes">
            {disponiveis.length === 0
              ? <div className="cs-vazio">{busca ? 'Nada encontrado.' : 'Todos já estão no grupo.'}</div>
              : disponiveis.map(i => (
                <div key={i.id} onClick={() => { onAdd(i.id); setBusca('') }}>{i.label}</div>
              ))}
          </div>
        )}
      </div>
    </div>
  )
}

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

  const add = (key, id) => setForm(f => f[key].includes(id) ? f : { ...f, [key]: [...f[key], id] })
  const remove = (key, id) => setForm(f => ({ ...f, [key]: f[key].filter(x => x !== id) }))

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

  // Espelha o backend: só ADMIN enxerga todas as empresas — por isso admin não
  // entra em grupo. O campo Supervisor sugere apenas supervisores; o de membros
  // aceita supervisores e usuários comuns (ambos dependem do grupo para ver as
  // empresas). Quem já está no grupo (dado legado) continua aparecendo.
  const supOpts = [
    { value: '', label: '— sem supervisor —' },
    ...users.filter(u => u.role === 'supervisor' || u.id === form.supervisor_id)
      .map(u => ({ value: u.id, label: u.full_name })),
  ]
  const membroOpts = users.filter(u => u.role !== 'admin' || form.user_ids.includes(u.id))

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
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 860, maxWidth: '96%' }}>
            <div className="modal-header">
              <h2>{editId ? 'Editar grupo' : 'Novo grupo'}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div className="field"><label>Nome</label><input value={form.nome} onChange={e => setForm(f => ({ ...f, nome: e.target.value }))} required /></div>
                  <div className="field"><label>Supervisor (responsável) do grupo</label><Dropdown value={form.supervisor_id} onChange={v => setForm(f => ({ ...f, supervisor_id: v }))} options={supOpts} /></div>
                </div>
                <div className="field"><label>Descrição</label><input value={form.descricao} onChange={e => setForm(f => ({ ...f, descricao: e.target.value }))} placeholder="opcional" /></div>

                <div className="field">
                  <label>Empresas do grupo ({form.empresa_ids.length})</label>
                  <ChipsPicker
                    itens={empresas.map(e => ({ id: e.id, label: e.razao_social }))}
                    selecionados={form.empresa_ids}
                    onAdd={id => add('empresa_ids', id)}
                    onRemove={id => remove('empresa_ids', id)}
                    placeholder="Adicionar uma empresa…"
                    vazio="Nenhuma empresa no grupo ainda."
                  />
                </div>

                <div className="field">
                  <label>Membros com acesso ({form.user_ids.length})</label>
                  <ChipsPicker
                    itens={membroOpts.map(u => ({ id: u.id, label: u.full_name }))}
                    selecionados={form.user_ids.filter(id => id !== form.supervisor_id)}
                    fixos={users.filter(u => u.id === form.supervisor_id).map(u => ({
                      id: u.id, label: `${u.full_name} (supervisor)`,
                      hint: 'O supervisor já tem acesso — definido no campo acima',
                    }))}
                    onAdd={id => add('user_ids', id)}
                    onRemove={id => remove('user_ids', id)}
                    placeholder="Adicionar um usuário…"
                    vazio="Nenhum membro no grupo ainda."
                  />
                </div>
                <p style={{ fontSize: 11.5, color: 'var(--text-4)', marginTop: 4 }}>Somente admins enxergam todas as empresas. Supervisores e usuários comuns veem apenas as empresas dos grupos em que estão.</p>
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
