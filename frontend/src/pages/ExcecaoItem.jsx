import { useCallback, useEffect, useState } from 'react'
import ErroCarga from '../components/ErroCarga'
import { useEmpresa } from '../context/EmpresaContext'
import { useToast, ToastContainer } from '../hooks/useToast'
import { api } from '../api'

const PAGE_SIZE = 50
const FORM_VAZIO = {
  codigo_produto: '', data_inicio_vigencia: '', data_fim_vigencia: '',
  tributado_icms: true, lei_icms: '', ativo: true,
}

const dataBr = (s) => (s ? s.split('-').reverse().join('/') : '—')
const badge = (texto, tom) => <span className="badge" style={{
  background: `var(--${tom}-bg)`, color: `var(--${tom}-text)`,
}}>{texto}</span>

function SwitchFiscal({ checked, onChange, label, description }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 20,
      padding: '14px 16px', border: '1px solid var(--border-2)', borderRadius: 12,
      background: 'var(--surface-2)',
    }}>
      <div>
        <div style={{ fontWeight: 650, color: 'var(--text-1)', fontSize: 13 }}>{label}</div>
        <div style={{ color: 'var(--text-4)', fontSize: 12, marginTop: 4 }}>{description}</div>
      </div>
      <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
        style={{
          width: 44, height: 24, padding: 2, border: 'none', borderRadius: 999,
          background: checked ? 'var(--primary)' : 'var(--border)', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: checked ? 'flex-end' : 'flex-start',
          transition: 'all .18s ease', flexShrink: 0,
        }}>
        <span style={{ width: 20, height: 20, borderRadius: '50%', background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,.2)' }} />
      </button>
    </div>
  )
}

export default function ExcecaoItem() {
  const { selectedEmpresa } = useEmpresa()
  const { toasts, toast } = useToast()
  const [lista, setLista] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [codigo, setCodigo] = useState('')
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [modal, setModal] = useState(false)
  const [editId, setEditId] = useState(null)
  const [form, setForm] = useState(FORM_VAZIO)
  const [saving, setSaving] = useState(false)

  const empresaId = selectedEmpresa?.id
  const nomeEmpresa = selectedEmpresa?.nome_fantasia || selectedEmpresa?.razao_social

  const carregar = useCallback(async () => {
    if (!empresaId) {
      setLista([]); setTotal(0); setErro(null); setLoading(false)
      return
    }
    setLoading(true); setErro(null)
    try {
      const r = await api.excecoesItem({ empresa_id: empresaId, codigo, page, page_size: PAGE_SIZE })
      setLista(r?.items || []); setTotal(r?.total || 0)
    } catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [empresaId, codigo, page])

  useEffect(() => { carregar() }, [carregar])
  useEffect(() => { setPage(1); setModal(false); setEditId(null) }, [empresaId])

  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))
  const setCampo = (campo, valor) => setForm(f => ({ ...f, [campo]: valor }))

  function nova() {
    if (!empresaId) return
    setEditId(null); setForm(FORM_VAZIO); setModal(true)
  }

  function editar(item) {
    setEditId(item.id)
    setForm({
      codigo_produto: item.codigo_produto,
      data_inicio_vigencia: item.data_inicio_vigencia,
      data_fim_vigencia: item.data_fim_vigencia || '',
      tributado_icms: Boolean(item.tributado_icms),
      lei_icms: item.lei_icms || '', ativo: Boolean(item.ativo),
    })
    setModal(true)
  }

  async function salvar(e) {
    e.preventDefault(); setSaving(true)
    try {
      const payload = {
        ...form, empresa_id: empresaId, descricao_produto: null, ncm: null,
        data_fim_vigencia: form.data_fim_vigencia || null,
        lei_icms: form.lei_icms.trim() || null,
      }
      if (editId) await api.editarExcecaoItem(editId, payload)
      else await api.criarExcecaoItem(payload)
      toast(`Exceção ${editId ? 'atualizada' : 'cadastrada'} e notas reprocessadas.`, 'ok')
      setModal(false); setEditId(null); await carregar()
    } catch (e2) { toast(e2.message, 'error') }
    finally { setSaving(false) }
  }

  async function remover(item) {
    if (!confirm(`Remover a exceção do item ${item.codigo_produto}?`)) return
    try {
      await api.removerExcecaoItem(item.id)
      toast('Exceção removida e notas reprocessadas.', 'ok'); await carregar()
    } catch (e) { toast(e.message, 'error') }
  }

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Exceção do Item</h1>
          <p className="page-breadcrumb">Defina por código do produto se o tratamento é Tributado ICMS ou ICMS-ST</p>
        </div>
        <button className="btn btn-primary" data-tour="matrizes-excecao-nova" disabled={!empresaId} onClick={nova}>
          <i className="ti ti-plus" /> Nova exceção do item
        </button>
      </div>

      {selectedEmpresa && <div style={{
        display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', marginBottom: 16,
        background: 'var(--info-bg)', border: '1px solid color-mix(in srgb, var(--info-text) 18%, transparent)',
        borderRadius: 12, color: 'var(--text-2)',
      }}>
        <i className="ti ti-building-store" style={{ fontSize: 20, color: 'var(--info-text)' }} />
        <div style={{ fontSize: 13 }}>
          Exceções de <strong style={{ color: 'var(--text-1)' }}>{nomeEmpresa}</strong>
          <span style={{ color: 'var(--text-4)' }}> — para trocar, use o seletor no canto superior.</span>
        </div>
      </div>}

      <div data-tour="matrizes-painel-excecoes">
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 14 }}>
          <div style={{ position: 'relative' }}>
            <i className="ti ti-search" style={{ position: 'absolute', left: 12, top: 10, color: 'var(--text-4)' }} />
            <input value={codigo} disabled={!empresaId} placeholder="Pesquisar código do item…"
              onChange={e => { setCodigo(e.target.value); setPage(1) }}
              style={{ width: 300, paddingLeft: 36 }} />
          </div>
          {total > 0 && <span className="tnum" style={{ alignSelf: 'center', color: 'var(--text-3)', fontSize: 13 }}>{total.toLocaleString('pt-BR')} exceção(ões)</span>}
        </div>

        {!selectedEmpresa ? <div className="empty-state card">
          <i className="ti ti-building-store" />
          <p className="empty-title">Selecione uma empresa</p>
          <p className="empty-subtitle">Escolha a empresa no canto superior para acessar as exceções dos produtos dela.</p>
        </div> : loading ? <div className="center-loader"><div className="spinner" /></div>
          : erro ? <ErroCarga mensagem={erro} onRetry={carregar} />
            : lista.length === 0 ? <div className="empty-state card">
              <i className="ti ti-adjustments-exclamation" />
              <p className="empty-title">Nenhuma exceção cadastrada</p>
              <p className="empty-subtitle">Cadastre apenas os produtos que precisam contrariar o enquadramento geral por NCM/CEST.</p>
            </div> : <div className="card" style={{ padding: 0 }}><div className="tbl-wrap"><table className="tbl">
              <thead><tr><th>Código Item</th><th>Início</th><th>Fim</th><th>Tratamento</th><th>Lei ICMS</th><th>Ativo</th><th></th></tr></thead>
              <tbody>{lista.map(item => <tr key={item.id} onClick={() => editar(item)} style={{ cursor: 'pointer' }}>
                <td className="mono" style={{ fontWeight: 650 }}>{item.codigo_produto}</td>
                <td>{dataBr(item.data_inicio_vigencia)}</td><td>{dataBr(item.data_fim_vigencia)}</td>
                <td>{badge(item.tributado_icms ? 'Tributado ICMS' : 'ICMS-ST', item.tributado_icms ? 'info' : 'warn')}</td>
                <td style={{ color: 'var(--text-3)', maxWidth: 380 }}>{item.lei_icms || '—'}</td>
                <td>{badge(item.ativo ? 'Sim' : 'Não', item.ativo ? 'ok' : 'err')}</td>
                <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                  <button className="btn btn-icon" title="Editar" onClick={e => { e.stopPropagation(); editar(item) }}><i className="ti ti-pencil" /></button>
                  <button className="btn btn-icon" title="Remover" onClick={e => { e.stopPropagation(); remover(item) }}><i className="ti ti-trash" style={{ color: 'var(--err-text)' }} /></button>
                </td>
              </tr>)}</tbody>
            </table></div>
            {totalPaginas > 1 && <div style={{ display: 'flex', justifyContent: 'center', gap: 8, padding: 12, borderTop: '1px solid var(--border-2)' }}>
              <button className="btn btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>←</button>
              <span className="tnum" style={{ alignSelf: 'center' }}>{page} de {totalPaginas}</span>
              <button className="btn btn-sm" disabled={page === totalPaginas} onClick={() => setPage(p => p + 1)}>→</button>
            </div>}</div>}
      </div>

      {modal && <div className="modal-overlay" onClick={() => setModal(false)}>
        <div className="modal" data-tour="matrizes-excecao-modal"
          style={{ width: 620, maxWidth: 'calc(100vw - 32px)' }} onClick={e => e.stopPropagation()}>
          <div className="modal-header">
            <div><h2>{editId ? 'Editar' : 'Nova'} Exceção do Item</h2>
              <p style={{ margin: '4px 0 0', color: 'var(--text-4)', fontSize: 12 }}>Aplicada em {nomeEmpresa}</p></div>
            <button className="btn btn-icon" data-tour="matrizes-excecao-fechar" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
          </div>
          <form onSubmit={salvar}>
            <div className="modal-body"><div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18 }}>
              <div className="field" style={{ gridColumn: '1 / -1' }}><label>Código do item</label>
                <input required maxLength={60} value={form.codigo_produto} placeholder="Ex.: 13846"
                  onChange={e => setCampo('codigo_produto', e.target.value)} /></div>
              <div className="field"><label>Data início</label><input required type="date" value={form.data_inicio_vigencia} onChange={e => setCampo('data_inicio_vigencia', e.target.value)} /></div>
              <div className="field"><label>Data fim <span style={{ color: 'var(--text-4)', fontWeight: 400 }}>(opcional)</span></label>
                <input type="date" value={form.data_fim_vigencia} onChange={e => setCampo('data_fim_vigencia', e.target.value)} /></div>
              <div style={{ gridColumn: '1 / -1' }}><SwitchFiscal checked={form.tributado_icms}
                onChange={v => setCampo('tributado_icms', v)} label="Tributado ICMS"
                description="Ativado = tributação normal; desativado = produto sujeito a ICMS-ST" /></div>
              <div className="field" style={{ gridColumn: '1 / -1' }}><label>Lei ICMS <span style={{ color: 'var(--text-4)', fontWeight: 400 }}>(opcional)</span></label>
                <textarea maxLength={2000} rows={4} value={form.lei_icms} placeholder="Fundamento legal ou justificativa da exceção"
                  onChange={e => setCampo('lei_icms', e.target.value)} /></div>
              <div style={{ gridColumn: '1 / -1' }}><SwitchFiscal checked={form.ativo}
                onChange={v => setCampo('ativo', v)} label="Exceção ativa"
                description="Quando desativada, a regra deixa de interferir no cálculo" /></div>
            </div></div>
            <div className="modal-footer">
              <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Fechar</button>
              <button type="submit" className="btn btn-primary" disabled={saving || !form.codigo_produto || !form.data_inicio_vigencia}>
                {saving ? 'Salvando…' : 'Salvar exceção'}
              </button>
            </div>
          </form>
        </div>
      </div>}
    </div>
  )
}
