import { useState, useRef, useEffect } from 'react'

const MESES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
const MESES_FULL = ['Janeiro','Fevereiro','Março','Abril','Maio','Junho','Julho','Agosto','Setembro','Outubro','Novembro','Dezembro']

// Variante compacta do MonthPicker para o topbar (competencia global, sempre preenchida).
export default function CompetenciaPicker({ value, onChange }) {
  const today = new Date()
  const selYear  = value ? parseInt(value.split('-')[0]) : today.getFullYear()
  const selMonth = value ? parseInt(value.split('-')[1]) - 1 : today.getMonth()

  const [open, setOpen] = useState(false)
  const [viewYear, setViewYear] = useState(selYear)
  const ref = useRef()

  useEffect(() => {
    function h(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  useEffect(() => { if (value) setViewYear(parseInt(value.split('-')[0])) }, [value])

  function select(i) {
    onChange(`${viewYear}-${String(i + 1).padStart(2, '0')}`)
    setOpen(false)
  }

  const label = value
    ? `${MESES[selMonth]}/${String(selYear).slice(2)}`
    : 'Competência'

  return (
    <div ref={ref} style={{ position:'relative', userSelect:'none' }}>
      <button
        onClick={() => { setOpen(o => !o); setViewYear(selYear) }}
        style={{
          display:'flex', alignItems:'center', gap:8,
          padding:'6px 12px', borderRadius:8, border:'1.5px solid var(--border)',
          background:'var(--primary-lt)', color:'var(--primary-text)',
          cursor:'pointer', fontSize:13, fontWeight:600, transition:'all .15s',
        }}
        title="Competência (período de referência)"
      >
        <i className="ti ti-calendar-month" style={{ fontSize:15, flexShrink:0 }} />
        <span style={{ whiteSpace:'nowrap' }}>{label}</span>
        <i className={`ti ti-chevron-${open ? 'up' : 'down'}`} style={{ fontSize:12 }} />
      </button>

      {open && (
        <div style={{
          position:'absolute', top:'calc(100% + 6px)', right:0, zIndex:500,
          background:'var(--surface)', border:'1px solid var(--border)',
          borderRadius:16, boxShadow:'var(--shadow-lg)', width:300, overflow:'hidden',
        }}>
          <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', padding:'14px 16px 10px' }}>
            <button onClick={() => setViewYear(y => y - 1)}
              className="btn btn-ghost btn-icon" style={{ fontSize:16 }}>
              <i className="ti ti-chevron-left" />
            </button>
            <span style={{ fontWeight:600, fontSize:15, color:'var(--text-2)', letterSpacing:'0.5px' }}>{viewYear}</span>
            <button onClick={() => setViewYear(y => y + 1)}
              className="btn btn-ghost btn-icon" style={{ fontSize:16 }}>
              <i className="ti ti-chevron-right" />
            </button>
          </div>

          <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:6, padding:'4px 14px 14px' }}>
            {MESES_FULL.map((m, i) => {
              const isSel = selYear === viewYear && selMonth === i
              const isCur = today.getFullYear() === viewYear && today.getMonth() === i
              return (
                <button key={m} onClick={() => select(i)}
                  title={`${MESES_FULL[i]} de ${viewYear}`}
                  style={{
                    padding:'10px 4px', borderRadius:10, border:'none',
                    background: isSel ? 'var(--primary-lt)' : 'transparent',
                    color: isSel ? 'var(--primary-text)' : isCur ? 'var(--primary-text)' : 'var(--text-2)',
                    fontWeight: isSel ? 600 : 400,
                    fontSize:12.5, cursor:'pointer', transition:'all .12s',
                    fontFamily:'var(--font)', letterSpacing:'0.2px',
                    boxShadow: isCur && !isSel ? 'inset 0 0 0 1.5px var(--primary-lt2)' : 'none',
                  }}
                  onMouseEnter={e => { if (!isSel) e.currentTarget.style.background = 'var(--surface-2)' }}
                  onMouseLeave={e => { if (!isSel) e.currentTarget.style.background = 'transparent' }}
                >{m}</button>
              )
            })}
          </div>

          <div style={{ padding:'4px 14px 14px' }}>
            <button
              onClick={() => { const d = new Date(); setViewYear(d.getFullYear()); select(d.getMonth()) }}
              style={{ fontSize:12, color:'var(--primary-text)', background:'none', border:'none', cursor:'pointer', fontWeight:500, padding:'4px 6px', borderRadius:6 }}
            >Mês atual</button>
          </div>
        </div>
      )}
    </div>
  )
}
