import { useState, useEffect, useCallback, useMemo, useRef, Fragment } from 'react'
import { api, saveBlob } from '../api'
import ErroCarga from '../components/ErroCarga'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const pct = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`)
const cnpjFmt = (c) => (c && c.length === 14 ? c.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5') : c || '—')

// Ordem de exibição dos cards + tom visual de cada situação.
const STATUS_INFO = [
  ['SEM_DESTAQUE',           { label: 'Sem destaque',        tone: 'err',  icon: 'ti-file-off',        desc: 'Regime normal sem o grupo IBS/CBS no XML' }],
  ['ALIQUOTA_DIVERGENTE',    { label: 'Alíquota errada',     tone: 'warn', icon: 'ti-percentage',      desc: 'CST 000 fora dos 0,1% (IBS) + 0,9% (CBS) de teste' }],
  ['VALOR_DIVERGENTE',       { label: 'Valor não fecha',     tone: 'warn', icon: 'ti-calculator-off',  desc: 'Alíquota certa, mas base × alíquota ≠ destacado' }],
  ['OK',                     { label: 'Corretos',            tone: 'ok',   icon: 'ti-circle-check',    desc: 'Destaque presente e conferido' }],
  ['TRATAMENTO_DIFERENCIADO',{ label: 'Trat. diferenciado',  tone: 'info', icon: 'ti-scale',           desc: 'CST ≠ 000: isenção, imunidade, alíquota zero, diferimento… — zerado é legítimo' }],
  ['DISPENSADO',             { label: 'Dispensados',         tone: 'info', icon: 'ti-user-check',      desc: 'Emitente do Simples/MEI (CRT 1/4)' }],
]
const TONE = Object.fromEntries(STATUS_INFO)

const badge = (txt, tone = 'info') => (
  <span className="badge" style={{ background: `var(--${tone}-bg)`, color: `var(--${tone}-text)` }}>{txt}</span>
)

const pctCurto = (v) => `${Number(v).toLocaleString('pt-BR', { maximumFractionDigits: 2 })}%`

// Rótulo cinza que nomeia cada linha da célula ("VEIO" / "DEVIDO").
const Rotulo = ({ children }) => (
  <span style={{ color: 'var(--text-4)', fontWeight: 600, fontSize: 9.5, textTransform: 'uppercase', letterSpacing: 0.5 }}>{children}</span>
)

// Confronto IBS + CBS numa célula só: uma linha compacta por tributo —
// "0,10%→0,00% · R$ 0,00" (nominal→efetiva quando o XML traz o gRed), com
// ✓ quando confere com a régua ou "▸ devido" quando não. O detalhamento
// completo (nominal, redução, efetiva, base, devido) vive no balão clicável,
// no mesmo padrão do balão da classificação.
function ConfrontoIbsCbs({ item, conforme }) {
  const [aberto, setAberto] = useState(false)
  const [pos, setPos] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    if (!aberto) return
    const fechar = (e) => { if (!e.target.closest('.balao-classif')) setAberto(false) }
    document.addEventListener('mousedown', fechar)
    return () => document.removeEventListener('mousedown', fechar)
  }, [aberto])

  function alternar(e) {
    e.stopPropagation()
    if (!aberto && ref.current) {
      const r = ref.current.getBoundingClientRect()
      setPos({
        top: Math.min(r.bottom + 6, window.innerHeight - 300),
        left: Math.min(r.left - 120, window.innerWidth - 480),
      })
    }
    setAberto(a => !a)
  }

  const pernas = [
    { nome: 'IBS', pVeio: item.p_ibs, vVeio: item.v_ibs, pEfet: item.p_aliq_efet_ibs,
      pEsp: item.p_ibs_esperado, vEsp: item.v_ibs_esperado },
    { nome: 'CBS', pVeio: item.p_cbs, vVeio: item.v_cbs, pEfet: item.p_aliq_efet_cbs,
      pEsp: item.p_cbs_esperado, vEsp: item.v_cbs_esperado },
  ]
  const celBalao = { padding: '3px 0', whiteSpace: 'nowrap' }
  const cabBalao = { ...celBalao, color: 'var(--text-4)', fontWeight: 600, fontSize: 10.5, textTransform: 'uppercase', letterSpacing: 0.4 }

  return (
    <span className="balao-classif" style={{ position: 'relative' }}>
      <div ref={ref} onClick={alternar} title="Clique para ver o detalhamento"
        style={{ display: 'inline-flex', alignItems: 'center', gap: 7, cursor: 'pointer' }}>
        <div style={{ display: 'inline-grid', gridTemplateColumns: 'auto auto auto', justifyContent: 'end',
                      columnGap: 8, rowGap: 2, alignItems: 'baseline', whiteSpace: 'nowrap', lineHeight: 1.45 }}>
          {pernas.map(p => (
            <Fragment key={p.nome}>
              <Rotulo>{p.nome}</Rotulo>
              <span style={{ fontWeight: 600, fontSize: 12.5, color: conforme ? 'var(--ok-text)' : 'var(--err-text)' }}>
                {p.pEfet != null
                  ? <>{pct(p.pVeio)}<span style={{ opacity: .55, fontWeight: 400 }}>→</span>{pct(p.pEfet)}</>
                  : pct(p.pVeio)}
                {' · '}{brl(p.vVeio)}
              </span>
              <span style={{ color: 'var(--ok-text)', fontSize: 12 }}>
                {conforme ? '✓' : (p.pEsp == null ? '▸ sem régua' : <>▸ {pct(p.pEsp)} · {brl(p.vEsp)}</>)}
              </span>
            </Fragment>
          ))}
        </div>
        <i className="ti ti-info-circle" style={{ fontSize: 12, opacity: .5, flexShrink: 0 }} />
      </div>

      {aberto && pos && (
        <div className="balao-classif" style={{
          position: 'fixed', top: pos.top, left: pos.left, zIndex: 2000, width: 460,
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          boxShadow: '0 10px 30px rgba(0,0,0,.18)', padding: '13px 15px', textAlign: 'left',
        }}>
          <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 8 }}>
            Destaque IBS/CBS — veio no XML × devido pela classificação
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'auto repeat(5, max-content)', columnGap: 13, fontSize: 12 }}>
            <span style={cabBalao} />
            <span style={cabBalao}>Nominal</span>
            <span style={cabBalao}>Redução</span>
            <span style={cabBalao}>Efetiva</span>
            <span style={cabBalao}>Destacado</span>
            <span style={cabBalao}>Devido</span>
            {pernas.map(p => (
              <Fragment key={p.nome}>
                <span style={{ ...celBalao, fontWeight: 700 }}>{p.nome}</span>
                <span style={celBalao}>{pct(p.pVeio)}</span>
                <span style={celBalao}>{item.p_red_aliq != null && p.pEfet != null ? `−${pctCurto(item.p_red_aliq)}` : '—'}</span>
                <span style={celBalao}>{p.pEfet != null ? pct(p.pEfet) : '—'}</span>
                <span style={celBalao}>{brl(p.vVeio)}</span>
                <span style={{ ...celBalao, color: 'var(--ok-text)', fontWeight: 600 }}>
                  {p.pEsp == null ? 'sem régua' : <>{pct(p.pEsp)} · {brl(p.vEsp)}</>}
                </span>
              </Fragment>
            ))}
          </div>
          {item.v_bc_ibs_cbs > 0 && (
            <div style={{ fontSize: 12, color: 'var(--text-2)', marginTop: 8 }}>
              Base de cálculo (vBC): <strong>{brl(item.v_bc_ibs_cbs)}</strong>
            </div>
          )}
          <div style={{ fontSize: 11.5, color: 'var(--text-4)', lineHeight: 1.5, marginTop: 7 }}>
            {(item.p_aliq_efet_ibs != null || item.p_aliq_efet_cbs != null)
              ? 'Com gRed no XML, a alíquota EFETIVA é o que se compara com o devido — a nominal de teste é obrigatória na NF-e (Rejeição 1026).'
              : 'Sem o grupo gRed no XML, a alíquota dos campos pIBS/pCBS é a própria alíquota aplicada.'}
          </div>
        </div>
      )}
    </span>
  )
}

const CONFORMES = ['OK', 'DISPENSADO', 'TRATAMENTO_DIFERENCIADO']

// Balão clicável da classificação: abre no clique com a descrição OFICIAL
// completa e só fecha clicando fora (ou clicando de novo no gatilho).
function BalaoClassificacao({ item }) {
  const [aberto, setAberto] = useState(false)
  const [pos, setPos] = useState(null)
  const ref = useRef(null)

  useEffect(() => {
    if (!aberto) return
    const fechar = (e) => { if (!e.target.closest('.balao-classif')) setAberto(false) }
    document.addEventListener('mousedown', fechar)
    return () => document.removeEventListener('mousedown', fechar)
  }, [aberto])

  function alternar(e) {
    e.stopPropagation()
    if (!aberto && ref.current) {
      const r = ref.current.getBoundingClientRect()
      setPos({
        top: Math.min(r.bottom + 6, window.innerHeight - 180),
        left: Math.min(r.left, window.innerWidth - 400),
      })
    }
    setAberto(a => !a)
  }

  return (
    <span className="balao-classif" style={{ position: 'relative' }}>
      <button ref={ref} onClick={alternar}
        style={{ border: '1px solid var(--border)', background: 'var(--surface-2)', borderRadius: 6,
                 padding: '3px 8px', fontSize: 12, cursor: 'pointer', whiteSpace: 'nowrap',
                 fontFamily: 'inherit', color: 'var(--text-2)' }}>
        <span className="mono">{item.cst || '—'}{item.c_class_trib ? ` · ${item.c_class_trib}` : ''}</span>
        {' '}<i className="ti ti-info-circle" style={{ fontSize: 12, opacity: .55 }} />
      </button>
      {aberto && pos && (
        <div className="balao-classif" style={{
          position: 'fixed', top: pos.top, left: pos.left, zIndex: 2000, width: 380,
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          boxShadow: '0 10px 30px rgba(0,0,0,.18)', padding: '13px 15px', textAlign: 'left',
        }}>
          <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 6 }}>
            CST {item.cst || '—'} · cClassTrib {item.c_class_trib || '—'}
          </div>
          <div style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55 }}>{item.regua_desc}</div>
        </div>
      )}
    </span>
  )
}

// Itens planos → notas (mestre) com seus itens (detalhe expandível).
function agruparPorNota(itens) {
  const mapa = new Map()
  for (const i of itens) {
    if (!mapa.has(i.chave_acesso)) {
      mapa.set(i.chave_acesso, {
        chave: i.chave_acesso, numero: i.numero_nota, emitente: i.emitente,
        cnpj: i.cnpj_emit, data: i.data_emissao, fluxo: i.fluxo,
        itens: [], valor: 0, situacoes: {},
      })
    }
    const g = mapa.get(i.chave_acesso)
    g.itens.push(i)
    g.valor += i.valor_produto || 0
    g.situacoes[i.status] = (g.situacoes[i.status] || 0) + 1
  }
  return [...mapa.values()]
}

export default function VerificacaoIbsCbs() {
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { toasts, toast } = useToast()
  const [tab, setTab] = useState('entrada')   // Entradas (fornecedores) × Saídas (emissão própria)
  const [dados, setDados] = useState(null)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [busy, setBusy] = useState(false)
  const [expandido, setExpandido] = useState(() => new Set())
  // Card clicado no topo: filtra a lista de notas pela situação (null = pendências)
  const [filtroStatus, setFiltroStatus] = useState(null)

  const notasApontadas = useMemo(() => agruparPorNota(dados?.itens || []), [dados])
  const toggle = (chave) => setExpandido(prev => {
    const s = new Set(prev); s.has(chave) ? s.delete(chave) : s.add(chave); return s
  })

  const params = useCallback(() => ({
    empresa_id: selectedEmpresa?.id, ano, mes, fluxo: tab,
  }), [selectedEmpresa, ano, mes, tab])

  useEffect(() => { setExpandido(new Set()); setFiltroStatus(null) }, [selectedEmpresa, ano, mes, tab])
  useEffect(() => { setExpandido(new Set()) }, [filtroStatus])

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try { setDados(await api.ibsCbsVerificacao({ ...params(), status: filtroStatus })) }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [params, filtroStatus])

  useEffect(() => { carregar() }, [carregar])

  // Carta timbrada (PDF) pedindo a correção — por emitente do ranking.
  const [cartaBusy, setCartaBusy] = useState(null)
  async function gerarCarta(cnpj) {
    setCartaBusy(cnpj)
    try {
      const { blob, filename } = await api.ibsCbsCarta({ ...params(), cnpj_emit: cnpj })
      saveBlob(blob, filename)
      toast('Carta gerada — pronta para encaminhar ao cliente.', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setCartaBusy(null) }
  }

  async function reprocessar() {
    if (!confirm('Reler os XMLs armazenados do período para preencher os campos de IBS/CBS? (necessário só para notas importadas antes deste módulo existir)')) return
    setBusy(true)
    try {
      const r = await api.ibsCbsReprocessar(params())
      toast(`${r.notas_reprocessadas} nota(s) reprocessada(s)` + (r.falhas_leitura ? ` · ${r.falhas_leitura} falha(s) de leitura` : ''), 'ok')
      carregar()
    } catch (e) { toast(e.message, 'error') }
    finally { setBusy(false) }
  }

  const resumo = dados?.resumo || {}
  const conforme = dados?.pct_conforme ?? 100

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">IBS/CBS — Ano-teste 2026</h1>
          <p className="page-breadcrumb">
            Destaque obrigatório de IBS 0,1% + CBS 0,9% (EC 132, ADCT art. 125) ·{' '}
            {selectedEmpresa ? selectedEmpresa.razao_social : 'todas as empresas'} · {mes}/{ano}
          </p>
        </div>
        <button className="btn btn-secondary" data-tour="ibscbs-atualizar" disabled={busy} onClick={reprocessar}>
          <i className="ti ti-refresh" /> {busy ? 'Atualizando…' : 'Atualizar consulta (reler XMLs)'}
        </button>
      </div>

      {/* Abas: Entradas = adequação dos FORNECEDORES; Saídas = a emissão da própria empresa */}
      <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3, marginBottom: 16 }}>
        {[['entrada', 'Entradas (fornecedores)', 'ti-arrow-down-left'], ['saida', 'Saídas (emissão própria)', 'ti-arrow-up-right']].map(([v, label, icon]) => (
          <button key={v} onClick={() => setTab(v)} className="btn btn-sm"
            style={{ border: 'none', background: tab === v ? 'var(--surface)' : 'transparent', color: tab === v ? 'var(--text-1)' : 'var(--text-3)', boxShadow: tab === v ? 'var(--shadow-sm)' : 'none' }}>
            <i className={`ti ${icon}`} /> {label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : erro ? (
        <ErroCarga mensagem={erro} onRetry={carregar} />
      ) : (dados?.total_itens || 0) === 0 ? (
        <div className="empty-state">
          <i className="ti ti-flask" />
          <p className="empty-title">Nenhum item para verificar</p>
          <p className="empty-subtitle">Importe XMLs de 2026 desta competência — ou use “Reprocessar XMLs” se as notas foram importadas antes deste módulo.</p>
        </div>
      ) : (
        <>
          {/* Termômetro + cards por situação */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 20 }}>
            <div className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Conformidade</span>
              <span style={{ fontSize: 26, fontWeight: 800, color: conforme >= 90 ? 'var(--ok-text)' : 'var(--err-text)' }}>{conforme}%</span>
              <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{dados.total_itens} item(ns) verificados</span>
            </div>
            {STATUS_INFO.map(([key, info]) => {
              const ativo = filtroStatus === key
              return (
                <div key={key} className="card kpi-click" role="button"
                  title={`${info.desc} — clique para ver essas notas`}
                  onClick={() => setFiltroStatus(f => (f === key ? null : key))}
                  style={{
                    padding: 16, display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
                    boxShadow: ativo ? `inset 0 0 0 2px var(--${info.tone}-text)` : undefined,
                  }}>
                  <span className="kpi-icon" style={{ background: `var(--${info.tone}-bg)`, color: `var(--${info.tone}-text)` }}>
                    <i className={`ti ${info.icon}`} />
                  </span>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                      {info.label}
                      {ativo && <i className="ti ti-filter" style={{ marginLeft: 6, color: `var(--${info.tone}-text)` }} />}
                    </span>
                    <span className="tnum" style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.3px', color: `var(--${info.tone}-text)` }}>{resumo[key]?.itens || 0}</span>
                    <span className="tnum" style={{ fontSize: 11, color: 'var(--text-4)' }}>{brl(resumo[key]?.valor)}</span>
                  </div>
                </div>
              )
            })}
          </div>

          {/* Ranking de emitentes com problema */}
          {(dados.ranking_emitentes || []).length > 0 && (
            <div className="card" style={{ padding: 0, marginBottom: 20 }}>
              <div style={{ padding: '12px 16px', fontWeight: 600, borderBottom: '1px solid var(--border-2)' }}>
                Emitentes com pendência — priorize o contato pelos maiores valores
              </div>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>Emitente</th><th>CNPJ</th><th style={{ textAlign: 'right' }}>Itens</th><th style={{ textAlign: 'right' }}>Valor movimentado</th><th>Situações</th><th /></tr></thead>
                  <tbody>
                    {dados.ranking_emitentes.map(e => (
                      <tr key={e.cnpj}>
                        <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{e.nome || '—'}</td>
                        <td className="mono">{cnpjFmt(e.cnpj)}</td>
                        <td style={{ textAlign: 'right' }}>{e.itens}</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{brl(e.valor)}</td>
                        <td>{Object.entries(e.status).map(([s, n]) => (
                          <span key={s} style={{ marginRight: 6 }}>{badge(`${TONE[s]?.label || s}: ${n}`, TONE[s]?.tone)}</span>
                        ))}</td>
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button className="btn btn-secondary btn-sm" disabled={cartaBusy === e.cnpj}
                            title="Gera a carta timbrada (PDF) solicitando a correção dos itens deste emitente"
                            onClick={() => gerarCarta(e.cnpj)}>
                            <i className={`ti ${cartaBusy === e.cnpj ? 'ti-loader-2' : 'ti-file-type-pdf'}`} />
                            {cartaBusy === e.cnpj ? ' Gerando…' : ' Carta PDF'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Notas: mestre (nota) → detalhe (itens). Sem filtro = pendências;
              com card clicado = notas daquela situação (inclusive corretas). */}
          {(notasApontadas.length > 0 || filtroStatus) && (
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: '12px 16px', fontWeight: 600, borderBottom: '1px solid var(--border-2)', display: 'flex', alignItems: 'center', gap: 10 }}>
                <span>
                  {filtroStatus ? `Notas — ${TONE[filtroStatus]?.label || filtroStatus}` : 'Notas apontadas'} ({notasApontadas.length})
                  <span style={{ fontWeight: 400, color: 'var(--text-4)', fontSize: 12 }}>
                    {' '}· {dados.itens.length}{dados.itens.length >= 500 ? '+' : ''} item(ns) — clique na nota para ver os produtos
                  </span>
                </span>
                {filtroStatus && (
                  <button className="btn btn-ghost btn-sm" style={{ marginLeft: 'auto' }} onClick={() => setFiltroStatus(null)}>
                    <i className="ti ti-filter-off" /> Limpar filtro
                  </button>
                )}
              </div>
              {notasApontadas.length === 0 && (
                <div style={{ padding: 20, fontSize: 13, color: 'var(--text-3)' }}>
                  Nenhuma nota na situação “{TONE[filtroStatus]?.label || filtroStatus}” neste período.
                </div>
              )}
              {notasApontadas.length > 0 && (
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th style={{ width: 34 }} />
                      <th>Emissão</th><th>NF</th><th>Emitente</th>
                      <th>Situações</th>
                      <th style={{ textAlign: 'right' }}>Itens</th>
                      <th style={{ textAlign: 'right' }}>Valor apontado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {notasApontadas.map(n => {
                      const aberto = expandido.has(n.chave)
                      return (
                        <Fragment key={n.chave}>
                          <tr style={{ cursor: 'pointer' }} onClick={() => toggle(n.chave)}>
                            <td><i className={`ti ti-chevron-${aberto ? 'down' : 'right'}`} style={{ color: 'var(--text-4)' }} /></td>
                            <td style={{ whiteSpace: 'nowrap' }}>{(n.data || '').split('-').reverse().join('/')}</td>
                            <td className="mono">{n.numero}</td>
                            <td>
                              <div style={{ fontWeight: 500, color: 'var(--text-1)', maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={n.emitente}>{n.emitente}</div>
                              <div className="mono" style={{ fontSize: 11, color: 'var(--text-4)' }}>{cnpjFmt(n.cnpj)}</div>
                            </td>
                            <td>{Object.entries(n.situacoes).map(([s, q]) => (
                              <span key={s} style={{ marginRight: 6 }}>{badge(`${TONE[s]?.label || s}${q > 1 ? ` ×${q}` : ''}`, TONE[s]?.tone)}</span>
                            ))}</td>
                            <td style={{ textAlign: 'right' }}>{n.itens.length}</td>
                            <td style={{ textAlign: 'right', fontWeight: 600 }}>{brl(n.valor)}</td>
                          </tr>
                          {aberto && (
                            <tr>
                              <td colSpan={7} style={{ padding: 0, background: 'var(--surface-2)' }}>
                                <table className="tbl" style={{ margin: 0 }}>
                                  <thead>
                                    <tr>
                                      <th style={{ width: 46 }}>Item</th>
                                      <th>Produto</th>
                                      <th>Situação</th>
                                      <th>Classificação</th>
                                      <th style={{ textAlign: 'right' }}>Valor</th>
                                      <th style={{ textAlign: 'right' }}>IBS / CBS <span style={{ fontWeight: 400, color: 'var(--text-4)' }}>(veio ▸ devido)</span></th>
                                    </tr>
                                  </thead>
                                  <tbody>
                                    {n.itens.map((i, idx) => (
                                      <tr key={`${i.numero_item}-${idx}`} className="filha">
                                        <td className="mono">{i.numero_item}</td>
                                        <td style={{ maxWidth: 280, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontWeight: 500, color: 'var(--text-1)' }} title={i.descricao}>{i.descricao || '—'}</td>
                                        <td>{badge(TONE[i.status]?.label || i.status, TONE[i.status]?.tone)}</td>
                                        <td><BalaoClassificacao item={i} /></td>
                                        <td style={{ textAlign: 'right' }}>{brl(i.valor_produto)}</td>
                                        <td style={{ textAlign: 'right' }}>
                                          <ConfrontoIbsCbs item={i} conforme={CONFORMES.includes(i.status)} />
                                        </td>
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </td>
                            </tr>
                          )}
                        </Fragment>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
