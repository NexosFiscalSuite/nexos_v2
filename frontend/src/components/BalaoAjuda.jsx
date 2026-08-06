import { useState, useEffect, useRef } from 'react'

// Balão de ajuda CLICÁVEL (padrão .balao-classif do projeto — nunca tooltip de
// hover): abre no clique e fecha clicando fora ou de novo no gatilho.
export default function BalaoAjuda({ titulo, children, largura = 360 }) {
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
    e.preventDefault()
    e.stopPropagation()
    if (!aberto && ref.current) {
      const r = ref.current.getBoundingClientRect()
      setPos({
        top: Math.min(r.bottom + 6, window.innerHeight - 240),
        left: Math.min(Math.max(r.left - 140, 12), window.innerWidth - (largura + 12)),
      })
    }
    setAberto(a => !a)
  }

  return (
    <span className="balao-classif" style={{ position: 'relative' }}>
      <button ref={ref} type="button" onClick={alternar} title="Clique para entender"
        style={{
          border: 'none', background: 'transparent', padding: 0, marginLeft: 5,
          cursor: 'pointer', color: 'var(--primary)', lineHeight: 1, verticalAlign: 'middle',
        }}>
        <i className="ti ti-help-circle-filled" style={{ fontSize: 14 }} />
      </button>
      {aberto && pos && (
        <div className="balao-classif" style={{
          position: 'fixed', top: pos.top, left: pos.left, zIndex: 2000, width: largura,
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
          boxShadow: '0 10px 30px rgba(0,0,0,.18)', padding: '13px 15px',
          textAlign: 'left', fontWeight: 400, textTransform: 'none', letterSpacing: 0,
        }}>
          <div style={{ fontWeight: 700, fontSize: 12.5, marginBottom: 6 }}>{titulo}</div>
          <div style={{ fontSize: 12.5, color: 'var(--text-2)', lineHeight: 1.6 }}>{children}</div>
        </div>
      )}
    </span>
  )
}
