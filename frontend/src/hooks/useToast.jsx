import { useState, useCallback } from 'react'

export function useToast() {
  const [toasts, setToasts] = useState([])
  const toast = useCallback((msg, type = 'info', duration = 4000) => {
    const id = Date.now()
    setToasts(t => [...t, { id, msg, type }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), duration)
  }, [])
  return { toasts, toast }
}

export function ToastContainer({ toasts }) {
  const icons = { ok:'ti-circle-check', error:'ti-circle-x', info:'ti-info-circle' }
  const colors = { ok:'#10B981', error:'#EF4444', info:'var(--primary)' }
  return (
    <div className="toast-container">
      {toasts.map(t => (
        <div key={t.id} className={`toast toast-${t.type}`}>
          <i className={`ti ${icons[t.type]||'ti-info-circle'} t-icon`} style={{ fontSize:18, color:colors[t.type], flexShrink:0 }} />
          <span style={{ color:'var(--text-1)', fontSize:13 }}>{t.msg}</span>
        </div>
      ))}
    </div>
  )
}
