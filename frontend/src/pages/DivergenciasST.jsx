import { useState, useEffect, useCallback, useMemo } from 'react'
import { api } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const PAGE_SIZE = 200
const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const pct = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`)

// Diferença (XML − calculado): negativo = imposto a recolher (destaque vermelho).
function corDiferenca(v) {
  const n = Number(v || 0)
  if (n < -0.004) return 'var(--err-text)'
  if (n > 0.004) return 'var(--info-text)'
  return 'var(--text-3)'
}

// Selo de AÇÃO: traduz o código de erro na conduta do analista (bater o olho).
//  • Antecipação devida (laranja) → recolher guia local (responsabilidade nossa).
//  • Erro do fornecedor / emissão (vermelho) → cobrar correção de quem emitiu.
//  • A favor do cliente (azul) → ST paga a maior, pleitear estorno.
function seloAcao(item) {
  if (item.status === 'NAO_AUDITAVEL')
    return { txt: 'Não auditável', cls: 'badge-neutral', icon: 'ti-help-circle' }
  const cod = item.codigo_erro || ''
  if (cod.includes('ERRO_111'))
    return { txt: 'Antecipação devida', cls: 'badge-warn', icon: 'ti-clock-dollar' }
  if (cod.includes('ERRO_110'))
    return { txt: 'A favor do cliente', cls: 'badge-info', icon: 'ti-arrow-back-up' }
  if (item.status === 'DIVERGENTE')
    return item.fluxo === 'saida'
      ? { txt: 'Erro de emissão', cls: 'badge-error', icon: 'ti-alert-triangle' }
      : { txt: 'Erro do fornecedor', cls: 'badge-error', icon: 'ti-alert-triangle' }
  return null
}

// Selo DOMINANTE da nota: o de maior prioridade de ação entre os itens, para o
// analista bater o olho na linha-mestre (sem expandir). Erro > antecipação >
// a-favor > não auditável.
const _PRIORIDADE = ['badge-error', 'badge-warn', 'badge-info', 'badge-neutral']
function seloNota(itens) {
  const selos = itens.map(seloAcao).filter(Boolean)
  if (!selos.length) return null
  return selos.sort((a, b) => _PRIORIDADE.indexOf(a.cls) - _PRIORIDADE.indexOf(b.cls))[0]
}

// ── Lógica de agrupamento: itens planos → notas (master) com seus itens (detail) ──
function agruparPorNota(itens) {
  const mapa = new Map()
  for (const it of itens) {
    if (!mapa.has(it.chave_acesso)) {
      mapa.set(it.chave_acesso, {
        chave: it.chave_acesso, numero: it.numero_nota, fornecedor: it.fornecedor,
        cnpj: it.cnpj_emit, ufOrigem: it.uf_origem, ufDestino: it.uf_destino, fluxo: it.fluxo,
        ctes: it.ctes_vinculados || [], itens: [],
        totalIcmsSt: 0, totalDiferenca: 0, divergentes: 0, naoAuditaveis: 0,
      })
    }
    const g = mapa.get(it.chave_acesso)
    g.itens.push(it)
    g.totalIcmsSt += Number(it.vicms_st_calculado || 0)
    g.totalDiferenca += Number(it.diferenca || 0)
    if (it.status === 'DIVERGENTE') g.divergentes += 1
    else if (it.status === 'NAO_AUDITAVEL') g.naoAuditaveis += 1
  }
  return [...mapa.values()]
}

export default function DivergenciasST() {
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { toasts, toast } = useToast()

  const [tab, setTab] = useState('entrada')   // Entradas (tpNF=0) × Saídas (tpNF=1)
  const [data, setData] = useState({ total: 0, itens: [] })
  const [loading, setLoading] = useState(false)
  const [expandido, setExpandido] = useState(() => new Set())
  const [detalhe, setDetalhe] = useState(null)

  const carregar = useCallback(async () => {
    if (!selectedEmpresa) { setData({ total: 0, itens: [] }); return }
    setLoading(true)
    try {
      setData(await api.stDivergencias(selectedEmpresa.id, {
        fluxo: tab, data_inicio: `${ano}-${mes}-01`, data_fim: `${ano}-${mes}-31`, page_size: PAGE_SIZE,
      }))
    } catch (e) {
      toast(e.message, 'error'); setData({ total: 0, itens: [] })
    } finally { setLoading(false) }
  }, [selectedEmpresa, ano, mes, tab])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setExpandido(new Set()) }, [selectedEmpresa, ano, mes, tab])

  const notas = useMemo(() => agruparPorNota(data.itens), [data.itens])
  const toggle = (chave) => setExpandido(prev => {
    const s = new Set(prev); s.has(chave) ? s.delete(chave) : s.add(chave); return s
  })

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
          <p className="page-breadcrumb">{selectedEmpresa.razao_social} · {mes}/{ano} · {notas.length} nota(s) · {data.total} item(ns)</p>
        </div>
      </div>

      {/* Abas: o risco fiscal da Entrada (erro de terceiro) ≠ da Saída (erro próprio) */}
      <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, marginBottom: 16 }}>
        {[['entrada', 'Entradas', 'ti-arrow-down-left'], ['saida', 'Saídas', 'ti-arrow-up-right']].map(([v, label, icon]) => (
          <button key={v} onClick={() => setTab(v)} className="btn btn-sm"
            style={{ border: 'none', background: tab === v ? 'var(--surface)' : 'transparent', color: tab === v ? 'var(--text-1)' : 'var(--text-3)', boxShadow: tab === v ? 'var(--shadow-sm)' : 'none' }}>
            <i className={`ti ${icon}`} /> {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : notas.length === 0 ? (
        <div className="empty-state"><i className="ti ti-circle-check" /><p>Nenhuma divergência de ST nesta competência. 🎉</p></div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="table">
              <thead>
                <tr>
                  <th style={{ width: 34 }} />
                  <th>Fornecedor / NF-e</th>
                  <th>UF</th>
                  <th style={{ textAlign: 'center' }}>CT-e</th>
                  <th style={{ textAlign: 'right' }}>ICMS-ST (total)</th>
                  <th style={{ textAlign: 'right' }}>Diferença (total)</th>
                  <th style={{ textAlign: 'center' }}>Situação</th>
                </tr>
              </thead>
              <tbody>
                {notas.map(nota => {
                  const aberto = expandido.has(nota.chave)
                  return (
                    <FragmentoNota
                      key={nota.chave} nota={nota} aberto={aberto}
                      onToggle={() => toggle(nota.chave)} onMemoria={setDetalhe}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {detalhe && <MemoriaModal d={detalhe} onClose={() => setDetalhe(null)} />}
    </div>
  )
}

// ── Linha-mestre (Nota) + linhas-filhas (itens) quando expandida ──
function FragmentoNota({ nota, aberto, onToggle, onMemoria }) {
  const temCte = nota.ctes.length > 0
  return (
    <>
      <tr onClick={onToggle} style={{ cursor: 'pointer', background: aberto ? 'var(--surface-2)' : undefined }}>
        <td style={{ textAlign: 'center', color: 'var(--text-4)' }}>
          <i className={`ti ti-chevron-${aberto ? 'down' : 'right'}`} />
        </td>
        <td>
          <div style={{ fontWeight: 500 }}>{nota.fornecedor || '—'}</div>
          <div style={{ fontSize: 11, color: 'var(--text-4)' }} className="mono">
            NF-e {nota.numero || '—'} · {nota.cnpj} · {nota.itens.length} item(ns)
          </div>
        </td>
        <td className="mono">{nota.ufOrigem}→{nota.ufDestino}</td>
        <td style={{ textAlign: 'center' }}>
          {temCte
            ? <i className="ti ti-truck" title={`CT-e vinculado(s): ${nota.ctes.join(', ')}`}
                 style={{ color: 'var(--info-text)', fontSize: 17 }} />
            : <span style={{ color: 'var(--text-4)' }}>—</span>}
        </td>
        <td className="mono" style={{ textAlign: 'right' }}>{brl(nota.totalIcmsSt)}</td>
        <td className="mono" style={{ textAlign: 'right', fontWeight: 600, color: corDiferenca(nota.totalDiferenca) }}>
          {brl(nota.totalDiferenca)}
        </td>
        <td style={{ textAlign: 'center' }}>
          {(() => {
            const selo = seloNota(nota.itens)
            return selo && (
              <span className={`badge ${selo.cls}`} style={{ fontSize: 10, marginRight: 6 }}>
                <i className={`ti ${selo.icon}`} style={{ marginRight: 3 }} />{selo.txt}
              </span>
            )
          })()}
          {nota.divergentes > 0 && <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{nota.divergentes} item(ns)</span>}
        </td>
      </tr>

      {aberto && temCte && (
        <tr>
          <td />
          <td colSpan={6} style={{ fontSize: 11, color: 'var(--text-4)', paddingTop: 0 }}>
            <i className="ti ti-truck" style={{ marginRight: 4 }} />Frete agregado dos CT-e: <span className="mono">{nota.ctes.join(', ')}</span>
          </td>
        </tr>
      )}

      {aberto && nota.itens.map(it => {
        const selo = seloAcao(it)
        return (
        <tr key={it.numero_item} style={{ background: 'var(--surface)' }}>
          <td />
          <td style={{ paddingLeft: 28 }}>
            <span className="mono">Item {it.numero_item}</span>
            <span style={{ fontSize: 11, color: 'var(--text-4)', marginLeft: 8 }}>CST {it.cst_csosn || '—'} · modBCST {it.mod_bc_st ?? '—'}</span>
            {selo && (
              <span className={`badge ${selo.cls}`} style={{ fontSize: 10, marginLeft: 8 }}>
                <i className={`ti ${selo.icon}`} style={{ marginRight: 3 }} />{selo.txt}
              </span>
            )}
            {it.status === 'NAO_AUDITAVEL' && it.observacao && (
              <div style={{ fontSize: 11, color: 'var(--warn-text)' }}><i className="ti ti-alert-circle" style={{ marginRight: 4 }} />{it.observacao}</div>
            )}
          </td>
          <td colSpan={2} className="mono" style={{ fontSize: 12, color: 'var(--text-4)' }}>
            XML {brl(it.vicms_st_xml)} → calc {brl(it.vicms_st_calculado)}
          </td>
          <td className="mono" style={{ textAlign: 'right' }}>{brl(it.vicms_st_calculado)}</td>
          <td className="mono" style={{ textAlign: 'right', fontWeight: 500, color: corDiferenca(it.diferenca) }}>{brl(it.diferenca)}</td>
          <td style={{ textAlign: 'center' }}>
            {it.memoria && <button className="btn btn-icon" title="Memória de cálculo" onClick={() => onMemoria(it)}><i className="ti ti-calculator" /></button>}
          </td>
        </tr>
        )
      })}
    </>
  )
}

// ── Modal da Verdade: a jornada matemática do JSON `memoria` ──
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
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 18 }}>
            <Cartao titulo="ICMS-ST no XML" valor={brl(d.vicms_st_xml)} />
            <Cartao titulo="Calculado pelo motor" valor={brl(d.vicms_st_calculado)} destaque />
            <Cartao titulo="Diferença" valor={brl(d.diferenca)} cor={corDiferenca(d.diferenca)} />
          </div>

          <div className="section-label" style={{ marginBottom: 10 }}>A jornada do cálculo</div>
          <Passo n="1" titulo="Operação" sub={`${d.uf_origem} → ${d.uf_destino} · regime ${m.regime || '—'}`}
            valor={`Alq. inter ${pct(m.alq_inter)} · interna ${pct(m.alq_intra)}`} />
          <Passo n="2" titulo="MVA"
            sub={ajustada ? 'Ajustada (interestadual, não-Simples)' : `Original — ${m.motivo_nao_ajuste || 'sem ajuste'}`}
            valor={<><span style={{ color: 'var(--text-4)' }}>{pct(m.mva_original)}</span> <i className="ti ti-arrow-right" style={{ fontSize: 12 }} /> <b>{pct(m.mva_aplicada)}</b></>}
            badge={ajustada ? { txt: 'Ajustada', cls: 'badge-info' } : { txt: 'Original', cls: 'badge-ok' }} />
          <Passo n="3" titulo="Base de Cálculo do ST" sub="custo + frete rateado × (1 + MVA)" valor={brl(m.base_st_calculada)} />
          <Passo n="4" titulo="Débito do ST" sub={`base × alíquota interna (${pct(m.alq_intra)})`} valor={brl(m.icms_st_debito)} />
          <Passo n="5" titulo="(−) Dedução ICMS Próprio" sub={`dedução ${m.deducao_tipo || '—'}`} valor={`− ${brl(m.deducao_aplicada)}`} negativo />
          <Passo n="=" titulo="ICMS-ST devido" valor={brl(m.icms_st_calculado)} final />

          {temFcp && (
            <>
              <div className="section-label" style={{ margin: '18px 0 10px' }}>FCP-ST (trilha paralela)</div>
              <Passo n="A" titulo="Débito FCP-ST" valor={brl(m.fcp_st_debito)} />
              <Passo n="B" titulo="(−) FCP próprio (não-cumulatividade)" valor={`− ${brl(m.fcp_st_deducao)}`} negativo />
              <Passo n="=" titulo="FCP-ST devido" valor={brl(m.fcp_st_calculado)} final />
            </>
          )}
        </div>
        <div className="modal-footer"><button className="btn btn-ghost" onClick={onClose}>Fechar</button></div>
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
      borderRadius: 'var(--radius)', background: final ? 'var(--primary-lt)' : 'transparent',
      border: final ? '1px solid var(--primary)' : '1px solid var(--border)',
    }}>
      <div style={{
        width: 26, height: 26, borderRadius: '50%', flexShrink: 0, display: 'flex',
        alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700,
        background: final ? 'var(--primary)' : 'var(--surface-2)', color: final ? '#fff' : 'var(--text-3)',
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
