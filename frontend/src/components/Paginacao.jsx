// Controles de paginação padrão (janela: 1 … 4 [5] 6 … 20) — o mesmo desenho
// de Empresas/Matrizes, agora num componente só. `total` é em ITENS; com uma
// página só, não renderiza nada.
export default function Paginacao({ page, total, pageSize, onChange }) {
  const totalPaginas = Math.max(1, Math.ceil((total || 0) / pageSize))
  if (totalPaginas <= 1) return null
  const nums = []
  for (let i = 1; i <= totalPaginas; i++) {
    if (i === 1 || i === totalPaginas || Math.abs(i - page) <= 2) nums.push(i)
    else if (nums[nums.length - 1] !== '…') nums.push('…')
  }
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4, padding: 12, borderTop: '1px solid var(--border-2)' }}>
      <button className="btn btn-ghost btn-sm" disabled={page === 1} onClick={() => onChange(page - 1)}>
        <i className="ti ti-chevron-left" />
      </button>
      {nums.map((n, i) => n === '…'
        ? <span key={`e${i}`} style={{ padding: '0 6px', color: 'var(--text-4)' }}>…</span>
        : (
          <button key={n} onClick={() => onChange(n)} className="btn btn-sm"
            style={{
              minWidth: 32, justifyContent: 'center', border: 'none',
              background: n === page ? 'var(--primary)' : 'transparent',
              color: n === page ? '#fff' : 'var(--text-2)', fontWeight: n === page ? 700 : 500,
            }}>{n}</button>
        ))}
      <button className="btn btn-ghost btn-sm" disabled={page === totalPaginas} onClick={() => onChange(page + 1)}>
        <i className="ti ti-chevron-right" />
      </button>
    </div>
  )
}
