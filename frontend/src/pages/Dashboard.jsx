import { useEffect, useState, useCallback } from 'react'
import { api } from '../api'
import { useRefresh } from '../context/RefreshContext'

const fmt = n => (n || 0).toLocaleString('pt-BR')
const fmtBRL = n => 'R$ ' + (n || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })
const KIND_LABEL = { import_xml: 'Importação de XML', generate_report: 'Relatório' }
const STATUS_BADGE = { done: 'badge-ok', failed: 'badge-error', running: 'badge-info', queued: 'badge-neutral' }

function StatCard({ icon, label, value, color = 'var(--primary-text)', bg = 'var(--primary-lt)' }) {
  return (
    <div className="stat-card">
      <div className="s-icon" style={{ background: bg, color }}><i className={`ti ${icon}`} /></div>
      <div>
        <div className="s-label">{label}</div>
        <div className="s-val">{value}</div>
      </div>
    </div>
  )
}

export default function Dashboard() {
  const { dataVersion } = useRefresh()
  const [geral, setGeral] = useState({ total_empresas: 0, fiscal_mes: [] })
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)

  const carregar = useCallback(async () => {
    setLoading(true)
    try {
      const [g, j] = await Promise.all([api.geral().catch(() => null), api.jobs().catch(() => [])])
      if (g) setGeral(g)
      setJobs(j || [])
    } finally { setLoading(false) }
  }, [dataVersion])

  useEffect(() => { carregar() }, [carregar])

  if (loading) return <div className="center-loader"><div className="spinner" /><span>Carregando dashboard...</span></div>

  const totNotas = geral.fiscal_mes.reduce((s, m) => s + (m.notas || 0), 0)
  const totValor = geral.fiscal_mes.reduce((s, m) => s + (m.valor || 0), 0)

  return (
    <div>
      <div className="page-header"><h1 className="page-title">Dashboard</h1></div>

      <div className="stat-grid">
        <StatCard icon="ti-building-store" label="Empresas" value={fmt(geral.total_empresas)} color="#D97706" bg="#FEF3C7" />
        <StatCard icon="ti-file-invoice" label="Notas (12 meses)" value={fmt(totNotas)} />
        <StatCard icon="ti-cash" label="Valor (12 meses)" value={fmtBRL(totValor)} color="#0369A1" bg="#DBEAFE" />
        <StatCard icon="ti-clipboard-list" label="Tarefas" value={fmt(jobs.length)} color="#7C3AED" bg="#EDE9FE" />
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 380px', gap: 20, alignItems: 'start' }}>
        <div className="card">
          <div className="card-header">
            <div><div className="card-title">Notas por competência</div><div className="card-sub">Últimos 12 meses</div></div>
          </div>
          {geral.fiscal_mes.length ? (
            <div className="tbl-wrap">
              <table className="tbl">
                <thead><tr><th>Competência</th><th>Notas</th><th>Valor total</th></tr></thead>
                <tbody>
                  {geral.fiscal_mes.map(m => (
                    <tr key={m.mes}>
                      <td className="mono" style={{ fontWeight: 500 }}>{m.mes}</td>
                      <td style={{ fontWeight: 500 }}>{fmt(m.notas)}</td>
                      <td style={{ color: 'var(--primary-text)', fontWeight: 600 }}>{fmtBRL(m.valor)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <div className="empty-state"><i className="ti ti-file-invoice" /><p>Nenhuma nota importada ainda</p></div>}
        </div>

        <div className="card">
          <div className="card-header"><div><div className="card-title">Tarefas recentes</div></div></div>
          {jobs.length === 0 ? (
            <div className="empty-state"><i className="ti ti-history" /><p>Nenhuma tarefa ainda</p></div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {jobs.slice(0, 8).map((j, i) => (
                <div key={j.id} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '11px 0', borderBottom: i < Math.min(jobs.length, 8) - 1 ? '1px solid var(--border-2)' : 'none' }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text-1)' }}>{KIND_LABEL[j.kind] || j.kind}</div>
                    <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 1 }}>{j.processed}/{j.total} · {j.created_at ? new Date(j.created_at).toLocaleString('pt-BR') : ''}</div>
                  </div>
                  <span className={`badge ${STATUS_BADGE[j.status] || 'badge-neutral'}`}>{j.status}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
