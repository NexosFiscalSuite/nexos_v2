import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useRefresh } from '../context/RefreshContext'
import { useCompetencia } from '../context/CompetenciaContext'

const fmt = n => (n || 0).toLocaleString('pt-BR')
const fmtBRL = n => 'R$ ' + (n || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })
const pct = n => `${Math.round(n || 0)}%`

// Mini-métrica do bloco branco (estilo funil).
function Kpi({ valor, label, icon, cor = 'var(--text-1)', sep }) {
  return (
    <div style={{ padding: '0 18px', borderLeft: sep ? '1px solid var(--border-2)' : 'none', textAlign: 'center' }}>
      <div style={{ fontSize: 11, color: 'var(--text-4)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, marginBottom: 6 }}><i className={`ti ${icon}`} />{label}</div>
      <div style={{ fontSize: 26, fontWeight: 800, color: cor, letterSpacing: '-0.5px', fontFamily: 'var(--font-display)' }}>{valor}</div>
    </div>
  )
}

// Um indicador estratégico dentro do resumo expandido da empresa.
function Indicador({ icon, cor, bg, titulo, children }) {
  return (
    <div style={{ background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 'var(--radius)', padding: '14px 16px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
        <span style={{ width: 26, height: 26, borderRadius: 7, background: bg, color: cor, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 15 }}><i className={`ti ${icon}`} /></span>
        <span style={{ fontSize: 12, color: 'var(--text-3)', fontWeight: 500 }}>{titulo}</span>
      </div>
      {children}
    </div>
  )
}

function LinhaEmpresa({ e, aberto, onToggle }) {
  const totalDiv = (e.divergencias_fornecedor || 0) + (e.antecipacoes || 0)
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer', background: aberto ? 'var(--surface-2)' : undefined }}>
        <td style={{ textAlign: 'center', color: 'var(--text-4)', width: 40 }}>
          <i className={`ti ti-chevron-${aberto ? 'down' : 'right'}`} />
        </td>
        <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{e.razao_social}</td>
        <td style={{ textAlign: 'center' }}>
          {e.divergencias_fornecedor > 0 && <span className="badge badge-error" style={{ fontSize: 10, marginRight: 4 }}><i className="ti ti-alert-octagon" style={{ marginRight: 3 }} />{e.divergencias_fornecedor}</span>}
          {e.antecipacoes > 0 && <span className="badge badge-warn" style={{ fontSize: 10 }}><i className="ti ti-receipt-tax" style={{ marginRight: 3 }} />{e.antecipacoes}</span>}
          {totalDiv === 0 && <span style={{ color: 'var(--text-4)', fontSize: 12 }}>—</span>}
        </td>
        <td style={{ textAlign: 'center' }}>
          {e.gargalos_cfop > 0
            ? <span className="badge badge-warn" style={{ fontSize: 10 }}><i className="ti ti-alert-triangle" /> {e.gargalos_cfop}</span>
            : <span style={{ color: 'var(--text-4)', fontSize: 12 }}>—</span>}
        </td>
        <td style={{ textAlign: 'right', color: 'var(--text-2)' }}>{fmt(e.volume_mes)}</td>
        <td className="mono" style={{ textAlign: 'right', fontWeight: 600, color: e.impacto_financeiro > 0 ? 'var(--err-text)' : 'var(--text-4)' }}>
          {fmtBRL(e.impacto_financeiro)}
        </td>
      </tr>
      {aberto && (
        <tr>
          <td />
          <td colSpan={5} style={{ paddingTop: 4, paddingBottom: 16 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
              <Indicador icon="ti-alert-octagon" cor="var(--err-text)" bg="var(--err-bg)" titulo="Divergências ST">
                <div style={{ fontSize: 13 }}>
                  <div style={{ color: 'var(--err-text)', fontWeight: 600 }}><i className="ti ti-alert-octagon" style={{ marginRight: 5 }} />{e.divergencias_fornecedor} Erro(s) do Fornecedor</div>
                  <div style={{ color: 'var(--warn-text)', fontWeight: 600, marginTop: 2 }}><i className="ti ti-receipt-tax" style={{ marginRight: 5 }} />{e.antecipacoes} Antecipação(ões)</div>
                </div>
              </Indicador>
              <Indicador icon="ti-arrows-exchange" cor="var(--warn-text)" bg="var(--warn-bg)" titulo="Gargalos / Alertas">
                <div style={{ fontSize: 20, fontWeight: 700, color: e.gargalos_cfop > 0 ? 'var(--warn-text)' : 'var(--text-3)' }}>{fmt(e.gargalos_cfop)}</div>
                <div style={{ fontSize: 11, color: 'var(--text-4)' }}>notas sem De/Para de CFOP</div>
              </Indicador>
              <Indicador icon="ti-files" cor="var(--primary-text)" bg="var(--primary-lt)" titulo="Volume do Mês">
                <div style={{ fontSize: 20, fontWeight: 700, color: 'var(--text-1)' }}>{fmt(e.volume_mes)}</div>
                <div style={{ fontSize: 11, color: 'var(--text-4)' }}>XMLs importados</div>
              </Indicador>
              <Indicador icon="ti-cash" cor="var(--err-text)" bg="var(--err-bg)" titulo="Impacto Financeiro">
                <div className="mono" style={{ fontSize: 18, fontWeight: 700, color: e.impacto_financeiro > 0 ? 'var(--err-text)' : 'var(--text-3)' }}>{fmtBRL(e.impacto_financeiro)}</div>
                <div style={{ fontSize: 11, color: 'var(--text-4)' }}>soma das divergências</div>
              </Indicador>
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

export default function Dashboard() {
  const { dataVersion } = useRefresh()
  const { ano, mes } = useCompetencia()
  const navigate = useNavigate()
  const [empresas, setEmpresas] = useState([])
  const [loading, setLoading] = useState(true)
  const [aberto, setAberto] = useState(null)

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setEmpresas(await api.dashSaude(ano, mes) || []) }
    catch { setEmpresas([]) }
    finally { setLoading(false) }
  }, [ano, mes, dataVersion])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setAberto(null) }, [ano, mes])

  const comAlerta = empresas.filter(e => (e.divergencias_fornecedor + e.antecipacoes + e.gargalos_cfop) > 0).length
  const totalEmpresas = empresas.length
  const notasProc = empresas.reduce((s, e) => s + (e.volume_mes || 0), 0)
  const impactoTotal = empresas.reduce((s, e) => s + (e.impacto_financeiro || 0), 0)
  const comGargalo = empresas.filter(e => e.gargalos_cfop > 0).length
  const comDiverg = empresas.filter(e => (e.divergencias_fornecedor + e.antecipacoes) > 0).length

  return (
    <div>
      <div className="page-header">
        <div>
          <h1 className="page-title">Saúde dos Clientes</h1>
          <p className="page-breadcrumb">{mes}/{ano} · {empresas.length} empresa(s) · {comAlerta} com pendência(s)</p>
        </div>
      </div>

      {!loading && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(230px,1fr) minmax(360px,1.8fr) minmax(230px,1fr)', gap: 16, marginBottom: 22 }}>
          {/* Bloco 1 — Destaque financeiro (escuro premium: gradiente navy da logo,
              borda translúcida = vidro polido, sombra própria p/ saltar da tela) */}
          <div className="hover-lift" style={{
            background: 'linear-gradient(140deg, #1E3A5F 0%, #0F1F38 100%)',
            border: '1px solid rgba(255,255,255,0.10)', borderRadius: 'var(--radius-lg)',
            padding: '22px 24px', position: 'relative', overflow: 'hidden',
            boxShadow: '0 14px 34px rgba(15,31,56,0.32)',
          }}>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,0.55)', textTransform: 'uppercase', letterSpacing: '0.6px', fontWeight: 600 }}>Impacto Total</div>
            <div style={{ fontSize: 40, fontWeight: 700, marginTop: 12, letterSpacing: '-1.8px', color: '#FFFFFF', lineHeight: 1 }}>{fmtBRL(impactoTotal)}</div>
            <div style={{ fontSize: 12.5, color: 'rgba(255,255,255,0.65)', marginTop: 12, lineHeight: 1.5 }}>Soma das divergências e antecipações do escritório em {mes}/{ano}.</div>
            <div style={{ position: 'absolute', right: -36, bottom: -36, width: 132, height: 132, borderRadius: '50%', background: 'rgba(130,223,111,0.14)' }} />
          </div>

          {/* Bloco 2 — KPIs (funil) */}
          <div className="hover-lift" style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '20px 8px', display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', alignItems: 'center' }}>
            <Kpi valor={fmt(totalEmpresas)} label="Empresas" icon="ti-building-store" />
            <Kpi valor={fmt(notasProc)} label="Notas processadas" icon="ti-files" sep />
            <Kpi valor={pct(totalEmpresas ? comGargalo / totalEmpresas * 100 : 0)} label="Com gargalos" icon="ti-arrows-exchange" cor="var(--warn-text)" sep />
            <Kpi valor={pct(totalEmpresas ? comDiverg / totalEmpresas * 100 : 0)} label="Com divergências" icon="ti-alert-octagon" cor="var(--err-text)" sep />
          </div>

          {/* Bloco 3 — Dica/atalho (flat branco, accent verde) */}
          <div className="hover-lift" onClick={() => navigate('/cfop-regras')} style={{ background: 'var(--surface)', border: '1px solid var(--hairline)', borderRadius: 'var(--radius-lg)', padding: '20px', cursor: 'pointer', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
            <div>
              <span style={{ width: 32, height: 32, borderRadius: '50%', background: 'var(--primary-lt)', color: 'var(--primary-text)', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 17 }}><i className="ti ti-bulb" /></span>
              <div style={{ fontWeight: 600, marginTop: 12, fontSize: 14, color: 'var(--ink)', letterSpacing: '-0.2px' }}>Dica do Sistema</div>
              <div style={{ fontSize: 12.5, color: 'var(--text-3)', marginTop: 5, lineHeight: 1.5 }}>Configure seus CFOPs globais para destravar notas retroativamente.</div>
            </div>
            <div style={{ color: 'var(--primary-text)', fontSize: 12.5, fontWeight: 600, marginTop: 16, display: 'flex', alignItems: 'center', gap: 5 }}>Ir para De/Para CFOP <i className="ti ti-arrow-right" /></div>
          </div>
        </div>
      )}

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : empresas.length === 0 ? (
        <div className="empty-state">
          <i className="ti ti-building-store" />
          <p className="empty-title">Nenhuma empresa cadastrada</p>
          <p className="empty-subtitle">Cadastre empresas e importe XMLs para acompanhar a saúde fiscal de cada cliente na competência.</p>
        </div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr>
                  <th></th><th>Empresa</th>
                  <th style={{ textAlign: 'center' }}>Divergências ST</th>
                  <th style={{ textAlign: 'center' }}>Gargalos</th>
                  <th style={{ textAlign: 'right' }}>Volume</th>
                  <th style={{ textAlign: 'right' }}>Impacto (R$)</th>
                </tr>
              </thead>
              <tbody>
                {empresas.map(e => (
                  <LinhaEmpresa key={e.empresa_id} e={e} aberto={aberto === e.empresa_id}
                    onToggle={() => setAberto(aberto === e.empresa_id ? null : e.empresa_id)} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
