import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import Dropdown from '../components/Dropdown'
import { api, saveBlob } from '../api'
import ErroCarga from '../components/ErroCarga'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const PAGE_SIZE = 200
const cnpjFmt = (c) => (c && c.length === 14 ? c.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5') : c || '—')

// Cards do topo: o dinheiro em jogo por tipo de pendência. Clicar filtra a
// lista (sobre os itens carregados) — mesmo padrão dos cards do IBS/CBS.
const CARDS = [
  { key: 'a_recolher', label: 'ST a menor (cobrar fornecedor)', tone: 'err', icon: 'ti-trending-down', dinheiro: true,
    filtro: it => it.status === 'DIVERGENTE' && Number(it.diferenca) < 0 && !(it.codigo_erro || '').includes('ERRO_111') },
  { key: 'a_favor', label: 'Pago a maior (a favor)', tone: 'info', icon: 'ti-arrow-back-up', dinheiro: true,
    filtro: it => it.status === 'DIVERGENTE' && Number(it.diferenca) > 0 },
  { key: 'antecipacao', label: 'Antecipação devida (guia própria)', tone: 'warn', icon: 'ti-receipt-tax', dinheiro: true,
    filtro: it => (it.codigo_erro || '').includes('ERRO_111') },
  { key: 'nao_auditaveis', label: 'Não auditáveis (pendência)', tone: 'warn', icon: 'ti-help-circle', dinheiro: false,
    filtro: it => it.status === 'NAO_AUDITAVEL' },
]

// Pendência de matriz faltante → deep-link para a aba certa das Matrizes,
// já pré-preenchida (o modal abre pronto para salvar; depois é só reprocessar).
function linkMatriz(item) {
  const cod = item.codigo_erro || ''
  const q = (params) => '/matrizes-fiscais?' + new URLSearchParams(
    Object.entries(params).filter(([, v]) => v)
  ).toString()
  if (cod.includes('ERRO_MVA_NAO_ENCONTRADA'))
    return q({ aba: 'mva', ncm: item.ncm, cest: item.cest, uf_destino: item.uf_destino })
  if (cod.includes('ERRO_ALIQUOTA_NAO_ENCONTRADA'))
    return q({ aba: 'aliquotas', uf_destino: item.uf_destino })
  if (cod.includes('ERRO_ENQUADRAMENTO_NAO_CADASTRADO'))
    return q({ aba: 'enquadramento', ncm: item.ncm, cest: item.cest, uf_destino: item.uf_destino })
  if (cod.includes('ERRO_PROTOCOLO_NAO_AVALIADO'))
    return q({ aba: 'protocolos', uf_origem: item.uf_origem, uf_destino: item.uf_destino })
  return null
}
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
    return { txt: 'Antecipação devida', cls: 'badge-warn', icon: 'ti-receipt-tax' }
  if (cod.includes('ERRO_110'))
    return { txt: 'A favor do cliente', cls: 'badge-info', icon: 'ti-arrow-back-up' }
  if (item.status === 'DIVERGENTE')
    return item.fluxo === 'saida'
      ? { txt: 'Erro de emissão', cls: 'badge-error', icon: 'ti-alert-octagon' }
      : { txt: 'Erro do fornecedor', cls: 'badge-error', icon: 'ti-alert-octagon' }
  return null
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
  const [maisBusy, setMaisBusy] = useState(false)
  const [reproBusy, setReproBusy] = useState(false)
  const [erro, setErro] = useState(null)      // falha de carga NÃO vira "lista vazia"
  const [expandido, setExpandido] = useState(() => new Set())
  const [detalhe, setDetalhe] = useState(null)
  const [catalogo, setCatalogo] = useState({})   // código de erro → {mensagem, acao}

  useEffect(() => {
    api.stCatalogoErros()
      .then(lista => setCatalogo(Object.fromEntries(lista.map(e => [e.codigo, e]))))
      .catch(() => {})
  }, [])

  // Filtros de servidor: busca livre (debounce), status e código do motor.
  const [busca, setBusca] = useState('')
  const [q, setQ] = useState('')
  const [fStatus, setFStatus] = useState('')
  const [fCodigo, setFCodigo] = useState('')
  useEffect(() => { const t = setTimeout(() => setQ(busca.trim()), 400); return () => clearTimeout(t) }, [busca])

  const params = useCallback((page = 1) => ({
    fluxo: tab, data_inicio: `${ano}-${mes}-01`, data_fim: `${ano}-${mes}-31`,
    status: fStatus, codigo_erro: fCodigo, q,
    page, page_size: PAGE_SIZE,
  }), [tab, ano, mes, fStatus, fCodigo, q])

  const carregar = useCallback(async () => {
    if (!selectedEmpresa) { setData({ total: 0, itens: [] }); return }
    setLoading(true)
    setErro(null)
    try {
      setData(await api.stDivergencias(selectedEmpresa.id, params(1)))
    } catch (e) {
      setErro(e.message); setData({ total: 0, itens: [] })
    } finally { setLoading(false) }
  }, [selectedEmpresa, params])

  // Paginação real: acumula as páginas seguintes (antes truncava em 200 mudo).
  async function carregarMais() {
    setMaisBusy(true)
    try {
      const proxima = Math.floor(data.itens.length / PAGE_SIZE) + 1
      const r = await api.stDivergencias(selectedEmpresa.id, params(proxima))
      setData(d => ({ ...r, itens: [...d.itens, ...r.itens] }))
    } catch (e) { toast(e.message, 'error') }
    finally { setMaisBusy(false) }
  }

  async function reprocessar() {
    setReproBusy(true)
    try {
      const r = await api.reprocessarPendentes(selectedEmpresa.id)
      const partes = []
      if (r.notas_destravadas) partes.push(`${r.notas_destravadas} destravada(s)`)
      if (r.cfop_reclassificados) partes.push(`${r.cfop_reclassificados} CFOP reclassificado(s)`)
      toast(r.notas_reprocessadas
        ? `Reprocessadas ${r.notas_reprocessadas} nota(s)${partes.length ? ` · ${partes.join(' · ')}` : ''}.`
        : 'Nenhuma pendência reprocessável.', 'ok')
      carregar()
    } catch (e) { toast(e.message, 'error') }
    finally { setReproBusy(false) }
  }

  // Carta PDF de cobrança por fornecedor (ranking) — sem antecipações.
  const [cartaBusy, setCartaBusy] = useState(null)
  async function gerarCarta(cnpj) {
    setCartaBusy(cnpj)
    try {
      const { blob, filename } = await api.stCartaFornecedor(selectedEmpresa.id, {
        cnpj_emit: cnpj, fluxo: tab,
        data_inicio: `${ano}-${mes}-01`, data_fim: `${ano}-${mes}-31`,
      })
      saveBlob(blob, filename)
      toast('Carta de ST gerada — pronta para encaminhar.', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setCartaBusy(null) }
  }

  const [diagBusy, setDiagBusy] = useState(false)
  async function gerarDiagnostico() {
    setDiagBusy(true)
    try {
      const { blob, filename } = await api.stDiagnostico(selectedEmpresa.id)
      saveBlob(blob, filename)
      toast('Diagnóstico gerado — o retrato executivo do período todo.', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setDiagBusy(false) }
  }

  const [expBusy, setExpBusy] = useState(false)
  async function exportarExcel() {
    setExpBusy(true)
    try {
      const { blob, filename } = await api.stExportarDivergencias(selectedEmpresa.id, params())
      saveBlob(blob, filename)
      toast('Planilha exportada.', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setExpBusy(false) }
  }

  const [filtroCard, setFiltroCard] = useState(null)
  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setExpandido(new Set()); setFiltroCard(null) }, [selectedEmpresa, ano, mes, tab, q, fStatus, fCodigo])

  const itensVisiveis = useMemo(() => {
    const card = CARDS.find(c => c.key === filtroCard)
    return card ? data.itens.filter(card.filtro) : data.itens
  }, [data.itens, filtroCard])
  const notas = useMemo(() => agruparPorNota(itensVisiveis), [itensVisiveis])
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
          <p className="page-breadcrumb">
            {selectedEmpresa.razao_social} · {mes}/{ano} · {notas.length} nota(s) ·{' '}
            {data.itens.length < data.total
              ? <strong style={{ color: 'var(--warn-text)' }}>mostrando {data.itens.length} de {data.total} item(ns)</strong>
              : `${data.total} item(ns)`}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button className="btn btn-secondary" disabled={diagBusy} onClick={gerarDiagnostico}
            title="Relatório executivo em PDF de TODO o período auditado desta empresa: conformidade e dinheiro em jogo por competência + top fornecedores">
            <i className="ti ti-report-analytics" /> {diagBusy ? 'Gerando…' : 'Diagnóstico (PDF)'}
          </button>
          <button className="btn btn-secondary" disabled={expBusy || data.total === 0} onClick={exportarExcel}
            title="Planilha Excel do filtro atual (todas as páginas): itens + consolidação por fornecedor">
            <i className="ti ti-file-spreadsheet" /> {expBusy ? 'Exportando…' : 'Exportar Excel'}
          </button>
          <button className="btn btn-secondary" disabled={reproBusy} onClick={reprocessar}
            title="Re-aplica De/Para CFOP e re-audita as notas travadas por matriz faltante">
            <i className={`ti ti-refresh ${reproBusy ? 'spin' : ''}`} /> {reproBusy ? 'Reprocessando…' : 'Reprocessar Pendentes'}
          </button>
        </div>
      </div>

      {/* Abas + filtros de servidor (compõem com competência e paginação) */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3 }}>
          {[['entrada', 'Entradas', 'ti-arrow-down-left'], ['saida', 'Saídas', 'ti-arrow-up-right']].map(([v, label, icon]) => (
            <button key={v} onClick={() => setTab(v)} className="btn btn-sm"
              style={{ border: 'none', background: tab === v ? 'var(--surface)' : 'transparent', color: tab === v ? 'var(--text-1)' : 'var(--text-3)', boxShadow: tab === v ? 'var(--shadow-sm)' : 'none' }}>
              <i className={`ti ${icon}`} /> {label}
            </button>
          ))}
        </div>
        <div style={{ width: 190 }}>
          <Dropdown value={fStatus} onChange={setFStatus} options={[
            { value: '', label: 'Todas as situações' },
            { value: 'DIVERGENTE', label: 'Só divergentes' },
            { value: 'NAO_AUDITAVEL', label: 'Só não auditáveis' },
          ]} />
        </div>
        <div style={{ width: 250 }}>
          <Dropdown value={fCodigo} onChange={setFCodigo} options={[
            { value: '', label: 'Todos os códigos do motor' },
            ...Object.keys(catalogo).sort().map(c => ({
              value: c, label: c.replace(/^ERRO_(\d+_)?/, '').replaceAll('_', ' ').toLowerCase(),
            })),
          ]} />
        </div>
        <div style={{ position: 'relative', marginLeft: 'auto', width: 280, maxWidth: '100%' }}>
          <i className="ti ti-search" style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-4)', fontSize: 14 }} />
          <input value={busca} onChange={e => setBusca(e.target.value)}
            placeholder="Buscar fornecedor, produto, NF, NCM…"
            style={{ width: '100%', paddingLeft: 32, paddingRight: busca ? 30 : 12 }} />
          {busca && (
            <button onClick={() => setBusca('')} title="Limpar busca"
              style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text-4)', padding: 2, display: 'flex' }}>
              <i className="ti ti-x" style={{ fontSize: 13 }} />
            </button>
          )}
        </div>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : erro ? (
        <ErroCarga mensagem={erro} onRetry={carregar} />
      ) : data.itens.length === 0 ? (
        <div className="empty-state"><i className="ti ti-circle-check" /><p>Nenhuma divergência de ST nesta competência. 🎉</p></div>
      ) : (
        <>
          {/* O dinheiro em jogo — totais do período (backend, sem truncar) */}
          {data.resumo && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 18 }}>
              {CARDS.map(c => {
                const ativo = filtroCard === c.key
                return (
                  <div key={c.key} className="card" role="button"
                    title={`${c.label} — clique para filtrar a lista`}
                    onClick={() => setFiltroCard(f => (f === c.key ? null : c.key))}
                    style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4, cursor: 'pointer',
                             boxShadow: ativo ? `inset 0 0 0 2px var(--${c.tone}-text)` : undefined }}>
                    <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                      <i className={`ti ${c.icon}`} /> {c.label}
                      {ativo && <i className="ti ti-filter" style={{ marginLeft: 6, color: `var(--${c.tone}-text)` }} />}
                    </span>
                    <span style={{ fontSize: 21, fontWeight: 700, color: `var(--${c.tone}-text)` }}>
                      {c.dinheiro ? brl(data.resumo[c.key]) : (data.resumo[c.key] ?? 0)}
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--text-4)' }}>
                      {c.key === 'nao_auditaveis'
                        ? `${data.resumo.divergentes ?? 0} divergente(s) no período`
                        : 'total do período (todas as páginas)'}
                    </span>
                  </div>
                )
              })}
            </div>
          )}

          {/* Quem cobrar primeiro: divergência cobrável acumulada por emitente */}
          {(data.ranking_fornecedores || []).length > 0 && (
            <div className="card" style={{ padding: 0, marginBottom: 18 }}>
              <div style={{ padding: '12px 16px', fontWeight: 600, borderBottom: '1px solid var(--border-2)' }}>
                {tab === 'entrada' ? 'Fornecedores com divergência — priorize pelos maiores valores' : 'Emitentes com divergência'}
              </div>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>{tab === 'entrada' ? 'Fornecedor' : 'Emitente'}</th><th>CNPJ</th><th style={{ textAlign: 'right' }}>Itens</th><th style={{ textAlign: 'right' }}>Divergência cobrável</th><th /></tr></thead>
                  <tbody>
                    {data.ranking_fornecedores.map(f => (
                      <tr key={f.cnpj || f.nome}>
                        <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{f.nome || '—'}</td>
                        <td className="mono">{cnpjFmt(f.cnpj)}</td>
                        <td style={{ textAlign: 'right' }}>{f.itens}</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{brl(f.valor)}</td>
                        <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                          <button className="btn btn-secondary btn-sm" disabled={cartaBusy === f.cnpj}
                            title="Gera a carta timbrada (PDF) de cobrança/correção do ST deste emitente"
                            onClick={() => gerarCarta(f.cnpj)}>
                            <i className={`ti ${cartaBusy === f.cnpj ? 'ti-loader-2' : 'ti-file-type-pdf'}`} />
                            {cartaBusy === f.cnpj ? ' Gerando…' : ' Carta PDF'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {notas.length === 0 ? (
            <div className="empty-state">
              <i className="ti ti-filter-off" />
              <p>Nenhum item carregado nesta categoria.{data.itens.length < data.total ? ' Há mais páginas — use “Carregar mais” sem o filtro.' : ''}</p>
              <button className="btn btn-ghost btn-sm" onClick={() => setFiltroCard(null)}>Limpar filtro</button>
            </div>
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
                      key={nota.chave} nota={nota} aberto={aberto} catalogo={catalogo}
                      onToggle={() => toggle(nota.chave)} onMemoria={setDetalhe}
                    />
                  )
                })}
              </tbody>
            </table>
          </div>
          {data.itens.length < data.total && (
            <div style={{ padding: 14, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 12, borderTop: '1px solid var(--border-2)' }}>
              <span style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
                Mostrando {data.itens.length} de {data.total} item(ns) — a lista abaixo cobre só o carregado; os cards somam o período inteiro.
              </span>
              <button className="btn btn-secondary btn-sm" disabled={maisBusy} onClick={carregarMais}>
                {maisBusy ? <span className="spinner" style={{ width: 12, height: 12 }} /> : <i className="ti ti-arrow-down" />} Carregar mais
              </button>
            </div>
          )}
        </div>
          )}
        </>
      )}

      {detalhe && <MemoriaModal d={detalhe} onClose={() => setDetalhe(null)} />}
    </div>
  )
}

// Rótulo pequeno que nomeia a linha do confronto ("NA NOTA" / "DEVIDO").
const RotuloSt = ({ children }) => (
  <span style={{ color: 'var(--text-4)', fontWeight: 600, fontSize: 9.5, textTransform: 'uppercase', letterSpacing: 0.5 }}>{children}</span>
)

// ── Linha-mestre (Nota) + linhas-filhas (itens) quando expandida ──
function FragmentoNota({ nota, aberto, onToggle, onMemoria, catalogo }) {
  const navigate = useNavigate()
  const temCte = nota.ctes.length > 0
  // Primeira ação sugerida do catálogo do motor para os códigos do item.
  const acaoDoCatalogo = (item) => {
    for (const cod of (item.codigo_erro || '').split(', ')) {
      if (catalogo[cod]?.acao) return { cod, ...catalogo[cod] }
    }
    return null
  }
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
        <td>{nota.ufOrigem}→{nota.ufDestino}</td>
        <td style={{ textAlign: 'center' }}>
          {temCte
            ? <i className="ti ti-truck" title={`CT-e vinculado(s): ${nota.ctes.join(', ')}`}
                 style={{ color: 'var(--info-text)', fontSize: 17 }} />
            : <span style={{ color: 'var(--text-4)' }}>—</span>}
        </td>
        <td className="tnum" style={{ textAlign: 'right' }}>{brl(nota.totalIcmsSt)}</td>
        <td className="tnum" style={{ textAlign: 'right', fontWeight: 700, color: corDiferenca(nota.totalDiferenca) }}>
          {brl(nota.totalDiferenca)}
        </td>
        <td style={{ textAlign: 'center' }}>
          {nota.divergentes > 0 && <span className="badge badge-error" style={{ fontSize: 10 }}>{nota.divergentes} divergente(s)</span>}
          {nota.naoAuditaveis > 0 && <span className="badge badge-warn" style={{ fontSize: 10, marginLeft: 4 }}>{nota.naoAuditaveis} não auditado(s)</span>}
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
        const acao = acaoDoCatalogo(it)
        const destinoMatriz = it.status === 'NAO_AUDITAVEL' ? linkMatriz(it) : null
        return (
        <tr key={it.numero_item} style={{ background: 'var(--surface)' }}>
          <td />
          <td style={{ paddingLeft: 28 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
              <span style={{ fontWeight: 600, color: 'var(--text-1)', maxWidth: 360, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={it.descricao}>
                {it.descricao || `Item ${it.numero_item} da nota`}
              </span>
              {selo && (
                <span className={`badge ${selo.cls}`} style={{ fontSize: 10 }}>
                  <i className={`ti ${selo.icon}`} style={{ marginRight: 3 }} />{selo.txt}
                </span>
              )}
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 2 }}>
              {it.ncm && <>NCM {it.ncm} · </>}{it.cest && <>CEST {it.cest} · </>}
              CST {it.cst_csosn || '—'} · modBCST {it.mod_bc_st ?? '—'} · item {it.numero_item}
            </div>
            {it.status === 'NAO_AUDITAVEL' && it.observacao && (
              <div style={{ fontSize: 11, color: 'var(--warn-text)', marginTop: 2 }}><i className="ti ti-alert-circle" style={{ marginRight: 4 }} />{it.observacao}</div>
            )}
            {acao && (
              <div style={{ fontSize: 11.5, color: 'var(--text-3)', marginTop: 2 }} title={acao.mensagem}>
                <i className="ti ti-bulb" style={{ marginRight: 4, color: 'var(--accent-text)' }} />
                <strong style={{ color: 'var(--text-2)' }}>Ação:</strong> {acao.acao}
                {destinoMatriz && (
                  <button className="btn btn-ghost btn-sm" style={{ marginLeft: 8, padding: '1px 8px', fontSize: 11.5 }}
                    onClick={(e) => { e.stopPropagation(); navigate(destinoMatriz) }}>
                    <i className="ti ti-table-plus" /> Cadastrar matriz
                  </button>
                )}
              </div>
            )}
          </td>
          <td colSpan={2}>
            <div style={{ display: 'inline-grid', gridTemplateColumns: 'auto auto', columnGap: 7, rowGap: 1, alignItems: 'baseline', lineHeight: 1.5 }}>
              <RotuloSt>na nota</RotuloSt>
              <span className="tnum" style={{ fontSize: 12.5, color: 'var(--text-3)' }}>{brl(it.vicms_st_xml)}</span>
              <RotuloSt>devido</RotuloSt>
              <span className="tnum" style={{ fontSize: 12.5, fontWeight: 700 }}>{brl(it.vicms_st_calculado)}</span>
            </div>
          </td>
          <td className="tnum" style={{ textAlign: 'right' }}>{brl(it.vicms_st_calculado)}</td>
          <td className="tnum" style={{ textAlign: 'right', fontWeight: 600, color: corDiferenca(it.diferenca) }}>{brl(it.diferenca)}</td>
          <td style={{ textAlign: 'center' }}>
            {it.memoria && <button className="btn btn-icon" title="Como chegamos ao valor devido (memória de cálculo)" onClick={() => onMemoria(it)}><i className="ti ti-calculator" /></button>}
          </td>
        </tr>
        )
      })}
    </>
  )
}

// ── Modal da Verdade: a jornada matemática do JSON `memoria`, escrita para
// qualquer pessoa entender (o jargão fica nos tooltips e na rastreabilidade) ──
const DEDUCAO_LEIGO = {
  real: 'o ICMS que o vendedor já destacou na própria nota',
  teorica: 'o ICMS teórico da operação própria (emitente do Simples)',
  zero: 'nada a descontar (operação própria isenta)',
  contaminada: 'o ICMS próprio recalculado (o da nota veio zerado por erro)',
}

function MemoriaModal({ d, onClose }) {
  const m = d.memoria || {}
  const ajustada = m.mva_foi_ajustada
  const temFcp = Number(m.fcp_st_debito || 0) > 0
  const dif = Number(d.diferenca || 0)
  const interna = d.uf_origem === d.uf_destino

  const frase = dif < -0.004
    ? <>A nota destacou <b>{brl(d.vicms_st_xml)}</b>, mas pela regra vigente o valor é <b>{brl(d.vicms_st_calculado)}</b> — <b style={{ color: 'var(--err-text)' }}>faltaram {brl(-dif)}</b> de ST.</>
    : dif > 0.004
      ? <>A nota destacou <b>{brl(d.vicms_st_xml)}</b> — <b style={{ color: 'var(--info-text)' }}>{brl(dif)} a mais</b> que o devido ({brl(d.vicms_st_calculado)}): candidato a ressarcimento.</>
      : <>O valor destacado confere com o cálculo.</>

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 560, maxWidth: '96%' }}>
        <div className="modal-header">
          <h2><i className="ti ti-calculator" style={{ marginRight: 8 }} />Como chegamos ao valor devido</h2>
          <button className="btn btn-icon" onClick={onClose}><i className="ti ti-x" /></button>
        </div>
        <div className="modal-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 12 }}>
            <Cartao titulo="Destacado na nota" valor={brl(d.vicms_st_xml)} />
            <Cartao titulo="Devido pela regra" valor={brl(d.vicms_st_calculado)} destaque />
            <Cartao titulo="Diferença" valor={brl(d.diferenca)} cor={corDiferenca(d.diferenca)} />
          </div>

          {/* A conclusão em uma frase — antes de qualquer número. */}
          <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: '10px 14px', fontSize: 13, lineHeight: 1.55, marginBottom: 18 }}>
            {frase}
          </div>

          <div className="section-label" style={{ marginBottom: 8 }}>Onde nasce a diferença</div>
          <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', marginBottom: 18, overflow: 'hidden' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px 90px 92px', gap: 10, padding: '6px 12px', background: 'var(--surface-2)', fontSize: 10.5, fontWeight: 600, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: 0.4 }}>
              <span>Etapa</span><span style={{ textAlign: 'right' }}>Na nota</span><span style={{ textAlign: 'right' }}>Pela regra</span><span style={{ textAlign: 'center' }}>Confere?</span>
            </div>
            <LinhaConfronto rotulo="Margem presumida (MVA)" xml={d.pmva_xml} calc={d.pmva_calculada} fmt={pct} tol={0.011} />
            <LinhaConfronto rotulo="Base de cálculo do ST" xml={d.vbc_st_xml} calc={d.vbc_st_calculado} />
            <LinhaConfronto rotulo="ICMS-ST" xml={d.vicms_st_xml} calc={d.vicms_st_calculado} />
            <LinhaConfronto rotulo="FCP-ST (fundo de combate à pobreza)" xml={d.vfcp_st_xml} calc={d.vfcp_st_calculado} ultima />
          </div>

          <div className="section-label" style={{ marginBottom: 10 }}>O cálculo, passo a passo</div>
          <Passo n="1" titulo="A operação"
            sub={interna
              ? `Venda dentro de ${d.uf_destino} · produto enquadrado na substituição tributária`
              : `${d.uf_origem} → ${d.uf_destino} · produto enquadrado na substituição tributária`}
            valor={`alíquotas: ${pct(m.alq_inter)} inter · ${pct(m.alq_intra)} interna`} />
          <Passo n="2" titulo="Margem presumida (MVA)"
            sub={ajustada
              ? 'Ajustada: em venda entre estados a lei corrige a margem pela diferença de alíquotas'
              : 'A margem que a lei presume até a venda ao consumidor final'}
            valor={<><span style={{ color: 'var(--text-4)' }}>{pct(m.mva_original)}</span> <i className="ti ti-arrow-right" style={{ fontSize: 12 }} /> <b>{pct(m.mva_aplicada)}</b></>}
            badge={ajustada ? { txt: 'Ajustada', cls: 'badge-info' } : { txt: 'Original', cls: 'badge-ok' }} />
          <Passo n="3" titulo="Base de cálculo do ST" sub="preço do produto + frete e encargos, acrescido da margem" valor={brl(m.base_st_calculada)} />
          <Passo n="4" titulo="Imposto cheio sobre a base" sub={`base × alíquota interna de ${pct(m.alq_intra)}`} valor={brl(m.icms_st_debito)} />
          <Passo n="5" titulo="(−) Desconto do ICMS próprio" sub={DEDUCAO_LEIGO[m.deducao_tipo] || 'desconto do imposto da operação própria'} valor={`− ${brl(m.deducao_aplicada)}`} negativo />
          <Passo n="=" titulo="ICMS-ST devido" valor={brl(m.icms_st_calculado)} final />

          {temFcp && (
            <>
              <div className="section-label" style={{ margin: '18px 0 10px' }}>FCP-ST (trilha paralela)</div>
              <Passo n="A" titulo="Débito FCP-ST" valor={brl(m.fcp_st_debito)} />
              <Passo n="B" titulo="(−) FCP próprio (não-cumulatividade)" valor={`− ${brl(m.fcp_st_deducao)}`} negativo />
              <Passo n="=" titulo="FCP-ST devido" valor={brl(m.fcp_st_calculado)} final />
            </>
          )}

          {/* Defensibilidade: qual versão do motor e quais linhas de matriz decidiram. */}
          <div style={{ marginTop: 14, fontSize: 11, color: 'var(--text-4)', lineHeight: 1.6 }}>
            <i className="ti ti-shield-check" style={{ marginRight: 4 }} />
            Rastreabilidade: motor v{m.engine_version || '—'} · MVA da matriz {m.mva_matriz_id ? `#${m.mva_matriz_id}` : '—'}{m.mva_base_legal ? ` (${m.mva_base_legal})` : ''} ·
            alíquota da matriz {m.aliquota_matriz_id ? `#${m.aliquota_matriz_id}` : '—'}{m.aliquota_base_legal ? ` (${m.aliquota_base_legal})` : ''} ·
            protocolo: {m.tem_protocolo == null ? 'operação interna (não se aplica)' : m.tem_protocolo ? 'com acordo' : 'sem acordo'}
            {m.protocolo_fonte ? ` (fonte: ${m.protocolo_fonte})` : ''}
          </div>
        </div>
        <div className="modal-footer"><button className="btn btn-ghost" onClick={onClose}>Fechar</button></div>
      </div>
    </div>
  )
}

// Linha do confronto etapa a etapa: destaca EM QUAL passo a conta descola.
function LinhaConfronto({ rotulo, xml, calc, fmt = brl, tol = 0.021, ultima }) {
  const dif = Number(xml || 0) - Number(calc || 0)
  const bate = Math.abs(dif) <= tol
  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 90px 90px 92px', gap: 10, alignItems: 'center', padding: '7px 12px', borderBottom: ultima ? 'none' : '1px solid var(--border-2)', fontSize: 12.5 }}>
      <span style={{ color: 'var(--text-2)' }}>{rotulo}</span>
      <span className="mono" style={{ textAlign: 'right', color: 'var(--text-3)' }}>{fmt(xml)}</span>
      <span className="mono" style={{ textAlign: 'right', fontWeight: 600 }}>{fmt(calc)}</span>
      <span style={{ textAlign: 'center' }}>
        {bate
          ? <span className="badge badge-ok" style={{ fontSize: 10 }}>confere</span>
          : <span className="badge badge-error" style={{ fontSize: 10 }}>Δ {fmt(dif)}</span>}
      </span>
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
