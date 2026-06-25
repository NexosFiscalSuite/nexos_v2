import { useState, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import Dropdown from '../components/Dropdown'
import { api } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const VAZIO = {
  cnpj: '', razao_social: '', nome_fantasia: '', regime: '', uf: '', municipio: '',
  inscricao_estadual: '', cnae: '', cep: '', logradouro: '', numero: '', bairro: '',
}

// Empresa (o próprio cliente do escritório) mantém as opções detalhadas de regime.
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
  const [editId, setEditId] = useState(null)        // null = criação; id = edição
  const [form, setForm] = useState(VAZIO)
  const [saving, setSaving] = useState(false)
  const [looking, setLooking] = useState(false)

  function abrirNova() { setEditId(null); setForm(VAZIO); setModal(true) }
  function abrirEdicao(e) {
    setEditId(e.id)
    setForm({ ...VAZIO, ...e })
    setModal(true)
  }

  async function puxarCNPJ() {
    setLooking(true)
    try {
      const r = await api.consultarCNPJ(form.cnpj, 'empresa')
      if (!r.ok) { toast(r.error || 'CNPJ não encontrado.', 'error'); return }
      const d = r.dados
      setForm(f => ({
        ...f,
        razao_social: d.razao_social || f.razao_social,
        nome_fantasia: d.nome_fantasia || f.nome_fantasia,
        regime: d.regime || f.regime,
        uf: d.uf || f.uf,
        municipio: d.municipio || f.municipio,
        cnae: d.cnae || f.cnae,
        cep: d.cep || f.cep,
        logradouro: d.logradouro || f.logradouro,
        numero: d.numero || f.numero,
        bairro: d.bairro || f.bairro,
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
      if (editId) {
        const { cnpj, ...campos } = form    // CNPJ é imutável
        await api.editarEmpresa(editId, campos)
        toast('Empresa atualizada.', 'ok')
      } else {
        await api.criarEmpresa(form)
        toast('Empresa cadastrada.', 'ok')
      }
      setModal(false); setForm(VAZIO); setEditId(null)
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
        <button className="btn btn-primary" onClick={abrirNova}><i className="ti ti-plus" /> Nova empresa</button>
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
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      <button className="btn btn-icon" title="Editar empresa"
                        onClick={ev => { ev.stopPropagation(); abrirEdicao(e) }}>
                        <i className="ti ti-pencil" />
                      </button>
                      <i className="ti ti-chevron-right" style={{ color: 'var(--text-4)', marginLeft: 4 }} />
                    </td>
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
              <h2>{editId ? 'Editar empresa' : 'Nova empresa'}</h2>
              <button className="btn btn-icon" onClick={() => setModal(false)}><i className="ti ti-x" /></button>
            </div>
            <form onSubmit={salvar}>
              <div className="modal-body">
                <div className="field">
                  <label>CNPJ</label>
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
                  <div className="field">
                    <label>Nome fantasia</label>
                    <input value={form.nome_fantasia} onChange={set('nome_fantasia')} />
                  </div>
                  <div className="field">
                    <label>CNAE Principal</label>
                    <input value={form.cnae} onChange={set('cnae')} placeholder="0000000" />
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 100px', gap: 14 }}>
                  <div className="field">
                    <label>Regime Tributário</label>
                    <Dropdown value={form.regime} onChange={v => setForm(f => ({ ...f, regime: v }))} options={REGIME_OPTS} placeholder="Selecione…" />
                  </div>
                  <div className="field">
                    <label>Inscrição estadual</label>
                    <input value={form.inscricao_estadual} onChange={set('inscricao_estadual')} />
                  </div>
                </div>

                <div className="section-label" style={{ marginTop: 8 }}>Endereço</div>
                <div style={{ display: 'grid', gridTemplateColumns: '140px 1fr 100px', gap: 14 }}>
                  <div className="field">
                    <label>CEP</label>
                    <input value={form.cep} onChange={set('cep')} placeholder="00000-000" />
                  </div>
                  <div className="field">
                    <label>Logradouro</label>
                    <input value={form.logradouro} onChange={set('logradouro')} />
                  </div>
                  <div className="field">
                    <label>Número</label>
                    <input value={form.numero} onChange={set('numero')} />
                  </div>
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 100px', gap: 14 }}>
                  <div className="field">
                    <label>Bairro</label>
                    <input value={form.bairro} onChange={set('bairro')} />
                  </div>
                  <div className="field">
                    <label>Município</label>
                    <input value={form.municipio} onChange={set('municipio')} />
                  </div>
                  <div className="field">
                    <label>UF</label>
                    <input value={form.uf} onChange={set('uf')} maxLength={2} />
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
