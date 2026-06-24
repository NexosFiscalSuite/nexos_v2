import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Dropdown from '../components/Dropdown'
import { api } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const VAZIO = { cnpj: '', razao_social: '', nome_fantasia: '', regime: '', uf: '', municipio: '', inscricao_estadual: '' }

export const REGIME_OPTS = [
  { value: 'Simples Nacional', label: 'Simples Nacional' },
  { value: 'MEI', label: 'MEI' },
  { value: 'Lucro Presumido', label: 'Lucro Presumido' },
  { value: 'Lucro Real', label: 'Lucro Real' },
]

export default function Empresas() {
  const { reload } = useEmpresa()
  const { toasts, toast } = useToast()
  const navigate = useNavigate()
  const [lista, setLista] = useState([])
  const [loading, setLoading] = useState(true)
  const [modal, setModal] = useState(false)
  const [form, setForm] = useState(VAZIO)
  const [saving, setSaving] = useState(false)
  const [looking, setLooking] = useState(false)

  async function puxarCNPJ() {
    setLooking(true)
    try {
      const r = await api.consultarCNPJ(form.cnpj, 'empresa')
      if (!r.ok) { toast(r.error || 'CNPJ não encontrado.', 'error'); return }
      setForm(f => ({
        ...f,
        razao_social: r.dados.razao_social || f.razao_social,
        nome_fantasia: r.dados.nome_fantasia || f.nome_fantasia,
        regime: r.dados.regime || f.regime,
        uf: r.dados.uf || f.uf,
        municipio: r.dados.municipio || f.municipio,
      }))
      toast('Dados preenchidos pela Receita.', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setLooking(false) }
  }

  const carregar = useCallback(async () => {
    setLoading(true)
    try { setLista(await api.empresas() || []) }
    catch (e) { toast(e.message, 'error') }
    finally { setLoading(false) }
  }, [toast])

  useEffect(() => { carregar() }, [carregar])

  async function salvar(e) {
    e.preventDefault()
    setSaving(true)
    try {
      await api.criarEmpresa(form)
      toast('Empresa cadastrada.', 'ok')
      setModal(false); setForm(VAZIO)
      await carregar(); reload()
    } catch (err) { toast(err.message, 'error') }
    finally { setSaving(false) }
  }

  const set = (k) => (e) => setForm(f => ({ ...f, [k]: e.target.value }))

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <h1 className="page-title">Empresas</h1>
        <button className="btn btn-primary" onClick={() => setModal(true)}><i className="ti ti-plus" /> Nova empresa</button>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : lista.length === 0 ? (
        <div className="empty-state"><i className="ti ti-building-store" /><p>Nenhuma empresa cadastrada.</p></div>
      ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>Razão social</th><th>CNPJ</th><th>Regime</th><th>UF</th><th></th></tr>
              </thead>
              <tbody>
                {lista.map(e => (
                  <tr key={e.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/empresas/${e.id}`)}>
                    <td>
                      <div style={{ fontWeight: 500, color: 'var(--text-1)' }}>{e.razao_social}</div>
                      {e.nome_fantasia && <div style={{ fontSize: 11, color: 'var(--text-4)' }}>{e.nome_fantasia}</div>}
                    </td>
                    <td className="mono">{e.cnpj}</td>
                    <td>{e.regime || '—'}</td>
                    <td>{e.uf || '—'}</td>
                    <td style={{ textAlign: 'right', color: 'var(--text-4)' }}><i className="ti ti-chevron-right" /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {modal && (
        <div className="modal-overlay" onClick={() => setModal(false)}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Nova empresa</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div className="field">
                  <label>CNPJ</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input value={form.cnpj} onChange={set('cnpj')} placeholder="00.000.000/0000-00" required />
                    <button type="button" className="btn btn-secondary btn-icon" title="Buscar dados pelo CNPJ" disabled={looking} onClick={puxarCNPJ}>
                      {looking ? <span className="spinner" style={{ width: 16, height: 16 }} /> : <i className="ti ti-search" style={{ fontSize: 17 }} />}
                    </button>
                  </div>
                </div>
                <div className="field">
                  <label>Razão social</label>
                  <input value={form.razao_social} onChange={set('razao_social')} required />
                </div>
                <div className="field">
                  <label>Nome fantasia</label>
                  <input value={form.nome_fantasia} onChange={set('nome_fantasia')} />
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px', gap: 14 }}>
                  <div className="field">
                    <label>Regime Tributário</label>
                    <Dropdown value={form.regime} onChange={v => setForm(f => ({ ...f, regime: v }))} options={REGIME_OPTS} placeholder="Selecione…" />
                  </div>
                  <div className="field">
                    <label>UF</label>
                    <input value={form.uf} onChange={set('uf')} maxLength={2} />
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 14 }}>
                  <div className="field">
                    <label>Município</label>
                    <input value={form.municipio} onChange={set('municipio')} />
                  </div>
                  <div className="field">
                    <label>Inscrição estadual</label>
                    <input value={form.inscricao_estadual} onChange={set('inscricao_estadual')} />
                  </div>
                </div>
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
