import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from '../api'

const fmt = n => (n || 0).toLocaleString('pt-BR')
const fmtBRL = n => 'R$ ' + (n || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })

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

export default function EmpresaDashboard() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [empresa, setEmpresa] = useState(null)
  const [dash, setDash] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let vivo = true
    Promise.all([api.empresa(id).catch(() => null), api.empresaDashboard(id).catch(() => null)])
      .then(([e, d]) => { if (vivo) { setEmpresa(e); setDash(d) } })
      .finally(() => { if (vivo) setLoading(false) })
    return () => { vivo = false }
  }, [id])

  const t = dash?.totais

  return (
    <div>
      <div className="page-header">
        <div>
          <button className="btn btn-ghost btn-sm" style={{ marginBottom: 8 }} onClick={() => navigate('/empresas')}>
            <i className="ti ti-arrow-left" /> Voltar
          </button>
          <h1 className="page-title">{empresa?.razao_social || 'Empresa'}</h1>
          {empresa && <p className="page-breadcrumb mono">{empresa.cnpj}</p>}
        </div>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : !t ? (
        <div className="empty-state"><i className="ti ti-chart-bar" /><p>Sem dados para esta empresa.</p></div>
      ) : (
        <>
          <div className="stat-grid">
            <StatCard icon="ti-file-invoice" label="Notas" value={fmt(t.notas)} />
            <StatCard icon="ti-cash" label="Valor total" value={fmtBRL(t.valor)} color="#0369A1" bg="#DBEAFE" />
            <StatCard icon="ti-arrow-down-left" label="Entradas" value={fmt(t.entradas)} />
            <StatCard icon="ti-arrow-up-right" label="Saídas" value={fmt(t.saidas)} color="#D97706" bg="#FEF3C7" />
            <StatCard icon="ti-briefcase" label="Serviços" value={fmt(t.servicos)} color="#7C3AED" bg="#EDE9FE" />
            <StatCard icon="ti-truck" label="CT-e" value={fmt(t.ctes)} />
            <StatCard icon="ti-ban" label="Canceladas" value={fmt(t.canceladas)} color="var(--err-text)" bg="var(--err-bg)" />
          </div>

          <div className="card" style={{ maxWidth: 520 }}>
            <div className="card-header"><div><div className="card-title">Movimento por competência</div></div></div>
            {(dash.por_mes || []).length === 0 ? (
              <div className="empty-state"><i className="ti ti-file-invoice" /><p>Sem notas importadas.</p></div>
            ) : (
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>Competência</th><th>Notas</th><th>Valor</th></tr></thead>
                  <tbody>
                    {dash.por_mes.map(m => (
                      <tr key={m.mes}>
                        <td className="mono" style={{ fontWeight: 500 }}>{m.mes}</td>
                        <td>{fmt(m.notas)}</td>
                        <td style={{ color: 'var(--primary-text)', fontWeight: 600 }}>{fmtBRL(m.valor)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
