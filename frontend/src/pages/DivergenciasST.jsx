import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const PAGE_SIZE = 50
const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const pct = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`)

// O rombo é (XML − calculado): negativo = imposto a recolher (XML a menor).
function corRombo(v) {
  const n = Number(v || 0)
  if (n < -0.004) return 'var(--err-text)'     // a recolher (falta imposto)
  if (n > 0.004) return 'var(--info-text)'     // retenção a maior (ressarcir)
  return 'var(--text-3)'
}

export default function DivergenciasST() {
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { toasts, toast } = useToast()

  const [data, setData] = useState({ total: 0, itens: [], page: 1, page_size: PAGE_SIZE })
  const [loading, setLoading] = useState(false)
  const [page, setPage] = useState(1)
  const [detalhe, setDetalhe] = useState(null)   // linha cujo modal de memória está aberto

  const carregar = useCallback(async () => {
    if (!selectedEmpresa) { setData({ total: 0, itens: [], page: 1, page_size: PAGE_SIZE }); return }
    setLoading(true)
    try {
      const res = await api.stDivergencias(selectedEmpresa.id, {
        data_inicio: `${ano}-${mes}-01`,
        data_fim: `${ano}-${mes}-31`,
        page,
        page_size: PAGE_SIZE,
      })
      setData(res)
    } catch (e) {
      toast(e.message, 'error')
      setData({ total: 0, itens: [], page: 1, page_size: PAGE_SIZE })
    } finally {
      setLoading(false)
    }
  }, [selectedEmpresa, ano, mes, page])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setPage(1) }, [selectedEmpresa, ano, mes])

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE))

  if (!selectedEmpresa) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Divergências de ICMS-ST</h1></div>
        <div className="empty-state"><i className="ti ti-building-store" /><p>Selecione uma empresa no topo.</p></div>
      </div>
    )
  }

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Divergências de ICMS-ST</h1>
          <p className="page-breadcrumb">{selectedEmpresa.razao_social} · {mes}/{ano} · {data.total} divergência(s)</p>
        </div>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : data.itens.length === 0 ? (
        <div className="empty-state"><i className="ti ti-circle-check" /><p>Nenhuma divergência de ST nesta competência. 🎉</p></div>
      ) : (
        <>
          <div className="card" style={{ padding: 0 }}>
            <div className="tbl-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>NF-e / Item</th>
                    <th>Fornecedor</th>
                    <th>UF</th>
                    <th>CST</th>
                    <th style={{ textAlign: 'right' }}>ICMS-ST XML</th>
                    <th style={{ textAlign: 'right' }}>ICMS-ST Calculado</th>
                    <th style={{ textAlign: 'right' }}>Rombo</th>
                    <th>Erro</th>
                    <th style={{ width: 44 }} />
                  </tr>
                </thead>
                <tbody>
                  {data.itens.map((d, i) => (
                    <tr key={`${d.chave_acesso}-${d.numero_item}-${i}`}>
                      <td className="mono">{d.numero_nota || '—'} <span style={{ color: 'var(--text-4)' }}>/ item {d.numero_item}</span></td>
                      <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={`${d.fornecedor || ''} · ${d.cnpj_emit || ''}`}>
                        {d.fornecedor || '—'}
                        <div style={{ fontSize: 11, color: 'var(--text-4)' }} className="mono">{d.cnpj_emit}</div>
                      </td>
                      <td className="mono">{d.uf_origem}→{d.uf_destino}</td>
                      <td className="mono">{d.cst_csosn || '—'}</td>
                      <td className="mono" style={{ textAlign: 'right' }}>{brl(d.vicms_st_xml)}</td>
                      <td className="mono" style={{ textAlign: 'right' }}>{brl(d.vicms_st_calculado)}</td>
                      <td className="mono" style={{ textAlign: 'right', fontWeight: 600, color: corRombo(d.divergencia) }}>
                        {brl(d.divergencia)}
                      </td>
                      <td><span className="badge badge-error" style={{ fontSize: 10 }}>{(d.codigo_erro || '').split(',')[0] || '—'}</span></td>
                      <td>
                        <button className="btn btn-icon" title="Memória de cálculo" onClick={() => setDetalhe(d)}>
                          <i className="ti ti-calculator" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8, marginTop: 14 }}>
            <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><i className="ti ti-chevron-left" /></button>
            <span style={{ fontSize: 13 }}>{page} / {totalPages}</span>
            <button className="btn btn-ghost btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}><i className="ti ti-chevron-right" /></button>
          </div>
        </>
      )}

      {detalhe && <MemoriaModal d={detalhe} onClose={() => setDetalhe(null)} />}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Modal da Verdade: desempacota o JSON `memoria` na jornada matemática do motor.
// ─────────────────────────────────────────────────────────────────────────────
function MemoriaModal({ d, onClose }) {
  const m = d.memoria || {}
  const ajustada = m.mva_foi_ajustada
  const temFcp = Number(m.fcp_st_debito || 0) > 0

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 560, maxWidth: '96%' }}>
        <div className="modal-header">
          <h2><i className="ti ti-calculator" style={{ marginRight: 8 }} />Memória de Cálculo do ST</h2>
          <button className="btn btn-icon" onClick={onClose}><i className="ti ti-x" /></button>
        </div>

        <div className="modal-body">
          {/* Cabeçalho: declarado × calculado × rombo */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 18 }}>
            <Cartao titulo="ICMS-ST no XML" valor={brl(d.vicms_st_xml)} />
            <Cartao titulo="Calculado pelo motor" valor={brl(d.vicms_st_calculado)} destaque />
            <Cartao titulo="Rombo" valor={brl(d.divergencia)} cor={corRombo(d.divergencia)} />
          </div>

          <div className="section-label" style={{ marginBottom: 10 }}>A jornada do cálculo</div>

          {/* A trilha do ICMS-ST */}
          <Passo n="1" titulo="Operação" sub={`${d.uf_origem} → ${d.uf_destino} · regime ${m.regime || '—'}`}
            valor={`Alq. inter ${pct(m.alq_inter)} · interna ${pct(m.alq_intra)}`} />
          <Passo n="2" titulo="MVA"
            sub={ajustada ? 'Ajustada (operação interestadual, não-Simples)' : `Original — ${m.motivo_nao_ajuste || 'sem ajuste'}`}
            valor={<><span style={{ color: 'var(--text-4)' }}>{pct(m.mva_original)}</span> <i className="ti ti-arrow-right" style={{ fontSize: 12 }} /> <b>{pct(m.mva_aplicada)}</b></>}
            badge={ajustada ? { txt: 'Ajustada', cls: 'badge-info' } : { txt: 'Original', cls: 'badge-ok' }} />
          <Passo n="3" titulo="Base de Cálculo do ST" sub="custo + frete rateado × (1 + MVA)" valor={brl(m.base_st_calculada)} />
          <Passo n="4" titulo="Débito do ST" sub={`base × alíquota interna (${pct(m.alq_intra)})`} valor={brl(m.icms_st_debito)} />
          <Passo n="5" titulo="(−) Dedução ICMS Próprio" sub={`dedução ${m.deducao_tipo || '—'}`} valor={`− ${brl(m.deducao_aplicada)}`} negativo />
          <Passo n="=" titulo="ICMS-ST devido" valor={brl(m.icms_st_calculado)} final />

          {/* A trilha paralela do FCP-ST */}
          {temFcp && (
            <>
              <div className="section-label" style={{ margin: '18px 0 10px' }}>FCP-ST (trilha paralela)</div>
              <Passo n="A" titulo="Débito FCP-ST" valor={brl(m.fcp_st_debito)} />
              <Passo n="B" titulo="(−) FCP próprio (não-cumulatividade)" valor={`− ${brl(m.fcp_st_deducao)}`} negativo />
              <Passo n="=" titulo="FCP-ST devido" valor={brl(m.fcp_st_calculado)} final />
            </>
          )}
        </div>

        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Fechar</button>
        </div>
      </div>
    </div>
  )
}

function Cartao({ titulo, valor, destaque, cor }) {
  return (
    <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: '10px 12px', border: destaque ? '1px solid var(--primary)' : '1px solid var(--border)' }}>
      <div style={{ fontSize: 11, color: 'var(--text-4)', marginBottom: 4 }}>{titulo}</div>
      <div className="mono" style={{ fontSize: 15, fontWeight: 600, color: cor || 'var(--text-1)' }}>{valor}</div>
    </div>
  )
}

function Passo({ n, titulo, sub, valor, badge, negativo, final }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px', marginBottom: 6,
      borderRadius: 'var(--radius)',
      background: final ? 'var(--primary-lt)' : 'transparent',
      border: final ? '1px solid var(--primary)' : '1px solid var(--border)',
    }}>
      <div style={{
        width: 26, height: 26, borderRadius: '50%', flexShrink: 0,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        background: final ? 'var(--primary)' : 'var(--surface-2)',
        color: final ? '#fff' : 'var(--text-3)', fontSize: 13, fontWeight: 700,
      }}>{n}</div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, display: 'flex', alignItems: 'center', gap: 8 }}>
          {titulo}
          {badge && <span className={`badge ${badge.cls}`} style={{ fontSize: 10 }}>{badge.txt}</span>}
        </div>
        {sub && <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{sub}</div>}
      </div>
      <div className="mono" style={{
        fontSize: final ? 16 : 14, fontWeight: final ? 700 : 500, whiteSpace: 'nowrap',
        color: negativo ? 'var(--err-text)' : (final ? 'var(--primary-text)' : 'var(--text-1)'),
      }}>{valor}</div>
    </div>
  )
}
