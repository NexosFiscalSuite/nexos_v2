/**
 * Empty state padrão: apenas ícone + título + subtítulo explicando o valor da
 * tela. A ação principal vive no botão do cabeçalho da página (sem duplicar aqui).
 */
export default function EmptyState({ icon, title, subtitle }) {
  return (
    <div className="empty-state">
      <i className={`ti ${icon}`} />
      <p className="empty-title">{title}</p>
      {subtitle && <p className="empty-subtitle">{subtitle}</p>}
    </div>
  )
}
