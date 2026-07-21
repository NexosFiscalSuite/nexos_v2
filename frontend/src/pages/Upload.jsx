import { useState, useRef, useCallback } from 'react'
import { api } from '../api'
import { useEmpresa } from '../context/EmpresaContext'
import { useRefresh } from '../context/RefreshContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const POLL_MS = 1200

function KpiBox({ valor, label, cor }) {
  return (
    <div className="result-kpi">
      <div className="rk-val" style={{ color: cor || 'var(--text-1)' }}>{valor}</div>
      <div className="rk-lbl">{label}</div>
    </div>
  )
}

export default function Upload() {
  const { selectedEmpresa } = useEmpresa()
  const { bumpData } = useRefresh()
  const { toasts, toast } = useToast()
  const inputRef = useRef()

  const [files, setFiles] = useState([])
  const [drag, setDrag] = useState(false)
  const [job, setJob] = useState(null)
  const [busy, setBusy] = useState(false)

  const addFiles = useCallback((novos) => {
    const aceitos = Array.from(novos).filter(f => /\.(xml|zip)$/i.test(f.name))
    if (!aceitos.length) { toast('Selecione arquivos .xml ou .zip', 'error'); return }
    setFiles(prev => {
      const nomes = new Set(prev.map(f => f.name + f.size))
      const merged = [...prev]
      aceitos.forEach(f => { if (!nomes.has(f.name + f.size)) merged.push(f) })
      return merged
    })
  }, [toast])

  function onDrop(e) { e.preventDefault(); setDrag(false); addFiles(e.dataTransfer.files) }
  const removeFile = (i) => setFiles(prev => prev.filter((_, idx) => idx !== i))

  async function pollJob(jobId) {
    try {
      const j = await api.job(jobId)
      setJob(j)
      if (j.status === 'done' || j.status === 'failed') {
        setBusy(false)
        if (j.status === 'done') { bumpData(); toast(`Importação concluída: ${j.result?.importadas ?? 0} nota(s).`, 'ok') }
        else toast(j.error || 'Falha no processamento.', 'error')
        return
      }
      setTimeout(() => pollJob(jobId), POLL_MS)
    } catch (e) { setBusy(false); toast(e.message || 'Erro ao consultar o job.', 'error') }
  }

  async function enviar() {
    if (!selectedEmpresa) { toast('Selecione uma empresa no topo.', 'error'); return }
    if (!files.length) return
    setBusy(true); setJob(null)
    try {
      const fd = new FormData()
      files.forEach(f => fd.append('files', f))
      const res = await api.upload(selectedEmpresa.id, fd)
      setFiles([])
      setJob({ status: 'queued', total: res.arquivos })
      pollJob(res.job_id)
    } catch (e) { setBusy(false); toast(e.message || 'Falha no upload.', 'error') }
  }

  const resumo = job?.result
  const running = job && (job.status === 'queued' || job.status === 'running')

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">Upload de XMLs</h1>
          <p className="page-breadcrumb">NF-e, NFC-e, CT-e, NFS-e e eventos de cancelamento</p>
        </div>
      </div>

      {!selectedEmpresa && (
        <div className="card" style={{ padding: 16, marginBottom: 16, borderLeft: '3px solid var(--warn-text)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--warn-text)', fontSize: 13, fontWeight: 500 }}>
            <i className="ti ti-alert-triangle" style={{ fontSize: 18 }} />
            Selecione uma empresa no seletor do topo para habilitar o upload.
          </div>
        </div>
      )}

      <div className="card" style={{ padding: 24 }}>
        {selectedEmpresa && (
          <div style={{ fontSize: 13, color: 'var(--text-3)', marginBottom: 16 }}>
            Empresa: <strong style={{ color: 'var(--text-1)' }}>{selectedEmpresa.razao_social}</strong>
            <span style={{ marginLeft: 8, color: 'var(--text-4)' }}>{selectedEmpresa.cnpj}</span>
          </div>
        )}

        <div
          className={`upload-zone ${drag ? 'drag' : ''}`}
          data-tour="upload-area"
          onClick={() => inputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={onDrop}
        >
          <i className="ti ti-file-upload" />
          <div className="uz-title">Arraste os XMLs (ou um .zip com XMLs) aqui, ou clique para selecionar</div>
          <div className="uz-sub">Vários arquivos de uma vez · .xml e .zip</div>
          <input ref={inputRef} type="file" accept=".xml,.zip" multiple hidden
            onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
        </div>

        {files.length > 0 && (
          <div style={{ marginTop: 16 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
              <span className="section-label" style={{ margin: 0 }}>{files.length} arquivo(s)</span>
              <button className="btn btn-ghost btn-sm" onClick={() => setFiles([])}>Limpar tudo</button>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill,minmax(220px,1fr))', gap: 8, maxHeight: 240, overflowY: 'auto' }}>
              {files.map((f, i) => (
                <div key={f.name + i} className="file-chip">
                  <i className="ti ti-file-code" style={{ color: 'var(--primary)', fontSize: 15 }} />
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{f.name}</span>
                  <button className="fc-remove" onClick={() => removeFile(i)}><i className="ti ti-x" /></button>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{ marginTop: 20, display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
          <button className="btn btn-primary" disabled={busy || !files.length || !selectedEmpresa} onClick={enviar}>
            {busy
              ? <><span className="spinner" style={{ width: 14, height: 14 }} /> Enviando...</>
              : <><i className="ti ti-upload" /> Importar {files.length || ''} arquivo(s)</>}
          </button>
        </div>
      </div>

      {job && (
        <div className="result-box" style={{ marginTop: 20 }}>
          <div className="rb-head">
            <i className={`ti ${job.status === 'done' ? 'ti-circle-check' : job.status === 'failed' ? 'ti-circle-x' : 'ti-loader-2'}`} style={{ fontSize: 18 }} />
            {job.status === 'done' ? 'Importação concluída' : job.status === 'failed' ? 'Falha na importação' : 'Processando importação…'}
          </div>

          {running && <div className="progress" style={{ marginBottom: 14 }}><div className="progress-bar" style={{ width: job.status === 'running' ? '66%' : '25%' }} /></div>}

          {resumo && (
            <>
              <div className="result-kpis">
                <KpiBox valor={resumo.importadas ?? 0} label="Importadas" cor="var(--primary-text)" />
                <KpiBox valor={(resumo.duplicadas || []).length} label="Duplicadas" />
                <KpiBox valor={(resumo.canceladas || []).length} label="Canceladas" cor="var(--err-text)" />
                <KpiBox valor={(resumo.rejeitadas || []).length + (resumo.erros || []).length} label="Rejeitadas/Erros" cor="var(--err-text)" />
              </div>
              {(resumo.rejeitadas?.length > 0 || resumo.erros?.length > 0) && (
                <div style={{ fontSize: 12, color: 'var(--text-3)', display: 'flex', flexDirection: 'column', gap: 4 }}>
                  {resumo.rejeitadas?.map((r, i) => (<div key={`r${i}`}><i className="ti ti-alert-triangle" style={{ color: 'var(--warn-text)' }} /> {r.arquivo}: {r.motivo}</div>))}
                  {resumo.erros?.map((r, i) => (<div key={`e${i}`}><i className="ti ti-circle-x" style={{ color: 'var(--err-text)' }} /> {r.arquivo}: {r.erro}</div>))}
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
