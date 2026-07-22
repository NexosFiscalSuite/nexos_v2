import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import ErroCarga from '../components/ErroCarga'
import { api, saveBlob } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useRefresh } from '../context/RefreshContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const TABS = [
  { value: 'saida', label: 'Saída', icon: 'ti-arrow-up-right' },
  { value: 'entrada', label: 'Entrada', icon: 'ti-arrow-down-left' },
  { value: 'servico', label: 'Serviço', icon: 'ti-briefcase' },
  { value: 'cte', label: 'CT-e', icon: 'ti-truck' },
]
const SUBSERV = [
  { value: 'prestador', label: 'Prestador' },
  { value: 'tomador', label: 'Tomador' },
]
// aba -> filtros de API. Serviço Tomador = NFS-e recebida (fluxo entrada + tipo NFSe);
// Entrada exclui NFS-e (que vai para a aba Serviço/Tomador).
function abaParams(tab, subServ) {
  if (tab === 'saida') return { fluxo: 'saida' }
  if (tab === 'cte') return { fluxo: 'cte' }
  if (tab === 'entrada') return { fluxo: 'entrada', tipo_excluir: 'NFSe' }
  return subServ === 'tomador' ? { fluxo: 'entrada', tipo: 'NFSe' } : { fluxo: 'servico' }
}
const STATUS_OPTS = [
  { value: '', label: 'Todos os status' }, { value: 'ativa', label: 'Ativas' }, { value: 'cancelada', label: 'Canceladas' },
]
const ISS_OPTS = [{ value: '', label: '—' }, { value: '1', label: 'Sim' }, { value: '0', label: 'Não' }]
const OP_OPTS = [
  { value: '', label: 'Selecione a operação' },
  { value: 'tipo', label: 'Classificar Tipo da Nota' },
  { value: 'cfop', label: 'Alterar CFOP' },
  { value: 'cancelar', label: 'Cancelar' },
  { value: 'reativar', label: 'Autorizar (reativar)' },
  { value: 'xml', label: 'Download XML' },
  { value: 'danfe', label: 'Download DANFE' },
]
const FLUXO_ICON = { entrada: 'ti-arrow-down-left', saida: 'ti-arrow-up-right', servico: 'ti-briefcase', cte: 'ti-truck' }
const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const isNfse = (n) => n && (n.tipo === 'NFSe' || String(n.modelo || '').startsWith('NFSe'))
const isEntrada = (n) => n && (n.fluxo === 'entrada' || n.fluxo === 'cte')

// Cor por status/tipo (identidade visual da grelha)
function linhaCor(n) {
  if (n.status === 'cancelada') return 'var(--err-text)'
  if (n.tipo_nota === 'Devolução de compra') return '#16A34A'
  if (n.tipo_nota === 'Devolução de venda') return 'var(--info-text)'
  if (isEntrada(n) && !n.tipo_nota) return 'var(--warn-text)'
  return null
}

export default function Notas() {
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { dataVersion, bumpData } = useRefresh()
  const { toasts, toast } = useToast()

  const [tab, setTab] = useState('saida')
  const [subServ, setSubServ] = useState('prestador')
  const [status, setStatus] = useState('')
  // Busca livre (nº da NF, chave, nome ou CNPJ): digita → aplica com debounce.
  const [busca, setBusca] = useState('')
  const [q, setQ] = useState('')
  const [sort, setSort] = useState(null)
  const [order, setOrder] = useState(null)
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ total: 0, notas: [], page: 1, page_size: 20 })
  const [loading, setLoading] = useState(false)
  const [erro, setErro] = useState(null)   // falha de carga NÃO pode parecer "sem notas"
  const [selected, setSelected] = useState(new Set())
  const [op, setOp] = useState('')
  const [busy, setBusy] = useState(false)
  const [cfopModal, setCfopModal] = useState(false)
  const [cfopVal, setCfopVal] = useState('')
  const [tipoModal, setTipoModal] = useState(false)
  const [tipoVal, setTipoVal] = useState('')

  const [detalhe, setDetalhe] = useState(null)
  const [head, setHead] = useState({})
  const [itens, setItens] = useState([])
  const [tiposSped, setTiposSped] = useState([])
  const [tiposNota, setTiposNota] = useState([])
  const [savingD, setSavingD] = useState(false)

  const carregar = useCallback(async () => {
    if (!selectedEmpresa) { setData({ total: 0, notas: [], page: 1, page_size: 20 }); return }
    setLoading(true)
    setErro(null)
    try {
      const p = abaParams(tab, subServ)
      setData(await api.notas(selectedEmpresa.id, { ...p, status_: status, ano, mes, q, sort, order, page, page_size: 20 }))
    } catch (e) { setErro(e.message); setData({ total: 0, notas: [], page: 1, page_size: 20 }) }
    finally { setLoading(false) }
  }, [selectedEmpresa, tab, subServ, status, ano, mes, q, sort, order, page, dataVersion])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { const t = setTimeout(() => setQ(busca.trim()), 400); return () => clearTimeout(t) }, [busca])
  useEffect(() => { setPage(1); setSelected(new Set()) }, [selectedEmpresa, tab, subServ, status, ano, mes, q, sort, order])
  useEffect(() => {
    api.tiposSped().then(setTiposSped).catch(() => {})
    api.tiposNota().then(setTiposNota).catch(() => {})
  }, [])

  const totalPages = Math.max(1, Math.ceil(data.total / (data.page_size || 20)))
  const tipoOpts = [{ value: '', label: '—' }, ...tiposNota.map(t => ({ value: t, label: t }))]
  const spedOpts = [{ value: '', label: '—' }, ...tiposSped.map(t => ({ value: t, label: t }))]

  function toggleSort(col) {
    if (sort !== col) { setSort(col); setOrder('asc') }
    else if (order === 'asc') setOrder('desc')
    else { setSort(null); setOrder(null) }
  }
  const allPageSel = data.notas.length > 0 && data.notas.every(n => selected.has(n.id))
  const toggleAll = () => setSelected(prev => {
    const s = new Set(prev); if (allPageSel) data.notas.forEach(n => s.delete(n.id)); else data.notas.forEach(n => s.add(n.id)); return s
  })
  const toggleOne = (id) => setSelected(prev => { const s = new Set(prev); s.has(id) ? s.delete(id) : s.add(id); return s })

  async function executarLote() {
    const ids = [...selected]
    if (!op) { toast('Escolha uma operação.', 'error'); return }
    if (!ids.length) { toast('Selecione ao menos uma nota.', 'error'); return }
    if (op === 'cfop') { setCfopModal(true); return }
    if (op === 'tipo') { setTipoModal(true); return }
    setBusy(true)
    try {
      if (op === 'cancelar') { const r = await api.cancelarLote(selectedEmpresa.id, ids); toast(`${r.afetadas} cancelada(s).`, 'ok'); setSelected(new Set()); bumpData() }
      else if (op === 'reativar') { const r = await api.reativarLote(selectedEmpresa.id, ids); toast(`${r.afetadas} reativada(s).`, 'ok'); setSelected(new Set()); bumpData() }
      else if (op === 'xml') { const { blob, filename } = await api.xmlLote(selectedEmpresa.id, ids); saveBlob(blob, filename) }
      else if (op === 'danfe') { toast('Gerando DANFEs…', 'info'); const { blob, filename } = await api.danfeLote(selectedEmpresa.id, ids); saveBlob(blob, filename) }
    } catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  async function aplicarCfop() {
    setBusy(true)
    try { const r = await api.cfopLote(selectedEmpresa.id, [...selected], cfopVal.trim()); toast(`CFOP em ${r.afetadas} nota(s).`, 'ok'); setCfopModal(false); setCfopVal(''); setSelected(new Set()); bumpData() }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }
  async function aplicarTipo() {
    setBusy(true)
    try { const r = await api.tipoLote(selectedEmpresa.id, [...selected], tipoVal); toast(`Tipo aplicado a ${r.afetadas} nota(s).`, 'ok'); setTipoModal(false); setTipoVal(''); setSelected(new Set()); bumpData() }
    catch (e) { toast(e.message, 'error') } finally { setBusy(false) }
  }

  async function abrir(id) {
    try {
      const d = await api.notaDetalhe(id)
      setDetalhe(d)
      setHead({
        data_entrada: d.data_entrada || '',
        competencia: d.competencia || '',
        iss_retido: d.iss_retido == null ? '' : String(d.iss_retido),
        tipo_nota: d.tipo_nota || '',
      })
      setItens((d.itens || []).map(i => ({ ...i })))
    } catch (e) { toast(e.message, 'error') }
  }

  async function salvar() {
    setSavingD(true)
    try {
      const payload = { data_entrada: head.data_entrada || null, competencia: head.competencia || null }
      if (isEntrada(detalhe)) payload.tipo_nota = head.tipo_nota || null
      if (isNfse(detalhe)) payload.iss_retido = head.iss_retido === '' ? null : Number(head.iss_retido)
      await api.editarNota(detalhe.id, payload)
      const orig = Object.fromEntries((detalhe.itens || []).map(i => [i.numero_item, i]))
      for (const it of itens) {
        const o = orig[it.numero_item]
        if (o && (o.cfop !== it.cfop || o.tipo_sped !== it.tipo_sped)) {
          await api.editarItem(detalhe.id, it.id, { cfop: it.cfop, tipo_sped: it.tipo_sped })
        }
      }
      toast('Nota atualizada.', 'ok'); setDetalhe(null); bumpData()
    } catch (e) { toast(e.message, 'error') } finally { setSavingD(false) }
  }
  async function cancelarNota() {
    if (!confirm('Cancelar esta nota?')) return
    try { await api.cancelarNota(detalhe.id); toast('Nota cancelada.', 'ok'); setDetalhe(null); bumpData() } catch (e) { toast(e.message, 'error') }
  }
  async function baixar(kind) {
    try { const { blob, filename } = kind === 'xml' ? await api.downloadXml(detalhe.id) : await api.downloadDanfe(detalhe.id); saveBlob(blob, filename) }
    catch (e) { toast(e.message, 'error') }
  }
  // Atalho: salva a combinação CFOP -> Tipo de Item como regra De/Para
  async function salvarRegraItem(it) {
    if (!it.tipo_sped) { toast('Defina o Tipo SPED do item primeiro.', 'error'); return }
    try {
      await api.cfopRegraCriar({
        tipo_item: it.tipo_sped, cfop_origem: it.cfop_original || it.cfop,
        cfop_destino: it.cfop, usa_extensao: false,
      })
      toast('Regra De/Para criada para as próximas importações.', 'ok')
    } catch (e) { toast(e.message, 'error') }
  }

  if (!selectedEmpresa) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Notas Fiscais</h1></div>
        <div className="empty-state"><i className="ti ti-building-store" /><p>Selecione uma empresa no topo.</p></div>
      </div>
    )
  }

  const Th = ({ col, children, align }) => {
    const active = sort === col
    return (
      <th className="th-sort" onClick={() => toggleSort(col)} style={{ textAlign: align || 'left' }}>
        {children} <i className={`ti ti-${active ? (order === 'asc' ? 'arrow-up' : 'arrow-down') : 'arrows-sort'} ${active ? '' : 'th-sort-inactive'}`} />
      </th>
    )
  }
  const RO = ({ label, value, span }) => (
    <div className="field" style={{ marginBottom: 0, gridColumn: span ? `span ${span}` : undefined }}>
      <label>{label}</label>
      <div className="nf-readonly mono">{value || '—'}</div>
    </div>
  )

  const entradaDet = isEntrada(detalhe)
  const cp = detalhe ? (entradaDet
    ? { lbl: 'Emitente', cnpj: detalhe.cnpj_emit, uf: detalhe.uf_emit, nome: detalhe.nome_emit }
    : { lbl: 'Destinatário', cnpj: detalhe.cnpj_dest, uf: detalhe.uf_dest, nome: detalhe.nome_dest }) : {}

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Notas Fiscais</h1>
          <p className="page-breadcrumb">{selectedEmpresa.razao_social} · {mes}/{ano}</p>
        </div>
        <div style={{ width: 160 }}><Dropdown value={status} onChange={setStatus} options={STATUS_OPTS} /></div>
      </div>

      {/* Abas por fluxo */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3 }}>
          {TABS.map(t => (
            <button key={t.value} onClick={() => setTab(t.value)} className="btn btn-sm"
              style={{ background: tab === t.value ? 'var(--surface)' : 'transparent', color: tab === t.value ? 'var(--text-1)' : 'var(--text-3)', boxShadow: tab === t.value ? 'var(--shadow-sm)' : 'none', border: 'none' }}>
              <i className={`ti ${t.icon}`} /> {t.label}
            </button>
          ))}
        </div>
        {tab === 'servico' && (
          <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3 }}>
            {SUBSERV.map(s => (
              <button key={s.value} onClick={() => setSubServ(s.value)} className="btn btn-sm"
                style={{ background: subServ === s.value ? 'var(--surface)' : 'transparent', color: subServ === s.value ? 'var(--primary-text)' : 'var(--text-3)', boxShadow: subServ === s.value ? 'var(--shadow-sm)' : 'none', border: 'none' }}>
                {s.label}
              </button>
            ))}
          </div>
        )}
        {/* Busca livre: acha a nota no meio de centenas sem paginar */}
        <div style={{ position: 'relative', marginLeft: 'auto', width: 300, maxWidth: '100%' }}>
          <i className="ti ti-search" style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-4)', fontSize: 14 }} />
          <input
            value={busca}
            onChange={e => setBusca(e.target.value)}
            placeholder="Buscar nº da NF, chave, nome ou CNPJ…"
            style={{ width: '100%', paddingLeft: 32, paddingRight: busca ? 30 : 12 }}
          />
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
      ) : data.notas.length === 0 ? (
        <div className="empty-state"><i className="ti ti-file-off" /><p>{q ? <>Nenhuma nota encontrada para “{q}”.</> : 'Nenhuma nota nesta competência.'}</p></div>
      ) : (
        <>
          <div className="card" style={{ padding: 0 }}>
            <div className="tbl-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th style={{ width: 34 }}><input type="checkbox" checked={allPageSel} onChange={toggleAll} /></th>
                    <Th col="fluxo">Fluxo</Th><Th col="modelo">Modelo</Th><Th col="numero">Número</Th>
                    <Th col="serie">Série</Th><Th col="contraparte">Contraparte</Th>
                    <Th col="valor" align="right">Valor</Th><Th col="data_emissao">Emissão</Th><Th col="status">Status</Th>
                  </tr>
                </thead>
                <tbody>
                  {data.notas.map(n => {
                    const contra = n.fluxo === 'saida' ? (n.nome_dest || n.cnpj_dest) : (n.nome_emit || n.cnpj_emit)
                    const cor = linhaCor(n)
                    const txt = cor ? { color: cor, fontWeight: 500 } : {}
                    const click = () => abrir(n.id)
                    return (
                      <tr key={n.id} style={{ background: selected.has(n.id) ? 'var(--primary-lt)' : undefined }}>
                        <td onClick={e => e.stopPropagation()}><input type="checkbox" checked={selected.has(n.id)} onChange={() => toggleOne(n.id)} /></td>
                        <td onClick={click} style={{ cursor: 'pointer', textTransform: 'capitalize', ...txt }}><i className={`ti ${FLUXO_ICON[n.fluxo] || 'ti-file'}`} style={{ marginRight: 6 }} />{n.fluxo}</td>
                        <td onClick={click} style={{ cursor: 'pointer', ...txt }}>{n.modelo}</td>
                        <td onClick={click} className="mono" style={{ cursor: 'pointer', ...txt }}>
                          {n.numero}{n.tem_correcao && <i className="ti ti-writing" title="CC-e emitida" style={{ marginLeft: 6, color: 'var(--info-text)' }} />}{n.tem_cte && <i className="ti ti-truck" title="Possui CT-e vinculado" style={{ marginLeft: 6, color: 'var(--info-text)' }} />}
                        </td>
                        <td onClick={click} className="mono" style={{ cursor: 'pointer', ...txt }}>{n.serie || '—'}</td>
                        <td onClick={click} style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', cursor: 'pointer', ...txt }}>{contra || '—'}</td>
                        <td onClick={click} className="mono" style={{ textAlign: 'right', cursor: 'pointer', ...txt }}>{brl(n.valor_total)}</td>
                        <td onClick={click} className="mono" style={{ cursor: 'pointer', ...txt }}>{n.data_emissao || '—'}</td>
                        <td onClick={click} style={{ cursor: 'pointer' }}><span className={`badge ${n.status === 'cancelada' ? 'badge-error' : 'badge-ok'}`}>{n.status}</span></td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* Legenda de cores */}
          <div style={{ display: 'flex', gap: 18, flexWrap: 'wrap', marginTop: 12, fontSize: 11, color: 'var(--text-4)', alignItems: 'center' }}>
            <span style={{ fontWeight: 600 }}>Legenda:</span>
            {[['var(--err-text)', 'Cancelada'], ['#16A34A', 'Devolução de compra'], ['var(--info-text)', 'Devolução de venda'], ['var(--warn-text)', 'Entrada sem classificação']].map(([c, t]) => (
              <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                <span style={{ width: 9, height: 9, borderRadius: 2, background: c, display: 'inline-block' }} />{t}
              </span>
            ))}
          </div>

          {/* Ações em lote + paginação */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 14, gap: 12, flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, color: 'var(--text-4)' }}>{data.total} nota(s) · {selected.size} selecionada(s)</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div style={{ width: 210 }}><Dropdown value={op} onChange={setOp} options={OP_OPTS} /></div>
              <button className="btn btn-primary btn-sm" disabled={busy || !selected.size} onClick={executarLote}>
                {busy ? <span className="spinner" style={{ width: 14, height: 14 }} /> : <i className="ti ti-player-play" />} Realizar em lote
              </button>
              <div style={{ width: 1, height: 24, background: 'var(--border)' }} />
              <button className="btn btn-ghost btn-sm" disabled={page <= 1} onClick={() => setPage(p => p - 1)}><i className="ti ti-chevron-left" /></button>
              <span style={{ fontSize: 13 }}>{page} / {totalPages}</span>
              <button className="btn btn-ghost btn-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}><i className="ti ti-chevron-right" /></button>
            </div>
          </div>
        </>
      )}

      {/* Modal CFOP em lote */}
      {cfopModal && (
        <div className="modal-overlay" onClick={() => setCfopModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 380 }}>
            <div className="modal-header"><h2>Alterar CFOP em lote</h2><button className="btn btn-icon" onClick={() => setCfopModal(false)}><i className="ti ti-x" /></button></div>
            <div className="modal-body">
              <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 12 }}>Aplica o CFOP a todos os itens das {selected.size} nota(s). O CFOP original é preservado.</p>
              <div className="field"><label>Novo CFOP</label><input value={cfopVal} onChange={e => setCfopVal(e.target.value)} placeholder="ex.: 5102" autoFocus /></div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setCfopModal(false)}>Cancelar</button>
              <button className="btn btn-primary" disabled={busy || !cfopVal.trim()} onClick={aplicarCfop}>{busy ? 'Aplicando…' : 'Aplicar'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal Tipo da Nota em lote */}
      {tipoModal && (
        <div className="modal-overlay" onClick={() => setTipoModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 420 }}>
            <div className="modal-header"><h2>Classificar Tipo da Nota</h2><button className="btn btn-icon" onClick={() => setTipoModal(false)}><i className="ti ti-x" /></button></div>
            <div className="modal-body">
              <p style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 12 }}>Aplica o tipo a {selected.size} nota(s) selecionada(s).</p>
              <div className="field"><label>Tipo da Nota</label><Dropdown value={tipoVal} onChange={setTipoVal} options={tipoOpts} placeholder="Selecione…" /></div>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setTipoModal(false)}>Cancelar</button>
              <button className="btn btn-primary" disabled={busy || !tipoVal} onClick={aplicarTipo}>{busy ? 'Aplicando…' : 'Aplicar'}</button>
            </div>
          </div>
        </div>
      )}

      {/* Modal detalhe */}
      {detalhe && (
        <div className="modal-overlay" onClick={() => setDetalhe(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 980, maxWidth: '96%' }}>
            <div className="modal-header">
              <h2>
                Nota Fiscal | {detalhe.fluxo} | {detalhe.tipo} | {detalhe.numero}
                {detalhe.tem_correcao && <span className="badge badge-info" style={{ marginLeft: 10 }}><i className="ti ti-writing" /> CC-e</span>}
              </h2>
              <button className="btn btn-icon" onClick={() => setDetalhe(null)}><i className="ti ti-x" /></button>
            </div>
            <div className="modal-body">
              {/* Cabeçalho padrão (sempre) */}
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 2fr', gap: 14, marginBottom: 14 }}>
                <RO label="Número" value={detalhe.numero} />
                <RO label="Status" value={detalhe.status?.toUpperCase()} />
                <RO label="Chave de Acesso" value={detalhe.chave_acesso} />
                <RO label={`CNPJ do ${cp.lbl}`} value={cp.cnpj} />
                <RO label={`UF do ${cp.lbl}`} value={cp.uf} />
                <RO label={`Nome do ${cp.lbl}`} value={cp.nome} />
                <RO label="Data de Emissão" value={detalhe.data_emissao} />
                <RO label="Valor Total" value={brl(detalhe.valor_total)} />
                <RO label="Série" value={detalhe.serie} />
              </div>

              {/* Campos editáveis (dependentes do tipo) */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14 }}>
                {entradaDet && (
                  <div className="field"><label>Data de Entrada</label>
                    <input type="date" value={head.data_entrada} onChange={e => setHead(h => ({ ...h, data_entrada: e.target.value }))} /></div>
                )}
                <div className="field"><label>Competência (AAAA-MM)</label>
                  <input value={head.competencia} onChange={e => setHead(h => ({ ...h, competencia: e.target.value }))} placeholder="2026-03" /></div>
                {entradaDet && (
                  <div className="field" style={{ gridColumn: 'span 2' }}><label>Tipo da Nota</label>
                    <Dropdown value={head.tipo_nota} onChange={v => setHead(h => ({ ...h, tipo_nota: v }))} options={tipoOpts} placeholder="Classifique a entrada…" /></div>
                )}
                {isNfse(detalhe) && (
                  <div className="field"><label>ISS retido</label>
                    <Dropdown value={head.iss_retido} onChange={v => setHead(h => ({ ...h, iss_retido: v }))} options={ISS_OPTS} /></div>
                )}
              </div>

              <div className="section-label" style={{ marginTop: 18 }}>Itens ({itens.length})</div>
              <div className="tbl-wrap">
                <table className="table" style={{ minWidth: 860 }}>
                  <thead>
                    <tr>
                      <th>#</th><th>Descrição</th><th>NCM</th><th>CFOP</th>
                      {entradaDet && <th style={{ minWidth: 170 }}>Tipo SPED</th>}
                      <th style={{ textAlign: 'right' }}>Qtd</th><th style={{ textAlign: 'right' }}>Unit.</th>
                      <th style={{ textAlign: 'right' }}>Desc.</th><th style={{ textAlign: 'right' }}>Frete</th>
                      <th style={{ textAlign: 'right' }}>Base ICMS</th><th style={{ textAlign: 'right' }}>ICMS</th>
                      <th style={{ textAlign: 'right' }}>Valor</th>
                      {entradaDet && <th></th>}
                    </tr>
                  </thead>
                  <tbody>
                    {itens.map((it, idx) => (
                      <tr key={it.id}>
                        <td>{it.numero_item}</td>
                        <td style={{ maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={it.descricao}>{it.descricao}</td>
                        <td className="mono">{it.ncm || '—'}</td>
                        <td><input value={it.cfop || ''} style={{ width: 64, padding: '6px 8px' }} onChange={e => setItens(arr => arr.map((x, i) => i === idx ? { ...x, cfop: e.target.value } : x))} /></td>
                        {entradaDet && <td><Dropdown value={it.tipo_sped || ''} onChange={v => setItens(arr => arr.map((x, i) => i === idx ? { ...x, tipo_sped: v } : x))} options={spedOpts} /></td>}
                        <td className="mono" style={{ textAlign: 'right' }}>{Number(it.quantidade || 0).toLocaleString('pt-BR')}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{brl(it.valor_unitario)}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{brl(it.valor_desconto)}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{brl(it.valor_frete)}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{brl(it.base_calculo)}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{brl(it.valor_icms)}</td>
                        <td className="mono" style={{ textAlign: 'right' }}>{brl(it.valor_total)}</td>
                        {entradaDet && <td><button type="button" className="btn btn-icon" title="Salvar CFOP→Tipo como regra De/Para" onClick={() => salvarRegraItem(it)}><i className="ti ti-bookmark-plus" /></button></td>}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* ADR-0001: CT-es vinculados (se NF-e) / NF-es transportadas (se CT-e) */}
              {detalhe.ctes_vinculados?.length > 0 && (
                <>
                  <div className="section-label" style={{ marginTop: 18 }}><i className="ti ti-truck" /> CT-es Vinculados ({detalhe.ctes_vinculados.length})</div>
                  <div className="tbl-wrap">
                    <table className="table" style={{ minWidth: 640 }}>
                      <thead><tr><th>Chave</th><th>Transportador</th><th style={{ textAlign: 'right' }}>Frete (vTPrest)</th><th style={{ width: 40 }} /></tr></thead>
                      <tbody>
                        {detalhe.ctes_vinculados.map(c => (
                          <tr key={c.chave_cte}>
                            <td className="mono" style={{ fontSize: 11 }}>{c.chave_cte}</td>
                            <td>{c.transportador || '—'}</td>
                            <td className="mono" style={{ textAlign: 'right' }}>{brl(c.vtprest)}</td>
                            <td>{c.nota_id && <button type="button" className="btn btn-icon" title="Abrir CT-e" onClick={() => abrir(c.nota_id)}><i className="ti ti-external-link" /></button>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
              {detalhe.nfes_transportadas?.length > 0 && (
                <>
                  <div className="section-label" style={{ marginTop: 18 }}><i className="ti ti-file-invoice" /> NF-es Transportadas ({detalhe.nfes_transportadas.length})</div>
                  <div className="tbl-wrap">
                    <table className="table" style={{ minWidth: 640 }}>
                      <thead><tr><th>Chave</th><th>Fornecedor</th><th>NF-e</th><th style={{ width: 40 }} /></tr></thead>
                      <tbody>
                        {detalhe.nfes_transportadas.map(nf => (
                          <tr key={nf.chave_nfe}>
                            <td className="mono" style={{ fontSize: 11 }}>{nf.chave_nfe}</td>
                            <td>{nf.fornecedor || '—'}</td>
                            <td className="mono">{nf.numero || '—'}</td>
                            <td>{nf.nota_id && <button type="button" className="btn btn-icon" title="Abrir NF-e" onClick={() => abrir(nf.nota_id)}><i className="ti ti-external-link" /></button>}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
            <div className="modal-footer" style={{ justifyContent: 'space-between' }}>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-secondary btn-sm" onClick={() => baixar('xml')}><i className="ti ti-file-code" /> XML</button>
                <button className="btn btn-secondary btn-sm" onClick={() => baixar('danfe')}><i className="ti ti-file-type-pdf" /> DANFE</button>
                {detalhe.status !== 'cancelada'
                  ? <button className="btn btn-danger btn-sm" onClick={cancelarNota}><i className="ti ti-ban" /> Cancelar</button>
                  : null}
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button className="btn btn-ghost" onClick={() => setDetalhe(null)}>Fechar</button>
                <button className="btn btn-primary" onClick={salvar} disabled={savingD}>{savingD ? 'Salvando…' : 'Salvar'}</button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
