import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import Paginacao from '../components/Paginacao'
import { api } from '../api'
import { useToast, ToastContainer } from '../hooks/useToast'

const ACAO_LABEL = {
  'empresa.criar': 'Empresa criada', 'usuario.criar': 'Usuário criado',
  'grupo.criar': 'Grupo criado', 'grupo.editar': 'Grupo editado', 'grupo.excluir': 'Grupo excluído',
  'nota.cancelar_lote': 'Notas canceladas (lote)', 'nota.reativar_lote': 'Notas reativadas (lote)',
  'relatorio.gerar': 'Relatório gerado',
}
const DIAS_OPTS = [
  { value: '7', label: 'Últimos 7 dias' }, { value: '30', label: 'Últimos 30 dias' },
  { value: '90', label: 'Últimos 90 dias' }, { value: '365', label: 'Último ano' },
]
const fmtData = (s) => { try { return new Date(s).toLocaleString('pt-BR') } catch { return s } }
const fmtDetalhe = (d) => !d ? '—' : Object.entries(d).map(([k, v]) => `${k}: ${v}`).join(' · ')

export default function Auditoria() {
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [acoes, setAcoes] = useState([])
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [filtro, setFiltro] = useState({ acao: '', user_id: '', dias: '30' })

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setLista(await api.auditoria(filtro) || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [filtro, toast])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setPage(1) }, [filtro])
  useEffect(() => {
    api.auditAcoes().then(setAcoes).catch(() => {})
    api.listUsers().then(setUsers).catch(() => {})
  }, [])

  const acaoOpts = [{ value: '', label: 'Todas as ações' }, ...acoes.map(a => ({ value: a, label: ACAO_LABEL[a] || a }))]
  const userOpts = [{ value: '', label: 'Todos os usuários' }, ...users.map(u => ({ value: u.id, label: u.full_name }))]
  const set = (k) => (v) => setFiltro(f => ({ ...f, [k]: v }))

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Auditoria</h1>
          <p className="page-breadcrumb">Trilha de ações relevantes do escritório (quem fez o quê e quando).</p>
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="field" style={{ minWidth: 200, margin: 0 }}><label>Período</label><Dropdown value={filtro.dias} onChange={set('dias')} options={DIAS_OPTS} /></div>
          <div className="field" style={{ minWidth: 220, margin: 0 }}><label>Ação</label><Dropdown value={filtro.acao} onChange={set('acao')} options={acaoOpts} /></div>
          <div className="field" style={{ minWidth: 220, margin: 0 }}><label>Usuário</label><Dropdown value={filtro.user_id} onChange={set('user_id')} options={userOpts} /></div>
          <button className="btn btn-ghost" onClick={carregar}><i className="ti ti-refresh" /> Atualizar</button>
        </div>
      </div>

      {loading ? <div className="center-loader"><div className="spinner" /></div>
        : lista.length === 0 ? <div className="empty-state"><i className="ti ti-history" /><p>Nenhum registro no período/filtro.</p></div>
          : (
            <div className="card" style={{ padding: 0 }}>
              {lista.length >= 200 && (
                <div style={{ padding: '10px 16px', fontSize: 12.5, color: 'var(--text-3)', borderBottom: '1px solid var(--border-2)' }}>
                  Mostrando os 200 registros mais recentes do período — refine o filtro para ver além.
                </div>
              )}
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th style={{ width: 160 }}>Data/Hora</th><th>Usuário</th><th>Ação</th><th>Alvo</th><th>Detalhes</th></tr></thead>
                  <tbody>
                    {lista.slice((page - 1) * 25, page * 25).map(a => (
                      <tr key={a.id}>
                        <td className="mono" style={{ whiteSpace: 'nowrap', fontSize: 12 }}>{fmtData(a.created_at)}</td>
                        <td style={{ color: 'var(--text-1)' }}>{a.user_nome || '—'}</td>
                        <td><span className="badge badge-primary">{ACAO_LABEL[a.acao] || a.acao}</span></td>
                        <td style={{ color: 'var(--text-3)' }}>{a.entidade || '—'}</td>
                        <td style={{ color: 'var(--text-3)', fontSize: 12 }}>{fmtDetalhe(a.detalhe)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <Paginacao page={page} total={lista.length} pageSize={25} onChange={setPage} />
            </div>
          )}
    </div>
  )
}
