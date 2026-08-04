import { useState, useEffect, useCallback } from 'react'
import Dropdown from '../components/Dropdown'
import Paginacao from '../components/Paginacao'
import { api } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const TIPOS = [
  { value: 'cliente', label: 'Clientes', icon: 'ti-users' },
  { value: 'fornecedor', label: 'Fornecedores', icon: 'ti-truck-delivery' },
]
// Para terceiros (cliente/fornecedor) só importa: é Simples ou é Normal? Real e
// Presumido têm o mesmo cálculo de ICMS, então agrupam em "Regime Normal".
const REGIME_OPTS = [
  { value: 'Simples Nacional', label: 'Simples Nacional' },
  { value: 'MEI', label: 'MEI' },
  { value: 'Normal', label: 'Regime Normal' },
]
const VAZIO = {
  cnpj: '', razao_social: '', nome_fantasia: '', situacao: '', uf: '', municipio: '',
  atividade: '', cnae: '', porte: '', regime: 'Normal', inscricao_estadual: '',
  cep: '', logradouro: '', numero: '', bairro: '',
}

export default function Cadastros() {
  const { selectedEmpresa } = useEmpresa()
  const { toasts, toast } = useToast()
  const [tipo, setTipo] = useState('cliente')
  const [search, setSearch] = useState('')
  const [lista, setLista] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(VAZIO)
  const [editId, setEditId] = useState(null)
  const [saving, setSaving] = useState(false)
  const [looking, setLooking] = useState(false)

  const carregar = useCallback(async () => {
    if (!selectedEmpresa) { setLista([]); setTotal(0); return }
    setLoading(true)
    try {
      // Paginação no servidor: fornecedor entra por upsert de XML aos milhares.
      const r = await api.contrapartes(selectedEmpresa.id, {
        tipo, search: search || undefined, page, page_size: 25,
      })
      setLista(r?.items || (Array.isArray(r) ? r : []))
      setTotal(r?.total ?? 0)
    }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [selectedEmpresa, tipo, search, page, toast])

  useEffect(() => { const t = setTimeout(carregar, 250); return () => clearTimeout(t) }, [carregar])
  useEffect(() => { setPage(1) }, [tipo, search, selectedEmpresa])

  function abrirNovo() { setForm(VAZIO); setEditId(null); setModal(true) }
  function abrirEdicao(c) {
    setForm({ ...VAZIO, ...c })
    setEditId(c.id); setModal(true)
  }

  async function puxarCNPJ() {
    setLooking(true)
    try {
      // contexto 'contraparte': se não for Simples, o backend já devolve "Normal".
      const r = await api.consultarCNPJ(form.cnpj, 'contraparte')
      if (!r.ok) { toast(r.error || 'CNPJ não encontrado.', 'error'); return }
      setForm(f => ({ ...f, ...r.dados, regime: r.dados.regime || 'Normal' }))
      toast('Dados preenchidos pela Receita.', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setLooking(false) }
  }

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      if (editId) {
        await api.editarContraparte(editId, { ...form, pendente_revisao: false })
      } else {
        await api.criarContraparte(selectedEmpresa.id, { tipo, ...form })
      }
      toast(editId ? 'Atualizado.' : 'Cadastrado.', 'ok')
      setModal(false); carregar()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  if (!selectedEmpresa) {
    return (
      <div>
        <div className="page-header"><h1 className="page-title">Clientes e Fornecedores</h1></div>
        <div className="empty-state"><i className="ti ti-address-book" /><p>Selecione uma empresa no topo.</p></div>
      </div>
    )
  }

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Clientes e Fornecedores</h1>
          <p className="page-breadcrumb">{selectedEmpresa.razao_social}</p>
        </div>
        <button className="btn btn-primary" onClick={abrirNovo}>
          <i className="ti ti-plus" /> Novo {tipo}
        </button>
      </div>

      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <div style={{ display: 'inline-flex', background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: 3 }}>
          {TIPOS.map(t => (
            <button key={t.value} onClick={() => setTipo(t.value)}
              className="btn btn-sm"
              style={{
                background: tipo === t.value ? 'var(--surface)' : 'transparent',
                color: tipo === t.value ? 'var(--text-1)' : 'var(--text-3)',
                boxShadow: tipo === t.value ? 'var(--shadow-sm)' : 'none', border: 'none',
              }}>
              <i className={`ti ${t.icon}`} /> {t.label}
            </button>
          ))}
        </div>
        <div className="input-wrap" style={{ flex: 1, maxWidth: 320 }}>
          <i className="ti ti-search input-icon" />
          <input value={search} onChange={e => setSearch(e.target.value)} placeholder="Buscar por nome ou CNPJ…" />
        </div>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : lista.length === 0 ? (
        <div className="empty-state"><i className="ti ti-address-book" /><p>Nenhum {tipo} cadastrado.</p></div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="table">
              <thead><tr><th>Razão social</th><th>CNPJ</th><th>UF</th><th>Regime</th><th>Origem</th><th></th></tr></thead>
              <tbody>
                {lista.map(c => (
                  <tr key={c.id} style={{ cursor: 'pointer' }} onClick={() => abrirEdicao(c)}>
                    <td>
                      <div style={{ fontWeight: 500, color: 'var(--text-1)' }}>{c.razao_social || '—'}</div>
                      {c.nome_fantasia && <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{c.nome_fantasia}</div>}
                    </td>
                    <td className="mono">{c.cnpj}</td>
                    <td>{c.uf || '—'}</td>
                    <td>{c.regime || '—'}</td>
                    <td>
                      {c.pendente_revisao
                        ? <span className="badge badge-warn">revisar</span>
                        : <span className="badge badge-neutral">{c.origem}</span>}
                    </td>
                    <td style={{ textAlign: 'right', color: 'var(--text-4)' }}><i className="ti ti-pencil" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Paginacao page={page} total={total} pageSize={25} onChange={setPage} />
        </div>
      )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()} style={{ width: 600 }}>
            <div className="modal-header">
              <h2>{editId ? 'Editar' : 'Novo'} {tipo}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div className="field">
                  <label>CNPJ / CPF</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input value={form.cnpj} onChange={set('cnpj')} placeholder="00.000.000/0000-00" required disabled={!!editId} />
                    {!editId && (
                      <button type="button" className="btn btn-secondary btn-icon" title="Buscar dados pelo CNPJ" disabled={looking} onClick={puxarCNPJ}>
                        {looking ? <span className="spinner" style={{ width: 16, height: 16 }} /> : <i className="ti ti-search" style={{ fontSize: 17 }} />}
                      </button>
                    )}
                  </div>
                </div>
                <div className="field">
                  <label>Razão social</label>
                  <input value={form.razao_social} onChange={set('razao_social')} required />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div className="field"><label>Nome fantasia</label><input value={form.nome_fantasia || ''} onChange={set('nome_fantasia')} /></div>
                  <div className="field"><label>Inscrição estadual</label><input value={form.inscricao_estadual || ''} onChange={set('inscricao_estadual')} /></div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 80px 1fr', gap: 14 }}>
                  <div className="field"><label>Município</label><input value={form.municipio || ''} onChange={set('municipio')} /></div>
                  <div className="field"><label>UF</label><input value={form.uf || ''} onChange={set('uf')} maxLength={2} /></div>
                  <div className="field">
                    <label>Regime Tributário</label>
                    <Dropdown value={form.regime || ''} onChange={v => setForm(f => ({ ...f, regime: v }))} options={REGIME_OPTS} placeholder="Selecione…" />
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '120px 1fr', gap: 14 }}>
                  <div className="field"><label>CNAE</label><input value={form.cnae || ''} onChange={set('cnae')} placeholder="0000000" /></div>
                  <div className="field"><label>Atividade</label><input value={form.atividade || ''} onChange={set('atividade')} /></div>
                </div>

                <div className="section-label" style={{ marginTop: 8 }}>Endereço</div>
                <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 100px', gap: 14 }}>
                  <div className="field"><label>CEP</label><input value={form.cep || ''} onChange={set('cep')} placeholder="00000-000" /></div>
                  <div className="field"><label>Logradouro</label><input value={form.logradouro || ''} onChange={set('logradouro')} /></div>
                  <div className="field"><label>Número</label><input value={form.numero || ''} onChange={set('numero')} /></div>
                </div>
                <div className="field"><label>Bairro</label><input value={form.bairro || ''} onChange={set('bairro')} /></div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-ghost" onClick={() => setModal(false)}>Cancelar</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'Salvando…' : 'Salvar'}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
