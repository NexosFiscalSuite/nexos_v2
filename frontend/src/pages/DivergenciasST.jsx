import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import Dropdown from '../components/Dropdown'
import { api, saveBlob } from '../api'
import ErroCarga from '../components/ErroCarga'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useToast, ToastContainer } from '../hooks/useToast'
import { TOUR_ADVANCE_EVENT } from '../tourDemo'

const PAGE_SIZE = 200
const cnpjFmt = (c) => (c && c.length === 14 ? c.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5') : c || '—')
// Diferença com SINAL explícito no positivo ("+R$ 84,60"): a favor × a recolher
// se distinguem no primeiro caractere, não só na cor (padrão fintech).
const brlDif = (v) => (Number(v || 0) > 0.004 ? `+${brl(v)}` : brl(v))
// Zero em coluna de dinheiro é ruído: classe muda o peso visual.
const classeValor = (v) => `tnum${Math.abs(Number(v || 0)) < 0.005 ? ' val-zero' : ''}`

// Cards do topo: o dinheiro em jogo por tipo de pendência. Clicar filtra a
// lista (sobre os itens carregados) — mesmo padrão dos cards do IBS/CBS.
const CARDS = [
  { key: 'a_recolher', label: 'ST a recolher', tone: 'err', icon: 'ti-receipt-tax', dinheiro: true,
    filtro: it => it.status === 'DIVERGENTE' && Number(it.diferenca) < 0 && !(it.codigo_erro || '').includes('ERRO_111') },
  { key: 'a_favor', label: 'Pago a maior (a favor)', tone: 'info', icon: 'ti-arrow-back-up', dinheiro: true,
    filtro: it => it.status === 'DIVERGENTE' && Number(it.diferenca) > 0 },
  { key: 'antecipacao', label: 'Antecipação devida (guia própria)', tone: 'warn', icon: 'ti-receipt-tax', dinheiro: true,
    filtro: it => (it.codigo_erro || '').includes('ERRO_111') },
  { key: 'nao_auditaveis', label: 'Não auditáveis (pendência)', tone: 'warn', icon: 'ti-help-circle', dinheiro: false,
    filtro: it => it.status === 'NAO_AUDITAVEL' },
]

// "Como verificar AQUI na plataforma" — o roteiro por código de erro que a
// ação sugerida sozinha não dá (o balão deixa de ser seco).
const COMO_VERIFICAR = {
  ERRO_101: [
    'Abra a memória de cálculo: o passo 2 mostra a MVA original × aplicada e o motivo do (não) ajuste.',
    'Operação interna ou emitente do Simples NÃO ajustam MVA — se a nota ajustou, a retenção veio a maior.',
  ],
  ERRO_102: [
    'Abra a memória de cálculo: o passo 3 mostra o custo aberto (produto + frete — com a parcela dos CT-e — + IPI − desconto).',
    'Compare com a base "Na nota" no quadro Onde nasce a diferença: o valor que falta costuma ser exatamente o frete do CT-e ou o IPI que o fornecedor não somou.',
  ],
  ERRO_103: [
    'Abra a memória de cálculo: o passo 5 mostra qual dedução o motor usou (real, teórica do Simples, isenta).',
    'Confira o CRT do emitente e o CST da operação própria no detalhe da nota (tela Notas).',
  ],
  ERRO_104: [
    'Abra a memória de cálculo: se MVA e base conferem no quadro, o erro está só na conta final do fornecedor.',
    'Diferença negativa = complemento a cobrar; positiva = ressarcimento a pleitear.',
  ],
  ERRO_105: [
    'Abra a memória de cálculo: a trilha do FCP-ST mostra débito − FCP próprio = devido.',
    'Confira na aba FCP das Matrizes se a alíquota da UF/NCM está vigente na data da nota.',
  ],
  ERRO_107: [
    'A operação própria veio zerada no XML (vICMS/vBC) — o motor recalculou a dedução esperada.',
    'Peça a correção da operação própria ao fornecedor; o detalhe do item está na tela Notas.',
  ],
  ERRO_109: [
    'O produto tem MVA cadastrada, mas o XML usou base sem MVA (modBCST=6) — base subdimensionada.',
    'A memória mostra a base recalculada COM a MVA; a diferença é o complemento a exigir.',
  ],
}

function comoVerificar(codigoErro) {
  for (const [pref, passos] of Object.entries(COMO_VERIFICAR)) {
    if ((codigoErro || '').includes(pref)) return passos
  }
  return null
}

// Diagnóstico automático do ERRO_102: cruza a diferença de base com os
// componentes do custo (memórias novas) e aponta a causa provável.
function diagnosticoAutomatico(it) {
  const m = it.memoria || {}
  if (!(it.codigo_erro || '').includes('ERRO_102') || m.custo_produto == null) return null
  const fator = 1 + Number(m.mva_aplicada || 0) / 100
  const difBase = Math.abs(Number(it.vbc_st_xml || 0) - Number(it.vbc_st_calculado || 0))
  if (difBase < 0.05) return null
  const candidatos = [
    ['o frete rateado dos CT-e', Number(m.custo_frete_cte || 0)],
    ['o IPI', Number(m.custo_ipi || 0)],
    ['o frete total', Number(m.custo_frete || 0)],
    ['o frete dos CT-e somado ao IPI', Number(m.custo_frete_cte || 0) + Number(m.custo_ipi || 0)],
  ].filter(([, v]) => v > 0.004)
  for (const [nome, v] of candidatos) {
    const esperado = v * fator
    if (Math.abs(difBase - esperado) <= Math.max(0.05, esperado * 0.01)) {
      return `A diferença de base (${brl(difBase)}) bate com ${nome} (${brl(v)} × margem de ${pct(m.mva_aplicada)}): provável que o fornecedor não somou ${nome} na base do ST.`
    }
  }
  return null
}

// Pendência de matriz faltante → deep-link para a aba certa das Matrizes,
// já pré-preenchida (o modal abre pronto para salvar; depois é só reprocessar).
function linkMatriz(item) {
  const cod = item.codigo_erro || ''
  const q = (params) => '/matrizes-fiscais?' + new URLSearchParams(
    Object.entries(params).filter(([, v]) => v)
  ).toString()
  if (cod.includes('ERRO_MVA_NAO_ENCONTRADA'))
    // Leva a origem junto: a MVA muda conforme o estado remetente, então abrir
    // o modal em "Qualquer origem" cadastraria uma regra geral no lugar da
    // regra do par que gerou a divergência.
    return q({ aba: 'mva', ncm: item.ncm, cest: item.cest,
               uf_origem: item.uf_origem, uf_destino: item.uf_destino })
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

// Selo de situação: DESCRITIVO, não acusatório — a divergência pode ter causa
// legítima (dispensa de retenção pelo estado/regime do remetente); a culpa só
// se afirma depois de verificar. O selo diz O QUE aconteceu com o imposto.
function seloAcao(item) {
  if (item.status === 'NAO_AUDITAVEL')
    return { txt: 'Não auditável', cls: 'badge-neutral', icon: 'ti-help-circle' }
  const cod = item.codigo_erro || ''
  if (cod.includes('ERRO_111'))
    return { txt: 'Antecipação devida', cls: 'badge-warn', icon: 'ti-receipt-tax' }
  if (cod.includes('ERRO_110'))
    return { txt: 'A favor do cliente', cls: 'badge-info', icon: 'ti-arrow-back-up' }
  if (item.status === 'DIVERGENTE') {
    if (Number(item.diferenca || 0) > 0.004)
      return { txt: 'Pago a maior', cls: 'badge-info', icon: 'ti-arrow-back-up' }
    return item.fluxo === 'saida'
      ? { txt: 'Complemento a recolher', cls: 'badge-error', icon: 'ti-receipt-tax' }
      : { txt: 'ST a recolher', cls: 'badge-error', icon: 'ti-receipt-tax' }
  }
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

// ── Triagem: o que o escritório decidiu sobre o item divergente ──
const TRIAGEM_BADGE = {
  COBRADA: { label: 'Cobrada', cls: 'badge-primary', icon: 'ti-mail-forward' },
  JUSTIFICADA: { label: 'Justificada', cls: 'badge-ok', icon: 'ti-scale' },
  ACEITA: { label: 'Aceita', cls: 'badge-warn', icon: 'ti-cash' },
}
const TRIAGEM_OPTS = [
  { value: 'EM_ABERTO', label: 'Em aberto — sem decisão' },
  { value: 'COBRADA', label: 'Cobrada — carta/contato com o fornecedor' },
  { value: 'JUSTIFICADA', label: 'Justificada — base normativa aceita (baixa)' },
  { value: 'ACEITA', label: 'Aceita — o cliente assume e recolhe' },
]

function TriagemModal({ item, onClose, onSalvar }) {
  const [status, setStatus] = useState(item.triagem?.status || 'EM_ABERTO')
  const [obs, setObs] = useState(item.triagem?.observacao || '')
  const [busy, setBusy] = useState(false)
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
        <div className="modal-header">
          <h2><i className="ti ti-tag" style={{ marginRight: 8 }} />Triagem do item</h2>
          <button className="btn btn-icon" onClick={onClose}><i className="ti ti-x" /></button>
        </div>
        <div className="modal-body">
          <p style={{ fontSize: 13, fontWeight: 600, margin: '0 0 2px' }}>{item.descricao || `Item ${item.numero_item}`}</p>
          <p style={{ fontSize: 12, color: 'var(--text-4)', margin: '0 0 14px' }}>
            NF-e {item.numero_nota || '—'} · item {item.numero_item} · {item.fornecedor || ''}
          </p>
          <div className="field">
            <label>O que foi decidido?</label>
            <Dropdown value={status} onChange={setStatus} options={TRIAGEM_OPTS} />
          </div>
          <div className="field">
            <label>Observação (opcional)</label>
            <input value={obs} onChange={e => setObs(e.target.value)} maxLength={300}
              placeholder="ex.: fornecedor apresentou regime especial nº…" />
          </div>
          {item.triagem && (
            <p style={{ fontSize: 12, color: 'var(--text-4)', margin: 0 }}>
              Registro atual: {TRIAGEM_BADGE[item.triagem.status]?.label || item.triagem.status} por {item.triagem.por || '—'}
              {item.triagem.em ? ` em ${new Date(item.triagem.em).toLocaleDateString('pt-BR')}` : ''}
            </p>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" disabled={busy}
            onClick={async () => { setBusy(true); try { await onSalvar(item, status, obs) } finally { setBusy(false) } }}>
            {busy ? 'Salvando…' : 'Salvar triagem'}
          </button>
        </div>
      </div>
    </div>
  )
}

function ConfirmacaoPendenciaModal({ alvo, busy, onClose, onConfirmar }) {
  const semAcordo = alvo.tipo === 'sem-acordo'
  const it = alvo.item
  const titulo = semAcordo ? 'Registrar ausência de acordo?' : 'Confirmar ausência de CT-e?'
  const referencia = semAcordo
    ? `${it.uf_origem || '—'} → ${it.uf_destino || '—'}`
    : `NF-e ${it.numero_nota || 'sem número'}`

  return (
    <div className="modal-overlay" onClick={busy ? undefined : onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 560 }} role="dialog" aria-modal="true" aria-labelledby="confirmacao-pendencia-titulo">
        <div className="modal-header">
          <div>
            <div style={{ color: 'var(--warn-text)', fontSize: 10.5, fontWeight: 700, letterSpacing: 0.7, textTransform: 'uppercase', marginBottom: 3 }}>
              {semAcordo ? 'Curadoria de protocolo/convênio' : 'Tratamento de frete'}
            </div>
            <h2 id="confirmacao-pendencia-titulo" style={{ margin: 0 }}>{titulo}</h2>
          </div>
          <button className="btn btn-icon" disabled={busy} onClick={onClose} aria-label="Fechar"><i className="ti ti-x" /></button>
        </div>
        <div className="modal-body">
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: 14, borderRadius: 'var(--radius)', background: 'var(--warn-bg)', color: 'var(--warn-text)', marginBottom: 16 }}>
            <span style={{ width: 38, height: 38, borderRadius: 10, display: 'inline-flex', alignItems: 'center', justifyContent: 'center', background: 'var(--surface)', flexShrink: 0 }}>
              <i className={`ti ${semAcordo ? 'ti-route-off' : 'ti-truck-off'}`} style={{ fontSize: 20 }} />
            </span>
            <div>
              <div style={{ fontSize: 11, opacity: 0.8 }}>{semAcordo ? 'Par interestadual' : 'Documento analisado'}</div>
              <strong className="tnum" style={{ fontSize: 18 }}>{referencia}</strong>
            </div>
          </div>

          <p style={{ margin: '0 0 14px', color: 'var(--text-2)', fontSize: 13.5, lineHeight: 1.6 }}>
            {semAcordo
              ? 'Use esta decisão somente após confirmar que não existe protocolo ou convênio de ICMS-ST aplicável ao par de UFs.'
              : 'Use esta decisão quando o frete é do destinatário, mas não existe CT-e relacionado a esta compra.'}
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: 10 }}>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 12 }}>
              <div style={{ color: 'var(--text-4)', fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', marginBottom: 5 }}>Efeito no cálculo</div>
              <div style={{ color: 'var(--text-2)', fontSize: 12.5, lineHeight: 1.5 }}>
                {semAcordo
                  ? 'As notas do par serão reauditadas como antecipação do destinatário.'
                  : 'A nota será reauditada sem adicionar frete proveniente de conhecimento.'}
              </div>
            </div>
            <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: 12 }}>
              <div style={{ color: 'var(--text-4)', fontSize: 10.5, fontWeight: 700, textTransform: 'uppercase', marginBottom: 5 }}>Rastreabilidade</div>
              <div style={{ color: 'var(--text-2)', fontSize: 12.5, lineHeight: 1.5 }}>
                {semAcordo
                  ? 'A ausência do acordo fica registrada na matriz com vigência.'
                  : 'A confirmação fica vinculada ao seu usuário, com data e hora.'}
              </div>
            </div>
          </div>
        </div>
        <div className="modal-footer">
          <button className="btn btn-ghost" disabled={busy} onClick={onClose}>Cancelar</button>
          <button className="btn btn-primary" disabled={busy} onClick={onConfirmar}
            data-tour={semAcordo ? 'st-confirmar-sem-acordo' : 'st-confirmar-sem-cte'}>
            {busy
              ? <><span className="spinner" style={{ width: 13, height: 13 }} /> Processando…</>
              : <><i className="ti ti-check" /> {semAcordo ? 'Registrar sem acordo' : 'Confirmar sem CT-e'}</>}
          </button>
        </div>
      </div>
    </div>
  )
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
  const [confirmacao, setConfirmacao] = useState(null)
  const [confirmacaoBusy, setConfirmacaoBusy] = useState(false)

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
  const [fTriagem, setFTriagem] = useState('')
  useEffect(() => { const t = setTimeout(() => setQ(busca.trim()), 400); return () => clearTimeout(t) }, [busca])

  const params = useCallback((page = 1) => ({
    fluxo: tab, data_inicio: `${ano}-${mes}-01`, data_fim: `${ano}-${mes}-31`,
    status: fStatus, codigo_erro: fCodigo, triagem: fTriagem, q,
    page, page_size: PAGE_SIZE,
  }), [tab, ano, mes, fStatus, fCodigo, fTriagem, q])

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
      await carregar()
    } catch (e) { toast(e.message, 'error') }
    finally { setReproBusy(false) }
  }

  // "Não há acordo": registra a ausência de protocolo no par de UFs (linha
  // SEM_ACORDO — cura o par sem criar acordo) e reaudita na sequência.
  async function registrarSemAcordo(it) {
    try {
      await api.criarMatrizProtocolo({
        uf_origem: it.uf_origem, uf_destino: it.uf_destino,
        numero_acordo: 'SEM ACORDO (registro do escritório)',
        situacao: 'SEM_ACORDO',
        data_inicio_vigencia: '2000-01-01', data_fim_vigencia: null,
      })
      toast(`Registrado: sem acordo ${it.uf_origem}→${it.uf_destino}. Reprocessando…`, 'ok')
      await reprocessar()
      return true
    } catch (e) { toast(e.message, 'error') }
    return false
  }

  // Triagem manual por item (o endpoint é o mesmo da marcação automática da carta).
  const [triagemAlvo, setTriagemAlvo] = useState(null)
  async function salvarTriagem(item, status, observacao) {
    try {
      await api.stDefinirTriagem(
        selectedEmpresa.id,
        [{ nota_id: item.nota_id, numero_item: item.numero_item }],
        status, observacao,
      )
      toast(status === 'EM_ABERTO'
        ? 'Triagem desfeita — item de volta ao “em aberto”.'
        : 'Triagem registrada — fica na trilha quem decidiu e quando.', 'ok')
      setTriagemAlvo(null)
      carregar()
    } catch (e) { toast(e.message, 'error') }
  }

  // "Não há CT-e": confirma a ausência (fica registrado quem/quando) e reaudita.
  async function confirmarSemCte(it) {
    try {
      await api.stConfirmarSemCte(it.nota_id)
      toast('Confirmado — nota reauditada sem CT-e.', 'ok')
      await carregar()
      return true
    } catch (e) { toast(e.message, 'error') }
    return false
  }

  async function executarConfirmacao() {
    if (!confirmacao) return
    setConfirmacaoBusy(true)
    try {
      const ok = confirmacao.tipo === 'sem-acordo'
        ? await registrarSemAcordo(confirmacao.item)
        : await confirmarSemCte(confirmacao.item)
      if (ok) {
        setConfirmacao(null)
        window.dispatchEvent(new Event(TOUR_ADVANCE_EVENT))
      }
    } finally { setConfirmacaoBusy(false) }
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
      toast('Carta gerada — itens marcados como “Cobrada” na triagem.', 'ok')
      carregar()
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

  // Aviso de legislação vigente (Fase 2): antes de emitir carta/planilha, o
  // usuário confirma que conferiu a norma — e a confirmação fica na trilha de
  // auditoria (quem/quando), no padrão da confirmação de nota sem CT-e.
  const [ciencia, setCiencia] = useState(null)   // { destino: 'carta'|'export', cnpj? }
  async function confirmarCiencia() {
    const alvo = ciencia
    setCiencia(null)
    try { await api.stCienciaLegislacao(selectedEmpresa.id, alvo.destino, `${mes}/${ano}`) }
    catch { /* a trilha não bloqueia a emissão */ }
    if (alvo.destino === 'carta') await gerarCarta(alvo.cnpj)
    else await exportarExcel()
  }

  const [filtroCard, setFiltroCard] = useState(null)
  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setExpandido(new Set()); setFiltroCard(null) }, [selectedEmpresa, ano, mes, tab, q, fStatus, fCodigo, fTriagem])

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
          <button className="btn btn-secondary" disabled={expBusy || data.total === 0} onClick={() => setCiencia({ destino: 'export' })}
            title="Planilha Excel do filtro atual (todas as páginas): itens + consolidação por fornecedor">
            <i className="ti ti-file-spreadsheet" /> {expBusy ? 'Exportando…' : 'Exportar Excel'}
          </button>
          <button className="btn btn-secondary" data-tour="st-reprocessar" disabled={reproBusy} onClick={reprocessar}
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
        <div style={{ width: 190 }}>
          <Dropdown value={fTriagem} onChange={setFTriagem} options={[
            { value: '', label: 'Toda triagem' },
            { value: 'EM_ABERTO', label: 'Em aberto (sem decisão)' },
            { value: 'COBRADA', label: 'Cobradas (carta enviada)' },
            { value: 'JUSTIFICADA', label: 'Justificadas (baixadas)' },
            { value: 'ACEITA', label: 'Aceitas (cliente recolhe)' },
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
            <div data-tour="st-cards" style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 18 }}>
              {CARDS.map(c => {
                const ativo = filtroCard === c.key
                return (
                  <div key={c.key} className="card kpi-click" role="button"
                    title={`${c.label} — clique para filtrar a lista`}
                    onClick={() => setFiltroCard(f => (f === c.key ? null : c.key))}
                    style={{ padding: 16, display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
                             boxShadow: ativo ? `inset 0 0 0 2px var(--${c.tone}-text)` : undefined }}>
                    <span className="kpi-icon" style={{ background: `var(--${c.tone}-bg)`, color: `var(--${c.tone}-text)` }}>
                      <i className={`ti ${c.icon}`} />
                    </span>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 2, minWidth: 0 }}>
                      <span style={{ fontSize: 12, color: 'var(--text-3)' }}>
                        {c.label}
                        {ativo && <i className="ti ti-filter" style={{ marginLeft: 6, color: `var(--${c.tone}-text)` }} />}
                      </span>
                      <span className="tnum" style={{ fontSize: 22, fontWeight: 800, letterSpacing: '-0.3px', color: `var(--${c.tone}-text)` }}>
                        {c.dinheiro ? brl(data.resumo[c.key]) : (data.resumo[c.key] ?? 0)}
                      </span>
                      <span style={{ fontSize: 11, color: 'var(--text-4)' }}>
                        {c.key === 'nao_auditaveis'
                          ? `${data.resumo.divergentes ?? 0} divergente(s) no período`
                          : 'total do período (todas as páginas)'}
                      </span>
                    </div>
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
                            onClick={() => setCiencia({ destino: 'carta', cnpj: f.cnpj })}>
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
                {notas.map((nota, i) => {
                  const aberto = expandido.has(nota.chave)
                  return (
                    <FragmentoNota
                      key={nota.chave} nota={nota} aberto={aberto} catalogo={catalogo}
                      onToggle={() => toggle(nota.chave)} onMemoria={setDetalhe}
                      onSemAcordo={item => setConfirmacao({ tipo: 'sem-acordo', item })}
                      onSemCte={item => setConfirmacao({ tipo: 'sem-cte', item })}
                      onTriagem={setTriagemAlvo}
                      dataTour={['st-nota-demo', 'st-nota-demo2', 'st-nota-demo3'][i]}
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

      {triagemAlvo && (
        <TriagemModal item={triagemAlvo} onClose={() => setTriagemAlvo(null)} onSalvar={salvarTriagem} />
      )}

      {confirmacao && (
        <ConfirmacaoPendenciaModal
          alvo={confirmacao}
          busy={confirmacaoBusy}
          onClose={() => setConfirmacao(null)}
          onConfirmar={executarConfirmacao}
        />
      )}

      {/* Ciência do aviso de legislação antes de emitir (com trilha) */}
      {ciencia && (
        <div className="modal-overlay" onClick={() => setCiencia(null)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 480 }}>
            <div className="modal-header">
              <h2><i className="ti ti-scale" style={{ marginRight: 8 }} />Confira a legislação vigente</h2>
              <button className="btn btn-icon" onClick={() => setCiencia(null)}><i className="ti ti-x" /></button>
            </div>
            <div className="modal-body">
              <p style={{ fontSize: 13.5, lineHeight: 1.6, margin: 0 }}>
                Os valores {ciencia.destino === 'carta' ? 'da carta' : 'da planilha'} saem das
                regras cadastradas nas Matrizes Fiscais (MVA, alíquotas, protocolos e convênios).
                Legislação muda: antes de emitir, confirme que não houve alteração recente
                que afete estes cálculos.
              </p>
              <p style={{ fontSize: 12.5, color: 'var(--text-3)', lineHeight: 1.55, marginTop: 10, marginBottom: 0 }}>
                A sua confirmação fica registrada na trilha de auditoria (quem confirmou e quando),
                e o documento sai com a data da última verificação da base.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setCiencia(null)}>Cancelar</button>
              <button className="btn btn-primary" onClick={confirmarCiencia}>
                <i className="ti ti-checks" /> Estou ciente — gerar
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// Rótulo pequeno que nomeia a linha do confronto ("NA NOTA" / "DEVIDO").
const RotuloSt = ({ children }) => (
  <span style={{ color: 'var(--text-4)', fontWeight: 600, fontSize: 9.5, textTransform: 'uppercase', letterSpacing: 0.5 }}>{children}</span>
)

// A conduta do analista como selo destacado; o ⓘ abre o balão com a
// explicação técnica do motor (padrão do balão da classificação — clique
// abre, clique fora fecha). Nada de tooltip escondido no hover.
function AcaoSugerida({ acao, destinoMatriz, onIrMatriz, onSemAcordo, verificar, diagnostico, onVerMemoria, ressalva, onImportarCte, onSemCte, seloTour }) {
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
        top: Math.min(r.bottom + 6, window.innerHeight - 200),
        left: Math.min(r.left, window.innerWidth - 420),
      })
    }
    setAberto(a => !a)
  }

  return (
    <div style={{ marginTop: 5, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
      <span className="balao-classif" style={{ position: 'relative', display: 'inline-flex', maxWidth: '100%' }}>
        <button ref={ref} onClick={alternar} data-tour={seloTour} title="Clique para ver a explicação do motor"
          style={{ display: 'inline-flex', alignItems: 'flex-start', gap: 6, maxWidth: '100%',
                   background: 'var(--accent-lt)', color: 'var(--accent-text)', border: 'none',
                   borderRadius: 8, padding: '5px 10px', fontSize: 11.5, fontWeight: 600,
                   lineHeight: 1.45, textAlign: 'left', cursor: 'pointer', fontFamily: 'inherit' }}>
          <i className="ti ti-bulb" style={{ fontSize: 13, flexShrink: 0, marginTop: 1 }} />
          <span>{acao.acao}</span>
          <i className="ti ti-info-circle" style={{ fontSize: 12, opacity: .55, flexShrink: 0, marginTop: 1 }} />
        </button>
        {aberto && pos && (
          <div className="balao-classif" style={{
            position: 'fixed', top: pos.top, left: pos.left, zIndex: 2000, width: 440,
            background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
            boxShadow: '0 10px 30px rgba(0,0,0,.18)', padding: '13px 15px', textAlign: 'left',
          }}>
            <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 6, color: 'var(--text-1)' }}>
              Por que este item foi apontado
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55 }}>{acao.mensagem}</div>

            {diagnostico && (
              <div style={{ marginTop: 8, background: 'var(--info-bg)', color: 'var(--info-text)', borderRadius: 8, padding: '8px 11px', fontSize: 12.5, lineHeight: 1.55 }}>
                <i className="ti ti-sparkles" style={{ marginRight: 4 }} />
                <strong>Diagnóstico:</strong> {diagnostico}
              </div>
            )}

            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-2)', fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55 }}>
              <strong style={{ color: 'var(--accent-text)' }}>O que fazer:</strong> {acao.acao}
            </div>

            {verificar && (
              <div style={{ marginTop: 8, fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.55 }}>
                <strong style={{ color: 'var(--text-1)' }}>Como verificar aqui:</strong>
                <ol style={{ margin: '4px 0 0', paddingLeft: 18 }}>
                  {verificar.map((p, i) => <li key={i} style={{ marginBottom: 3 }}>{p}</li>)}
                </ol>
              </div>
            )}

            {ressalva && (
              <div style={{ marginTop: 8, background: 'var(--warn-bg)', color: 'var(--warn-text)', borderRadius: 8, padding: '8px 11px', fontSize: 12, lineHeight: 1.55 }}>
                <i className="ti ti-scale" style={{ marginRight: 4 }} />{ressalva}
              </div>
            )}

            <div style={{ marginTop: 10, display: 'flex', alignItems: 'center', gap: 8 }}>
              {onVerMemoria && (
                <button className="btn btn-secondary btn-sm" data-tour="st-abrir-memoria" style={{ padding: '3px 10px', fontSize: 11.5 }}
                  onClick={(e) => { e.stopPropagation(); setAberto(false); onVerMemoria() }}>
                  <i className="ti ti-calculator" /> Abrir memória de cálculo
                </button>
              )}
              <span className="mono" style={{ marginLeft: 'auto', fontSize: 10.5, color: 'var(--text-4)' }}>{acao.cod}</span>
            </div>
          </div>
        )}
      </span>
      {destinoMatriz && (
        <button className="btn btn-secondary btn-sm" style={{ padding: '3px 10px', fontSize: 11.5 }}
          onClick={(e) => { e.stopPropagation(); onIrMatriz() }}>
          <i className="ti ti-table-plus" /> Cadastrar matriz
        </button>
      )}
      {onSemAcordo && (
        <button className="btn btn-secondary btn-sm" data-tour="st-sem-acordo" style={{ padding: '3px 10px', fontSize: 11.5 }}
          title="Registra na matriz de protocolos que NÃO há acordo entre as UFs (antecipação do destinatário) e reaudita"
          onClick={(e) => { e.stopPropagation(); onSemAcordo() }}>
          <i className="ti ti-ban" /> Não há acordo
        </button>
      )}
      {onImportarCte && (
        <button className="btn btn-secondary btn-sm" style={{ padding: '3px 10px', fontSize: 11.5 }}
          title="Vai para a tela de Upload — importe o CT-e da nota e a auditoria destrava sozinha no reprocesso"
          onClick={(e) => { e.stopPropagation(); onImportarCte() }}>
          <i className="ti ti-truck" /> Importar CT-e
        </button>
      )}
      {onSemCte && (
        <button className="btn btn-secondary btn-sm" data-tour="st-sem-cte" style={{ padding: '3px 10px', fontSize: 11.5 }}
          title="Confirma que NÃO há CT-e para esta nota (fica registrado quem confirmou e quando) e reaudita na hora"
          onClick={(e) => { e.stopPropagation(); onSemCte() }}>
          <i className="ti ti-truck-off" /> Não há CT-e
        </button>
      )}
    </div>
  )
}

// ── Linha-mestre (Nota) + linhas-filhas (itens) quando expandida ──
function FragmentoNota({ nota, aberto, onToggle, onMemoria, catalogo, onSemAcordo, onSemCte, onTriagem, dataTour }) {
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
      <tr onClick={onToggle} data-tour={dataTour} style={{ cursor: 'pointer', background: aberto ? 'var(--surface-2)' : undefined }}>
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
        <td className={classeValor(nota.totalIcmsSt)} style={{ textAlign: 'right' }}>{brl(nota.totalIcmsSt)}</td>
        <td className="tnum" style={{ textAlign: 'right', fontWeight: 700, color: corDiferenca(nota.totalDiferenca) }}>
          {brlDif(nota.totalDiferenca)}
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
        <tr key={it.numero_item} className="filha" style={{ background: 'var(--surface)' }}>
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
              {it.triagem && TRIAGEM_BADGE[it.triagem.status] && (
                <span className={`badge ${TRIAGEM_BADGE[it.triagem.status].cls}`} style={{ fontSize: 10 }}
                  title={`${TRIAGEM_BADGE[it.triagem.status].label} por ${it.triagem.por || '—'}${it.triagem.em ? ` em ${new Date(it.triagem.em).toLocaleDateString('pt-BR')}` : ''}${it.triagem.observacao ? ` — ${it.triagem.observacao}` : ''}`}>
                  <i className={`ti ${TRIAGEM_BADGE[it.triagem.status].icon}`} style={{ marginRight: 3 }} />
                  {TRIAGEM_BADGE[it.triagem.status].label}
                </span>
              )}
              {it.status === 'DIVERGENTE' && onTriagem && (
                <button className="btn btn-icon" title="Triagem do item — registrar cobrada, justificada ou aceita"
                  style={{ padding: 3 }} onClick={(e) => { e.stopPropagation(); onTriagem(it) }}>
                  <i className="ti ti-tag" style={{ fontSize: 14, color: 'var(--text-3)' }} />
                </button>
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
              <AcaoSugerida acao={acao} destinoMatriz={destinoMatriz}
                seloTour={dataTour ? `${dataTour}-selo` : undefined}
                onIrMatriz={() => navigate(destinoMatriz)}
                onSemAcordo={(it.codigo_erro || '').includes('ERRO_PROTOCOLO_NAO_AVALIADO')
                  ? () => onSemAcordo(it) : null}
                verificar={comoVerificar(it.codigo_erro)}
                diagnostico={diagnosticoAutomatico(it)}
                onVerMemoria={it.memoria ? () => onMemoria(it) : null}
                onImportarCte={(it.codigo_erro || '').includes('ERRO_FRETE_PENDENTE_CTE')
                  ? () => navigate('/upload') : null}
                onSemCte={(it.codigo_erro || '').includes('ERRO_FRETE_PENDENTE_CTE')
                  ? () => onSemCte(it) : null}
                ressalva={it.fluxo !== 'saida' && it.status === 'DIVERGENTE'
                  && !(it.codigo_erro || '').match(/ERRO_110|ERRO_111/)
                  ? 'Antes de cobrar: a retenção pode ser legitimamente dispensada conforme o estado ou o regime do remetente (acordo não aplicável ao produto, regime especial, inscrição de substituto). Se for o caso, a obrigação vira antecipação nossa — confirme o enquadramento do par de UFs antes de contestar.'
                  : null} />
            )}
          </td>
          <td colSpan={2}>
            <div style={{ display: 'inline-grid', gridTemplateColumns: 'auto auto', columnGap: 7, rowGap: 1, alignItems: 'baseline', lineHeight: 1.5 }}>
              <RotuloSt>na nota</RotuloSt>
              <span className={classeValor(it.vicms_st_xml)} style={{ fontSize: 12.5, color: 'var(--text-3)' }}>{brl(it.vicms_st_xml)}</span>
              <RotuloSt>devido</RotuloSt>
              <span className="tnum" style={{ fontSize: 12.5, fontWeight: 700 }}>{brl(it.vicms_st_calculado)}</span>
            </div>
          </td>
          <td className={classeValor(it.vicms_st_calculado)} style={{ textAlign: 'right' }}>{brl(it.vicms_st_calculado)}</td>
          <td className="tnum" style={{ textAlign: 'right', fontWeight: 600, color: corDiferenca(it.diferenca) }}>{brlDif(it.diferenca)}</td>
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

  // Custo aproximado da compra (base ÷ (1 + MVA)): deixa o passo 3 concreto.
  const mvaApl = Number(m.mva_aplicada)
  const custoAprox = (m.base_st_calculada != null && Number(m.base_st_calculada) > 0
    && !Number.isNaN(mvaApl))
    ? Number(m.base_st_calculada) / (1 + mvaApl / 100)
    : null

  // Composição REAL do custo (memórias novas trazem os componentes): a conta
  // aberta que responde "como verificar o rateio de frete/IPI" na plataforma.
  const custoComposicao = m.custo_produto != null ? [
    ['produto', Number(m.custo_produto)],
    ['frete', Number(m.custo_frete || 0)],
    ['seguro', Number(m.custo_seguro || 0)],
    ['outras despesas', Number(m.custo_outras || 0)],
    ['IPI', Number(m.custo_ipi || 0)],
    ['(−) desconto', -Number(m.custo_desconto || 0)],
  ].filter(([, v]) => Math.abs(v) > 0.004) : null
  const freteCte = Number(m.custo_frete_cte || 0)

  const frase = dif < -0.004
    ? <>A nota destacou <b>{brl(d.vicms_st_xml)}</b>, mas pela regra vigente o valor é <b>{brl(d.vicms_st_calculado)}</b> — <b style={{ color: 'var(--err-text)' }}>faltaram {brl(-dif)}</b> de ST.</>
    : dif > 0.004
      ? <>A nota destacou <b>{brl(d.vicms_st_xml)}</b> — <b style={{ color: 'var(--info-text)' }}>{brl(dif)} a mais</b> que o devido ({brl(d.vicms_st_calculado)}): candidato a ressarcimento.</>
      : <>O valor destacado confere com o cálculo.</>

  return (
    <div className="modal-overlay">
      <div className="modal" data-tour="st-memoria" style={{ width: 920, maxWidth: '96%' }}>
        <div className="modal-header">
          <h2><i className="ti ti-calculator" style={{ marginRight: 8 }} />Como chegamos ao valor devido</h2>
          <button className="btn btn-icon" data-tour="st-memoria-fechar" onClick={onClose}><i className="ti ti-x" /></button>
        </div>
        <div className="modal-body">
          {/* Topo em largura total: os 3 números + a conclusão em uma frase. */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 10, marginBottom: 12 }}>
            <Cartao titulo="Destacado na nota" valor={brl(d.vicms_st_xml)} />
            <Cartao titulo="Devido pela regra" valor={brl(d.vicms_st_calculado)} destaque />
            <Cartao titulo="Diferença" valor={brlDif(d.diferenca)} cor={corDiferenca(d.diferenca)} />
          </div>
          <div style={{ background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: '10px 14px', fontSize: 13, lineHeight: 1.55, marginBottom: 18 }}>
            {frase}
          </div>

          {/* Duas colunas: a narrativa do cálculo à esquerda, o veredito etapa
              a etapa (+ FCP) à direita — o modal ganha largura, não altura. */}
          <div className="memoria-grid">
            <div>
              <div className="section-label" style={{ marginBottom: 10 }}>O cálculo, passo a passo</div>

              {/* Passo 1: a operação e DE ONDE VEM cada alíquota (e se foi usada). */}
              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', padding: '12px 14px', marginBottom: 6 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <NumeroPasso n="1" />
                  <div style={{ fontSize: 13, fontWeight: 600 }}>
                    {interna
                      ? <>Venda dentro de {d.uf_destino}</>
                      : <>Venda de {d.uf_origem} para {d.uf_destino}</>}
                    <span style={{ fontWeight: 400, color: 'var(--text-3)' }}> · produto na substituição tributária</span>
                  </div>
                </div>
                <div style={{ marginLeft: 38, marginTop: 8, display: 'grid', gap: 6 }}>
                  <LinhaAliquota
                    nome={`Alíquota interna de ${d.uf_destino || 'destino'}`}
                    valor={pct(m.alq_intra)}
                    desc={m.aliquota_ncm_casado && m.aliquota_ncm_casado !== 'GERAL'
                      ? `alíquota própria do NCM ${m.aliquota_ncm_casado}, e não a geral do estado — é ela que entra no passo 4`
                      : 'usada no passo 4 para calcular o imposto cheio da cadeia — vem da matriz de alíquotas vigente na data da nota'} />
                  <LinhaAliquota
                    nome="Alíquota interestadual"
                    valor={pct(m.alq_inter)}
                    apagada={interna}
                    desc={interna
                      ? 'não entra neste cálculo — a venda não cruza estados'
                      : (Number(m.alq_inter) === 4
                        ? 'usada no ICMS próprio e no ajuste da MVA — 4% indica produto de origem importada (Resolução 13/2012)'
                        : 'usada no ICMS próprio e no ajuste da MVA — 7% ou 12% conforme as regiões de origem e destino')} />
                </div>
              </div>

              <Passo n="2" titulo="Margem presumida (MVA)"
                sub={ajustada
                  ? `A margem original de ${pct(m.mva_original)} é corrigida para ${pct(m.mva_aplicada)} porque a alíquota da compra (${pct(m.alq_inter)}) difere da interna (${pct(m.alq_intra)}) — o ajuste equaliza a carga entre comprar dentro e fora do estado`
                  : 'Quanto a lei presume que o preço vai subir até chegar ao consumidor final — é sobre essa margem que o ST antecipa o imposto'}
                valor={<><span style={{ color: 'var(--text-4)' }}>{pct(m.mva_original)}</span> <i className="ti ti-arrow-right" style={{ fontSize: 12 }} /> <b>{pct(m.mva_aplicada)}</b></>}
                badge={ajustada ? { txt: 'Ajustada', cls: 'badge-info' } : { txt: 'Original', cls: 'badge-ok' }} />
              <Passo n="3" titulo="Base de cálculo do ST"
                sub={custoComposicao
                  ? <>
                      Custo da compra: {custoComposicao.map(([nome, v], i) => (
                        <span key={nome}>{i > 0 && (v < 0 ? ' ' : ' + ')}{v < 0 ? '− ' : ''}{nome} <b className="tnum">{brl(Math.abs(v))}</b></span>
                      ))}
                      {freteCte > 0.004 && <> — sendo <b className="tnum">{brl(freteCte)}</b> de frete rateado dos CT-e vinculados</>}
                      {'. '}Sobre o custo, a margem de {pct(m.mva_aplicada)}.
                    </>
                  : (custoAprox != null
                    ? `Valor da compra (produto + frete e encargos ≈ ${brl(custoAprox)}) acrescido da margem de ${pct(m.mva_aplicada)} — o preço presumido de venda ao consumidor`
                    : 'Valor da compra (produto + frete e encargos) acrescido da margem — o preço presumido de venda ao consumidor')}
                valor={brl(m.base_st_calculada)}
                badge={Number(m.reducao_base_st) > 0
                  ? { txt: `Base reduzida ${pct(m.reducao_base_st)}`, cls: 'badge-info' }
                  : null} />
              <Passo n="4" titulo="Imposto cheio sobre a base"
                sub={`${brl(m.base_st_calculada)} × ${pct(m.alq_intra)} — o ICMS total da cadeia até o consumidor, que o ST antecipa de uma vez`}
                valor={brl(m.icms_st_debito)} />
              <Passo n="5" titulo="(−) Desconto do ICMS próprio"
                sub={`${DEDUCAO_LEIGO[m.deducao_tipo] || 'desconto do imposto da operação própria'} — desconta para não cobrar duas vezes o mesmo imposto`}
                valor={`− ${brl(m.deducao_aplicada)}`} negativo />
              <Passo n="=" titulo="ICMS-ST devido"
                sub="É o que deveria vir destacado no campo vICMSST da nota"
                valor={brl(m.icms_st_calculado)} final />
            </div>

            <div>
              <div className="section-label" style={{ marginBottom: 8 }}>Onde nasce a diferença</div>
              <div style={{ border: '1px solid var(--border)', borderRadius: 'var(--radius)', overflow: 'hidden' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 82px 82px 84px', gap: 8, padding: '6px 12px', background: 'var(--surface-2)', fontSize: 10.5, fontWeight: 600, color: 'var(--text-4)', textTransform: 'uppercase', letterSpacing: 0.4 }}>
                  <span>Etapa</span><span style={{ textAlign: 'right' }}>Na nota</span><span style={{ textAlign: 'right' }}>Pela regra</span><span style={{ textAlign: 'center' }}>Confere?</span>
                </div>
                <LinhaConfronto rotulo="Margem presumida (MVA)" xml={d.pmva_xml} calc={d.pmva_calculada} fmt={pct} tol={0.011} />
                <LinhaConfronto rotulo="Base de cálculo do ST" xml={d.vbc_st_xml} calc={d.vbc_st_calculado} />
                <LinhaConfronto rotulo="ICMS-ST" xml={d.vicms_st_xml} calc={d.vicms_st_calculado} />
                <LinhaConfronto rotulo="FCP-ST" xml={d.vfcp_st_xml} calc={d.vfcp_st_calculado} ultima />
              </div>

              {temFcp && (
                <>
                  <div className="section-label" style={{ margin: '18px 0 10px' }}>FCP-ST (trilha paralela)</div>
                  <Passo n="A" titulo="Débito FCP-ST"
                    sub="Adicional do Fundo de Combate à Pobreza sobre a mesma base presumida do ST"
                    valor={brl(m.fcp_st_debito)} />
                  <Passo n="B" titulo="(−) FCP próprio"
                    sub="Desconta o FCP que já veio pago na operação própria — mesmo princípio do passo 5"
                    valor={`− ${brl(m.fcp_st_deducao)}`} negativo />
                  <Passo n="=" titulo="FCP-ST devido"
                    sub="Recolhido junto com o ICMS-ST na mesma guia"
                    valor={brl(m.fcp_st_calculado)} final />
                </>
              )}
            </div>
          </div>

          {/* Defensibilidade: qual versão do motor e quais linhas de matriz decidiram. */}
          <div style={{ marginTop: 16, paddingTop: 12, borderTop: '1px solid var(--border-2)', fontSize: 11, color: 'var(--text-4)', lineHeight: 1.6 }}>
            <i className="ti ti-shield-check" style={{ marginRight: 4 }} />
            Rastreabilidade: motor v{m.engine_version || '—'} · MVA da matriz {m.mva_matriz_id ? `#${m.mva_matriz_id}` : '—'}{m.mva_base_legal ? ` (${m.mva_base_legal})` : ''} ·
            alíquota da matriz {m.aliquota_matriz_id ? `#${m.aliquota_matriz_id}` : '—'}{m.aliquota_base_legal ? ` (${m.aliquota_base_legal})` : ''} ·
            protocolo: {m.tem_protocolo == null ? 'operação interna (não se aplica)' : m.tem_protocolo ? 'com acordo' : 'sem acordo'}
            {m.protocolo_fonte ? ` (fonte: ${m.protocolo_fonte})` : ''}
            {/* De onde saiu a redução: regra curada do produto ou o que a nota
                declarou. Sem isto o percentual apareceria sem dono. */}
            {m.reducao_fonte === 'matriz'
              ? ` · redução da base ${pct(m.reducao_base_st)} pela matriz do NCM`
              : Number(m.reducao_base_st_xml) > 0
                ? ` · redução da base ${pct(m.reducao_base_st_xml)} conforme a nota (produto sem redução cadastrada na matriz)`
                : ''}
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

function NumeroPasso({ n, final }) {
  return (
    <div style={{
      width: 26, height: 26, borderRadius: '50%', flexShrink: 0, display: 'flex',
      alignItems: 'center', justifyContent: 'center', fontSize: 13, fontWeight: 700,
      background: final ? 'var(--primary)' : 'var(--primary-lt)',
      color: final ? 'var(--primary-contrast)' : 'var(--primary-text)',
    }}>{n}</div>
  )
}

// Uma alíquota do passo 1: nome + valor + DE ONDE VEM / SE FOI USADA.
function LinhaAliquota({ nome, valor, desc, apagada }) {
  return (
    <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, opacity: apagada ? 0.55 : 1 }}>
      <span className="tnum" style={{ fontWeight: 700, fontSize: 13, minWidth: 58, textAlign: 'right' }}>{valor}</span>
      <div style={{ fontSize: 11.5, lineHeight: 1.5 }}>
        <span style={{ fontWeight: 600, color: 'var(--text-2)' }}>{nome}</span>
        <span style={{ color: 'var(--text-4)' }}> — {desc}</span>
      </div>
    </div>
  )
}

function Passo({ n, titulo, sub, valor, badge, negativo, final }) {
  return (
    <div style={{
      padding: '10px 14px', marginBottom: 6,
      borderRadius: 'var(--radius)', background: final ? 'var(--primary-lt)' : 'transparent',
      border: final ? '1px solid var(--primary)' : '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <NumeroPasso n={n} final={final} />
        <div style={{ flex: 1, minWidth: 0, fontSize: 13, fontWeight: 600, display: 'flex', alignItems: 'center', gap: 8 }}>
          {titulo}
          {badge && <span className={`badge ${badge.cls}`} style={{ fontSize: 10 }}>{badge.txt}</span>}
        </div>
        <div className="tnum" style={{
          fontSize: final ? 16 : 14, fontWeight: 700, whiteSpace: 'nowrap',
          color: negativo ? 'var(--err-text)' : (final ? 'var(--primary-text)' : 'var(--text-1)'),
        }}>{valor}</div>
      </div>
      {sub && (
        <div style={{ marginLeft: 38, marginTop: 3, fontSize: 11.5, color: 'var(--text-4)', lineHeight: 1.5 }}>
          {sub}
        </div>
      )}
    </div>
  )
}
