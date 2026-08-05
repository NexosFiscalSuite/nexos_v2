import { useEffect, useRef, useState } from 'react'

const MESES = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
]
const SEMANA = ['D', 'S', 'T', 'Q', 'Q', 'S', 'S']

function parseIso(value) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return null
  const [ano, mes, dia] = value.split('-').map(Number)
  const data = new Date(ano, mes - 1, dia)
  return Number.isNaN(data.getTime()) ? null : data
}

function iso(data) {
  return [data.getFullYear(), String(data.getMonth() + 1).padStart(2, '0'),
    String(data.getDate()).padStart(2, '0')].join('-')
}

function formatar(value) {
  const data = parseIso(value)
  return data ? data.toLocaleDateString('pt-BR') : ''
}

export default function DatePicker({ value = '', onChange, placeholder = 'dd/mm/aaaa', required = false }) {
  const hoje = new Date()
  const selecionada = parseIso(value)
  const [open, setOpen] = useState(false)
  const [view, setView] = useState(() => selecionada || hoje)
  const ref = useRef(null)

  useEffect(() => {
    if (selecionada) setView(selecionada)
  }, [value]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    function fechar(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', fechar)
    return () => document.removeEventListener('mousedown', fechar)
  }, [])

  const ano = view.getFullYear()
  const mes = view.getMonth()
  const primeiro = new Date(ano, mes, 1)
  const inicio = new Date(ano, mes, 1 - primeiro.getDay())
  const dias = Array.from({ length: 42 }, (_, i) => new Date(
    inicio.getFullYear(), inicio.getMonth(), inicio.getDate() + i,
  ))

  function mudarMes(delta) { setView(new Date(ano, mes + delta, 1)) }
  function escolher(data) { onChange(iso(data)); setOpen(false) }

  return (
    <div ref={ref} style={{ position: 'relative', width: '100%' }}>
      <button type="button" onClick={() => setOpen(o => !o)} aria-expanded={open}
        style={{
          width: '100%', height: 38, padding: '0 12px', borderRadius: 8,
          border: `1px solid ${open ? 'var(--primary)' : 'var(--border)'}`,
          background: 'var(--surface)', color: value ? 'var(--text-1)' : 'var(--text-4)',
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          cursor: 'pointer', fontFamily: 'var(--font)', fontSize: 13,
          boxShadow: open ? '0 0 0 3px var(--primary-lt)' : 'none',
        }}>
        <span>{formatar(value) || placeholder}</span>
        <i className="ti ti-calendar" style={{ fontSize: 16, color: 'var(--text-3)' }} />
      </button>
      {required && <input tabIndex={-1} aria-hidden="true" required value={value} onChange={() => {}}
        style={{ position: 'absolute', width: 1, height: 1, opacity: 0, pointerEvents: 'none' }} />}

      {open && <div style={{
        position: 'absolute', top: 'calc(100% + 7px)', left: 0, zIndex: 900,
        width: 304, padding: 14, background: 'var(--surface)', border: '1px solid var(--border)',
        borderRadius: 14, boxShadow: 'var(--shadow-lg)', userSelect: 'none',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <button type="button" className="btn btn-ghost btn-icon" onClick={() => mudarMes(-1)} aria-label="Mês anterior">
            <i className="ti ti-chevron-left" />
          </button>
          <strong style={{ color: 'var(--text-1)', fontSize: 14 }}>{MESES[mes]} de {ano}</strong>
          <button type="button" className="btn btn-ghost btn-icon" onClick={() => mudarMes(1)} aria-label="Próximo mês">
            <i className="ti ti-chevron-right" />
          </button>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: 3 }}>
          {SEMANA.map((dia, i) => <div key={`${dia}-${i}`} style={{
            textAlign: 'center', color: 'var(--text-4)', fontSize: 11, fontWeight: 700,
            padding: '4px 0 6px',
          }}>{dia}</div>)}
          {dias.map(data => {
            const chave = iso(data)
            const selecionado = chave === value
            const atual = chave === iso(hoje)
            const fora = data.getMonth() !== mes
            return <button key={chave} type="button" onClick={() => escolher(data)} style={{
              height: 34, padding: 0, borderRadius: 9,
              border: atual && !selecionado ? '1px solid var(--primary)' : '1px solid transparent',
              background: selecionado ? 'var(--primary)' : 'transparent',
              color: selecionado ? 'var(--primary-contrast)' : fora ? 'var(--text-4)' : 'var(--text-2)',
              fontWeight: selecionado || atual ? 700 : 450, fontSize: 12, cursor: 'pointer',
            }}>{data.getDate()}</button>
          })}
        </div>

        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--border-2)' }}>
          <button type="button" className="btn btn-ghost btn-sm" disabled={!value} onClick={() => { onChange(''); setOpen(false) }}>Limpar</button>
          <button type="button" className="btn btn-ghost btn-sm" onClick={() => escolher(hoje)}>Hoje</button>
        </div>
      </div>}
    </div>
  )
}
