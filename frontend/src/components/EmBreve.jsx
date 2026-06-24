// Placeholder para páginas do V1 cujo endpoint ainda não existe no backend V2.
export default function EmBreve({ titulo = 'Em breve', descricao, icon = 'ti-tools' }) {
  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">{titulo}</h1>
      </div>
      <div className="empty-state" style={{ marginTop: 24 }}>
        <i className={`ti ${icon}`} style={{ fontSize: 40, color: 'var(--text-4)' }} />
        <p style={{ marginTop: 12, fontWeight: 500, color: 'var(--text-2, var(--text-1))' }}>
          Módulo em construção
        </p>
        <p style={{ color: 'var(--text-4)', maxWidth: 460, margin: '6px auto 0', fontSize: 13 }}>
          {descricao || 'Esta tela já existe no design, mas depende de um endpoint do backend que entra numa próxima fase.'}
        </p>
      </div>
    </div>
  )
}
