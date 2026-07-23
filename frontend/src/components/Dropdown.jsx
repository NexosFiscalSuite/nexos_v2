import { useState, useEffect, useRef } from 'react'

export default function Dropdown({ value, onChange, options, placeholder = 'Selecione...', disabled = false }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const selected = options.find(o => String(o.value) === String(value))

  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [])

  return (
    <div ref={ref} style={{ position:'relative' }}>
      <button type="button" onClick={() => !disabled && setOpen(o => !o)} disabled={disabled}
        style={{
          width:'100%', display:'flex', alignItems:'center', justifyContent:'space-between', gap:8,
          padding:'9px 12px', fontSize:13, fontFamily:'inherit', textAlign:'left',
          border:'1.5px solid var(--border)', borderRadius:'var(--radius)',
          background: disabled ? 'var(--surface-2)' : 'var(--surface)',
          color: selected && selected.value !== '' ? 'var(--text-1)' : 'var(--text-4)',
          cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.7 : 1,
          boxShadow: open ? '0 0 0 3px rgba(0,86,210,0.15)' : 'none',
          borderColor: open ? 'var(--primary)' : 'var(--border)',
        }}>
        <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
          {selected ? selected.label : placeholder}
        </span>
        <i className={`ti ti-chevron-${open ? 'up' : 'down'}`} style={{ fontSize:14, color:'var(--text-4)', flexShrink:0 }} />
      </button>

      {open && (
        <div style={{
          position:'absolute', top:'calc(100% + 4px)', left:0, right:0, zIndex:50,
          background:'var(--surface)', border:'1px solid var(--border)', borderRadius:'var(--radius-lg)',
          boxShadow:'0 8px 24px rgba(0,0,0,0.12)', overflow:'hidden', maxHeight:220, overflowY:'auto',
          padding:4,
        }}>
          {options.map(o => {
            const isSel = String(o.value) === String(value)
            return (
              <button key={String(o.value)} type="button"
                onClick={() => { onChange(o.value); setOpen(false) }}
                style={{
                  width:'100%', textAlign:'left', padding:'8px 10px', fontSize:13, fontFamily:'inherit',
                  border:'none', borderRadius:'var(--radius)', cursor:'pointer',
                  background: isSel ? 'var(--primary-lt)' : 'transparent',
                  color: isSel ? 'var(--primary-text)' : 'var(--text-1)',
                  fontWeight: isSel ? 600 : 400,
                  display:'flex', alignItems:'center', justifyContent:'space-between', gap:8,
                }}
                onMouseEnter={e => { if (!isSel) e.currentTarget.style.background = 'var(--surface-2)' }}
                onMouseLeave={e => { if (!isSel) e.currentTarget.style.background = 'transparent' }}>
                <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{o.label}</span>
                {isSel && <i className="ti ti-check" style={{ fontSize:15, color:'var(--primary-text)', flexShrink:0 }} />}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}
