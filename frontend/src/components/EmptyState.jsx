/**
 * Empty state padrão: ícone + título + subtítulo (o valor da tela) e, opcional,
 * o botão de ação principal centralizado logo abaixo — para o usuário agir sem
 * caçar o botão no topo.
 */
export default function EmptyState({ icon, title, subtitle, actionLabel, onAction, actionIcon = 'ti-plus' }) {
  return (
    <div className="empty-state">
      <i className={`ti ${icon}`} />
      <p className="empty-title">{title}</p>
      {subtitle && <p className="empty-subtitle">{subtitle}</p>}
      {actionLabel && onAction && (
        <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={onAction}>
          <i className={`ti ${actionIcon}`} /> {actionLabel}
        </button>
      )}
    </div>
  )
}
