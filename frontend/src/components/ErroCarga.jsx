// Estado de ERRO de carregamento — distinto do estado vazio, de propósito:
// numa ferramenta de auditoria, falha de rede exibida como lista vazia parece
// "nenhuma divergência" e engana o analista. Erro tem cara de erro, com retry.
export default function ErroCarga({ mensagem, onRetry }) {
  return (
    <div className="empty-state">
      <i className="ti ti-plug-connected-x" style={{ color: 'var(--err-text)' }} />
      <p className="empty-title">Não foi possível carregar</p>
      <p className="empty-subtitle">{mensagem || 'Falha de comunicação com o servidor.'}</p>
      {onRetry && (
        <button className="btn btn-secondary" style={{ marginTop: 10 }} onClick={onRetry}>
          <i className="ti ti-refresh" /> Tentar novamente
        </button>
      )}
    </div>
  )
}
