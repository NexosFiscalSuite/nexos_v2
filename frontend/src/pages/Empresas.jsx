import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import Dropdown from '../components/Dropdown'
import ResumoImportModal from '../components/ResumoImportModal'
import { api, saveBlob } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const VAZIO = {
  cnpj: '', razao_social: '', nome_fantasia: '', regime: '', uf: '', municipio: '',
  inscricao_estadual: '', cnae: '', cep: '', logradouro: '', numero: '', bairro: '',
}

// Espelha o ritmo do backend (pausa entre consultas cresce com o lote) para
// estimar a duração antes de o usuário confirmar a atualização em massa.
function minutosEstimados(total) {
  const pausa = total <= 30 ? 1 : total <= 120 ? 2 : 3
  return Math.max(1, Math.ceil((total * pausa) / 60))
}

// Números de página com janela: 1 … 4 [5] 6 … 20 (elipse onde saltar).
function paginasVisiveis(atual, total) {
  const nums = []
  for (let i = 1; i <= total; i++) {
    if (i === 1 || i === total || Math.abs(i - atual) <= 2) nums.push(i)
    else if (nums[nums.length - 1] !== '…') nums.push('…')
  }
  return nums
}

// Empresa (o próprio cliente do escritório) mantém as opções detalhadas de regime.
export const REGIME_OPTS = [
  { value: 'Simples Nacional', label: 'Simples Nacional' },
  { value: 'MEI', label: 'MEI' },
  { value: 'Lucro Presumido', label: 'Lucro Presumido' },
  { value: 'Lucro Real', label: 'Lucro Real' },
  { value: 'Produtor Rural', label: 'Produtor Rural (PF)' },
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

  // Busca + paginação: a carteira cresce; a tela não pode virar um rolo.
  const [porPagina, setPorPagina] = useState(25)
  const [busca, setBusca] = useState('')
  const [page, setPage] = useState(1)
  const filtradas = useMemo(() => {
    const t = busca.trim().toLowerCase()
    if (!t) return lista
    const dig = t.replace(/\D/g, '')
    return lista.filter(e =>
      (e.razao_social || '').toLowerCase().includes(t)
      || (e.nome_fantasia || '').toLowerCase().includes(t)
      || (e.municipio || '').toLowerCase().includes(t)
      || (dig && (e.cnpj || '').includes(dig)))
  }, [lista, busca])
  useEffect(() => { setPage(1) }, [busca, porPagina])
  const totalPaginas = Math.max(1, Math.ceil(filtradas.length / porPagina))
  const pagina = filtradas.slice((page - 1) * porPagina, page * porPagina)

  // Cadastro em lote (planilha): template = export; import = upsert por CNPJ.
  const fileRef = useRef(null)
  const [bulkBusy, setBulkBusy] = useState(false)
  const [resultado, setResultado] = useState(null)

  // Atualização em massa pela Receita: roda no worker; aqui só polling do job.
  const [confirmAtu, setConfirmAtu] = useState(false)
  const [jobAtu, setJobAtu] = useState(null)         // {id,total,processed}
  const [resumoAtu, setResumoAtu] = useState(null)

  async function exportarPlanilha() {
    setBulkBusy(true)
    try {
      const { blob, filename } = await api.exportarEmpresas()
      saveBlob(blob, filename)
      toast('Planilha exportada — vazia é o modelo: preencha uma linha por empresa.', 'ok')
    } catch (e) { toast(e.message, 'error') }
    finally { setBulkBusy(false) }
  }

  async function importarPlanilha(e) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    setBulkBusy(true)
    try {
      const r = await api.importarEmpresas(file)
      carregar()
      reload()
      if (r.erros?.length) setResultado(r)
      else toast(`Importação concluída: ${r.inseridos} nova(s), ${r.atualizados} atualizada(s).`, 'ok')
    } catch (e2) { toast(e2.message, 'error') }
    finally { setBulkBusy(false) }
  }

  function abrirNova() { setEditId(null); setForm(VAZIO); setModal(true) }
  function abrirEdicao(e) {
    setEditId(e.id)
    setForm({ ...VAZIO, ...e })
    setModal(true)
  }

  async function iniciarAtualizacao() {
    setConfirmAtu(false)
    try {
      const r = await api.atualizarCadastrosEmpresas()
      setJobAtu({ id: r.job_id, total: r.total, processed: 0 })
    } catch (e) { toast(e.message, 'error') }
  }

  // Se já havia uma atualização rodando (outra aba, F5), retoma o acompanhamento.
  useEffect(() => {
    (async () => {
      try {
        const js = await api.jobs()
        const ativo = (js || []).find(j => j.kind === 'atualiza_cadastro'
          && (j.status === 'queued' || j.status === 'running'))
        if (ativo) setJobAtu({ id: ativo.id, total: ativo.total, processed: ativo.processed })
      } catch { /* silencioso: só perde a retomada do chip */ }
    })()
  }, [])

  useEffect(() => {
    if (!jobAtu) return
    const t = setInterval(async () => {
      try {
        const j = await api.job(jobAtu.id)
        if (j.status === 'done') {
          setJobAtu(null)
          setResumoAtu(j.result || {})
          carregar(); reload()
        } else if (j.status === 'failed') {
          setJobAtu(null)
          toast(j.error || 'A atualização de cadastros falhou.', 'error')
        } else {
          setJobAtu(a => (a ? { ...a, processed: j.processed, total: j.total || a.total } : a))
        }
      } catch { /* rede oscilou: tenta no próximo tick */ }
    }, 3000)
    return () => clearInterval(t)
  }, [jobAtu?.id])           // eslint-disable-line react-hooks/exhaustive-deps

  async function puxarCNPJ() {
    // CPF (produtor rural) e CEI (obra/INSS) não têm consulta pública — manual.
    const digitos = (form.cnpj || '').replace(/\D/g, '').length
    if (digitos === 11 || digitos === 12) {
      toast('Consulta pela Receita vale só para CNPJ — cadastro por CPF ou CEI é manual.', 'info')
      return
    }
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
      toast(editId ? 'Dados atualizados pela Receita — confira e salve.' : 'Dados preenchidos pela Receita.', 'ok')
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
        const { cnpj: _cnpj, ...campos } = form    // CNPJ é imutável (descartado)
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
      <input ref={fileRef} type="file" accept=".csv" onChange={importarPlanilha} style={{ display: 'none' }} />
      <div className="page-header">
        <h1 className="page-title">Empresas</h1>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {jobAtu ? (
            <span className="btn btn-secondary" style={{ cursor: 'default', gap: 8 }}
              title="Consultando CNPJ a CNPJ na base pública — com pausa entre consultas para não derrubar a API">
              <span className="spinner" style={{ width: 14, height: 14 }} />
              Atualizando {jobAtu.processed} de {jobAtu.total}…
            </span>
          ) : (
            <button className="btn btn-secondary" disabled={bulkBusy} onClick={() => setConfirmAtu(true)}
              title="Consulta cada CNPJ na base pública da Receita e atualiza razão social, endereço e CNAE">
              <i className="ti ti-refresh" /> Atualizar pela Receita
            </button>
          )}
          <button className="btn btn-secondary" disabled={bulkBusy} onClick={exportarPlanilha}
            title="Baixa a planilha modelo (com as empresas atuais); preencha e importe de volta">
            <i className="ti ti-file-spreadsheet" /> Exportar Planilha
          </button>
          <button className="btn btn-secondary" disabled={bulkBusy} onClick={() => fileRef.current?.click()}
            title="Cadastro em lote: upsert por CNPJ, linha inválida vira relatório sem derrubar o lote">
            <i className="ti ti-upload" /> Importar Planilha
          </button>
          <button className="btn btn-primary" onClick={abrirNova}><i className="ti ti-plus" /> Nova empresa</button>
        </div>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : lista.length === 0 ? (
        <div className="empty-state"><i className="ti ti-building-store" /><p>Nenhuma empresa cadastrada.</p></div>
      ) : (
        <>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
          <div style={{ position: 'relative', width: 320, maxWidth: '100%' }}>
            <i className="ti ti-search" style={{ position: 'absolute', left: 11, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-4)', fontSize: 14 }} />
            <input value={busca} onChange={e => setBusca(e.target.value)}
              placeholder="Buscar razão social, fantasia, CNPJ, município…"
              style={{ width: '100%', paddingLeft: 32, paddingRight: busca ? 30 : 12 }} />
            {busca && (
              <button onClick={() => setBusca('')} title="Limpar busca"
                style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', cursor: 'pointer', color: 'var(--text-4)', padding: 2, display: 'flex' }}>
                <i className="ti ti-x" style={{ fontSize: 13 }} />
              </button>
            )}
          </div>
          <span style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
            {filtradas.length} de {lista.length} empresa(s)
          </span>
          <div style={{ marginLeft: 'auto', width: 150 }}>
            <Dropdown value={String(porPagina)} onChange={v => setPorPagina(Number(v))} options={[
              { value: '25', label: '25 por página' },
              { value: '50', label: '50 por página' },
              { value: '100', label: '100 por página' },
            ]} />
          </div>
        </div>

        {filtradas.length === 0 ? (
          <div className="empty-state"><i className="ti ti-search-off" /><p>Nenhuma empresa encontrada para “{busca}”.</p></div>
        ) : (
        <div className="card" style={{ padding: 0 }}>
          <div className="tbl-wrap">
            <table className="tbl">
              <thead>
                <tr><th>Razão social</th><th>Documento</th><th>Regime</th><th>UF</th><th></th></tr>
              </thead>
              <tbody>
                {pagina.map(e => (
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
          {totalPaginas > 1 && (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: 12, borderTop: '1px solid var(--border-2)' }}>
              <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}>
                <i className="ti ti-chevron-left" />
              </button>
              {paginasVisiveis(page, totalPaginas).map((n, i) => n === '…'
                ? <span key={`e${i}`} style={{ padding: '0 6px', color: 'var(--text-4)' }}>…</span>
                : (
                  <button key={n} onClick={() => setPage(n)} className="btn btn-sm"
                    style={{
                      minWidth: 32, justifyContent: 'center', border: 'none',
                      background: n === page ? 'var(--primary)' : 'transparent',
                      color: n === page ? '#fff' : 'var(--text-2)', fontWeight: n === page ? 700 : 500,
                    }}>{n}</button>
                ))}
              <button className="btn btn-ghost btn-sm" disabled={page === totalPaginas} onClick={() => setPage(p => p + 1)}>
                <i className="ti ti-chevron-right" />
              </button>
            </div>
          )}
        </div>
        )}
        </>
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
                  <label>CNPJ / CPF (produtor rural) / CEI (obra)</label>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input value={form.cnpj} onChange={set('cnpj')} placeholder="CNPJ, CPF ou matrícula CEI" required disabled={!!editId} />
                    <button type="button" className="btn btn-secondary btn-icon" disabled={looking} onClick={puxarCNPJ}
                      title={editId ? 'Atualizar dados pela Receita' : 'Buscar dados pelo CNPJ'}>
                      {looking
                        ? <span className="spinner" style={{ width: 16, height: 16 }} />
                        : <i className={`ti ${editId ? 'ti-refresh' : 'ti-search'}`} style={{ fontSize: 17 }} />}
                    </button>
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

      {resultado && <ResumoImportModal r={resultado} onClose={() => setResultado(null)} />}

      {confirmAtu && (
        <div className="modal-overlay" onClick={() => setConfirmAtu(false)}>
          <div className="modal" style={{ maxWidth: 460 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Atualizar cadastros pela Receita</h2>
              <button className="btn btn-icon" onClick={() => setConfirmAtu(false)}><i className="ti ti-x" /></button>
            </div>
            <div className="modal-body" style={{ fontSize: 13.5, color: 'var(--text-2)', display: 'grid', gap: 10 }}>
              <p>
                As <b>{lista.length} empresa(s)</b> serão consultadas uma a uma na base pública
                da Receita (OpenCNPJ) — razão social, nome fantasia, endereço e CNAE são atualizados
                com os dados oficiais.
              </p>
              <p>
                Para não derrubar a API gratuita, há uma pausa entre as consultas: a atualização roda
                em segundo plano e leva cerca de <b>{minutosEstimados(lista.length)} min</b>. Pode
                continuar usando o sistema normalmente.
              </p>
              <p style={{ fontSize: 12.5, color: 'var(--text-3)' }}>
                O regime tributário só muda quando a Receita confirma Simples Nacional ou MEI —
                Lucro Presumido × Real continua sendo escolha do escritório. Nenhum campo é apagado.
                Cadastros por CPF (produtor rural) ou CEI (obra) são pulados: a consulta pública só existe para CNPJ.
              </p>
            </div>
            <div className="modal-footer">
              <button className="btn btn-ghost" onClick={() => setConfirmAtu(false)}>Cancelar</button>
              <button className="btn btn-primary" onClick={iniciarAtualizacao}>
                <i className="ti ti-refresh" /> Atualizar {lista.length} empresa(s)
              </button>
            </div>
          </div>
        </div>
      )}

      {resumoAtu && (
        <div className="modal-overlay" onClick={() => setResumoAtu(null)}>
          <div className="modal" style={{ maxWidth: 560 }} onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Atualização concluída</h2>
              <button className="btn btn-icon" onClick={() => setResumoAtu(null)}><i className="ti ti-x" /></button>
            </div>
            <div className="modal-body" style={{ display: 'grid', gap: 12 }}>
              <p style={{ fontSize: 13.5, color: 'var(--text-2)' }}>
                <b>{resumoAtu.atualizadas ?? 0}</b> de <b>{resumoAtu.total ?? 0}</b> empresa(s)
                atualizada(s) pela Receita.
                {resumoAtu.sem_consulta > 0 && <> <b>{resumoAtu.sem_consulta}</b> cadastro(s) por
                CPF ou CEI não têm consulta pública — atualização manual.</>}
              </p>
              {(resumoAtu.avisos?.length > 0) && (
                <div>
                  <div className="section-label">Situação cadastral exige atenção</div>
                  <div style={{ maxHeight: 180, overflowY: 'auto', border: '1px solid var(--border-2)', borderRadius: 8 }}>
                    <table className="tbl">
                      <tbody>
                        {resumoAtu.avisos.map((a, i) => (
                          <tr key={i}>
                            <td style={{ fontSize: 12.5 }}>{a.razao_social}<div className="mono" style={{ fontSize: 11, color: 'var(--text-4)' }}>{a.cnpj}</div></td>
                            <td style={{ fontSize: 12.5, color: 'var(--warning, #b45309)', whiteSpace: 'nowrap' }}>{a.situacao}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
              {(resumoAtu.falhas?.length > 0) && (
                <div>
                  <div className="section-label">Não foi possível consultar</div>
                  <div style={{ maxHeight: 180, overflowY: 'auto', border: '1px solid var(--border-2)', borderRadius: 8 }}>
                    <table className="tbl">
                      <tbody>
                        {resumoAtu.falhas.map((f, i) => (
                          <tr key={i}>
                            <td style={{ fontSize: 12.5 }}>{f.razao_social}<div className="mono" style={{ fontSize: 11, color: 'var(--text-4)' }}>{f.cnpj}</div></td>
                            <td style={{ fontSize: 12.5, color: 'var(--text-3)' }}>{f.erro}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
            <div className="modal-footer">
              <button className="btn btn-primary" onClick={() => setResumoAtu(null)}>Fechar</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
