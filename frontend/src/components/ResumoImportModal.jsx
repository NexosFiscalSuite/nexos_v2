/**
 * Modal "Resultado da Importação" — reusado por Matrizes e De/Para CFOP.
 * Resumo (✅ inseridas/atualizadas · ❌ com erro) + grid de erros por linha.
 */
export default function ResumoImportModal({ r, onClose }) {
  const ok = (r.inseridos || 0) + (r.atualizados || 0)
  const nErros = r.erros?.length || 0
  // "Ignoradas" existe onde a planilha admite linha em branco de propósito
  // (Exceção do Item: sem a marcação de tributado, nada é decidido). Vem como
  // lista de {linha, motivo}, no mesmo formato de `erros`.
  const ignoradas = r.ignoradas || []
  const nIgnorados = ignoradas.length
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={e => e.stopPropagation()} style={{ maxWidth: 620 }}>
        <div className="modal-header">
          <h2>Resultado da Importação</h2>
          <button className="btn btn-icon" onClick={onClose}><i className="ti ti-x" /></button>
        </div>
        <div className="modal-body">
          <div style={{ display: 'flex', gap: 12, marginBottom: nErros ? 18 : 0 }}>
            <div style={{ flex: 1, background: 'var(--ok-bg)', borderRadius: 'var(--radius)', padding: '12px 14px' }}>
              <div className="tnum" style={{ fontSize: 22, fontWeight: 700, color: 'var(--ok-text)' }}><i className="ti ti-circle-check" style={{ marginRight: 6 }} />{ok}</div>
              <div style={{ fontSize: 12, color: 'var(--ok-text)' }}>linha(s) inserida(s)/atualizada(s)</div>
            </div>
            {nIgnorados > 0 && (
              <div style={{ flex: 1, background: 'var(--surface-2)', borderRadius: 'var(--radius)', padding: '12px 14px' }}>
                <div className="tnum" style={{ fontSize: 22, fontWeight: 700, color: 'var(--text-3)' }}><i className="ti ti-minus" style={{ marginRight: 6 }} />{nIgnorados}</div>
                <div style={{ fontSize: 12, color: 'var(--text-3)' }}>linha(s) em branco, ignorada(s)</div>
              </div>
            )}
            <div style={{ flex: 1, background: nErros ? 'var(--err-bg)' : 'var(--surface-2)', borderRadius: 'var(--radius)', padding: '12px 14px' }}>
              <div className="tnum" style={{ fontSize: 22, fontWeight: 700, color: nErros ? 'var(--err-text)' : 'var(--text-4)' }}><i className="ti ti-circle-x" style={{ marginRight: 6 }} />{nErros}</div>
              <div style={{ fontSize: 12, color: nErros ? 'var(--err-text)' : 'var(--text-4)' }}>linha(s) com erro</div>
            </div>
          </div>

          {nIgnorados > 0 && (
            <p style={{ fontSize: 12.5, color: 'var(--text-3)', margin: '12px 0 0', lineHeight: 1.6 }}>
              Linha ignorada é linha sem decisão: a coluna de tratamento ficou em branco,
              então nada foi criado nem alterado para aquele produto. Basta marcar e reenviar.
            </p>
          )}

          {nErros > 0 && (
            <>
              <div className="section-label">Linhas não importadas</div>
              <div className="tbl-wrap" style={{ maxHeight: 280, overflowY: 'auto' }}>
                <table className="tbl">
                  <thead><tr><th style={{ width: 120 }}>Linha da planilha</th><th>Motivo do erro</th></tr></thead>
                  <tbody>
                    {r.erros.map(e => (
                      <tr key={e.linha}>
                        <td className="mono" style={{ fontWeight: 600 }}>{e.linha}</td>
                        <td style={{ color: 'var(--err-text)', fontSize: 13 }}>{e.erro}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 10 }}>
                As demais linhas foram aplicadas normalmente. Corrija as linhas acima na planilha e reimporte — o upsert não duplica o que já entrou.
              </p>
            </>
          )}
        </div>
        <div className="modal-footer">
          <button className="btn btn-primary" onClick={onClose}>Entendi</button>
        </div>
      </div>
    </div>
  )
}
