import { useState, useCallback } from 'react'
import { api } from '../api'

// ── "Por que não achamos a margem" ────────────────────────────────────────────
// Bloco que abre DENTRO do balão do item que caiu em ERRO_MVA_NAO_ENCONTRADA e
// mostra o que EXISTE na matriz para aquele produto — em vez de só repetir que
// não há MVA cadastrada. A consulta usa a data de EMISSÃO da nota (é ela que
// decide a vigência), nunca a data de hoje, e só sai quando o usuário abre o
// bloco: a tela de divergências pode ter centenas de itens.

const dataBr = (v) => {
  if (!v) return null
  const s = String(v).slice(0, 10)
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s
}

// Período de vigência em linguagem de gente: sem data final é "desde ...".
function vigenciaBr(inicio, fim) {
  const a = dataBr(inicio)
  const b = dataBr(fim)
  if (a && b) return `${a} a ${b}`
  if (a) return `desde ${a}`
  if (b) return `até ${b}`
  return 'sem período informado'
}

// Origem "*" é o coringa do motor (vale para qualquer estado remetente) — na
// tela ele nunca aparece cru.
const origemBr = (uf) => (!uf || uf === '*' ? 'Qualquer origem' : uf)

const mvaBr = (v) => (v == null || v === ''
  ? '—'
  : `${Number(v).toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`)

// Veredictos do backend → cor, ícone e uma frase de reserva (se a explicação
// vier vazia, o bloco continua dizendo alguma coisa útil).
const VEREDICTOS = {
  ENCONTRADA: {
    icone: 'ti-circle-check', bg: 'var(--ok-bg)', fg: 'var(--ok-text)',
    frase: 'Existe margem cadastrada e válida para este produto na data da nota.',
  },
  SEM_LINHA_NENHUMA: {
    icone: 'ti-database-off', bg: 'var(--warn-bg)', fg: 'var(--warn-text)',
    frase: 'Nossa matriz não tem nenhuma linha de margem para este produto neste estado.',
  },
  FORA_DA_VIGENCIA: {
    icone: 'ti-calendar-off', bg: 'var(--warn-bg)', fg: 'var(--warn-text)',
    frase: 'Existem linhas de margem para este produto, mas nenhuma valia na data de emissão da nota.',
  },
  ORIGEM_NAO_COBERTA: {
    icone: 'ti-map-pin-off', bg: 'var(--warn-bg)', fg: 'var(--warn-text)',
    frase: 'As linhas cadastradas valem para outros estados de origem, não para o desta nota.',
  },
  CEST_NAO_BATE: {
    icone: 'ti-barcode-off', bg: 'var(--warn-bg)', fg: 'var(--warn-text)',
    frase: 'As linhas cadastradas estão em outro CEST — o CEST da nota não bate com o da matriz.',
  },
  AMBIGUA: {
    icone: 'ti-arrows-split', bg: 'var(--warn-bg)', fg: 'var(--warn-text)',
    frase: 'Mais de uma linha serve para esta nota ao mesmo tempo, então o motor não escolhe nenhuma.',
  },
}
const VEREDICTO_PADRAO = {
  icone: 'ti-help-circle', bg: 'var(--surface-2)', fg: 'var(--text-2)',
  frase: 'Consultamos a matriz de margem para este produto.',
}

export default function DiagnosticoMva({ consulta }) {
  const [aberto, setAberto] = useState(false)
  const [carregando, setCarregando] = useState(false)
  const [erro, setErro] = useState(null)
  const [dados, setDados] = useState(null)

  const buscar = useCallback(async () => {
    setCarregando(true)
    setErro(null)
    try {
      const r = await api.mvaDiagnostico(consulta)
      setDados(r || {})
    } catch (e) {
      setErro(e?.message || 'Falha ao consultar a matriz de margem.')
    } finally {
      setCarregando(false)
    }
  }, [consulta])

  function alternar(e) {
    e.stopPropagation()
    const vai = !aberto
    setAberto(vai)
    // Carga sob demanda: só na primeira abertura (e no "tentar de novo").
    if (vai && !dados && !carregando) buscar()
  }

  const c = (dados && dados.consulta) || consulta || {}
  const veredicto = dados?.veredicto
  const tom = VEREDICTOS[veredicto] || VEREDICTO_PADRAO
  const candidatas = Array.isArray(dados?.candidatas) ? dados.candidatas : []
  const aplicada = dados?.aplicada || null
  const idAplicada = aplicada?.id ?? null

  return (
    <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-2)' }}>
      <button type="button" onClick={alternar}
        title="Mostra o que existe na nossa matriz de margem para este produto"
        style={{
          display: 'flex', alignItems: 'center', gap: 6, width: '100%', textAlign: 'left',
          background: 'transparent', border: 'none', padding: 0, cursor: 'pointer',
          fontFamily: 'inherit', fontSize: 12.5, fontWeight: 700, color: 'var(--text-1)',
        }}>
        <i className={`ti ti-chevron-${aberto ? 'down' : 'right'}`} style={{ fontSize: 13, color: 'var(--text-3)' }} />
        <i className="ti ti-search" style={{ fontSize: 13, color: 'var(--primary)' }} />
        <span>Por que não achamos a margem</span>
      </button>

      {aberto && (
        <div style={{ marginTop: 8, fontSize: 12, color: 'var(--text-2)', lineHeight: 1.55 }}>
          <div style={{ fontSize: 11.5, color: 'var(--text-4)', marginBottom: 7 }}>
            Procuramos por NCM <span className="mono">{c.ncm || '—'}</span>
            {c.cest ? <> · CEST <span className="mono">{c.cest}</span></> : ' · sem CEST na nota'}
            {' · '}{origemBr(c.uf_origem)} → {c.uf_destino || '—'}
            {' · '}
            {consulta?.data
              ? <>na data de emissão da nota (<span className="tnum">{dataBr(c.data) || '—'}</span>)</>
              : <>na data de hoje (<span className="tnum">{dataBr(c.data) || '—'}</span>) — a nota não trouxe data de emissão</>}
          </div>

          {carregando && (
            <div style={{ color: 'var(--text-3)' }}>
              <i className="ti ti-loader-2" style={{ marginRight: 5, display: 'inline-block', animation: 'spin .8s linear infinite' }} />
              Consultando a matriz…
            </div>
          )}

          {!carregando && erro && (
            <div style={{ background: 'var(--surface-2)', borderRadius: 8, padding: '9px 11px' }}>
              <div style={{ color: 'var(--text-2)' }}>
                <i className="ti ti-plug-connected-x" style={{ marginRight: 5, color: 'var(--warn-text)' }} />
                Não conseguimos consultar a matriz de margem agora. O item segue apontado
                normalmente — isto aqui é só a explicação detalhada.
              </div>
              <div style={{ fontSize: 11, color: 'var(--text-4)', marginTop: 4 }}>{erro}</div>
              <button type="button" className="btn btn-secondary btn-sm"
                style={{ marginTop: 7, padding: '3px 10px', fontSize: 11.5 }}
                onClick={(e) => { e.stopPropagation(); buscar() }}>
                <i className="ti ti-refresh" /> Tentar de novo
              </button>
            </div>
          )}

          {!carregando && !erro && dados && (
            <>
              <div style={{ background: tom.bg, color: tom.fg, borderRadius: 8, padding: '9px 11px', fontWeight: 600 }}>
                <i className={`ti ${tom.icone}`} style={{ marginRight: 5 }} />
                {dados.explicacao || tom.frase}
              </div>

              {dados.acao_sugerida && (
                <div style={{ marginTop: 7 }}>
                  <strong style={{ color: 'var(--accent-text)' }}>O que fazer:</strong> {dados.acao_sugerida}
                </div>
              )}

              <div style={{ marginTop: 9, fontWeight: 700, color: 'var(--text-1)' }}>
                O que existe na matriz hoje
                {candidatas.length > 0 && (
                  <span style={{ fontWeight: 400, color: 'var(--text-4)' }}> — {candidatas.length} linha(s)</span>
                )}
              </div>

              {candidatas.length === 0 ? (
                <div style={{ marginTop: 5, color: 'var(--text-3)' }}>
                  Nenhuma linha cadastrada para este produto neste estado — a margem precisa
                  ser incluída na matriz (ou importada do anexo da legislação) antes de
                  reprocessar a nota.
                </div>
              ) : (
                <div style={{ marginTop: 5, maxHeight: 210, overflowY: 'auto', border: '1px solid var(--border-2)', borderRadius: 8 }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 11.5 }}>
                    <thead>
                      <tr style={{ background: 'var(--surface-2)', color: 'var(--text-3)' }}>
                        <th style={{ textAlign: 'right', padding: '5px 8px', fontWeight: 600 }}>Margem</th>
                        <th style={{ textAlign: 'left', padding: '5px 8px', fontWeight: 600 }}>De → para</th>
                        <th style={{ textAlign: 'left', padding: '5px 8px', fontWeight: 600 }}>Vigência</th>
                        <th style={{ textAlign: 'left', padding: '5px 8px', fontWeight: 600 }}>Situação</th>
                      </tr>
                    </thead>
                    <tbody>
                      {candidatas.map((l, i) => {
                        const casou = l.casou === true || (idAplicada != null && l.id === idAplicada)
                        return (
                          <tr key={l.id ?? i} style={{
                            borderTop: '1px solid var(--border-2)',
                            background: casou ? 'var(--ok-bg)' : undefined,
                          }}>
                            <td className="tnum" style={{ textAlign: 'right', padding: '5px 8px', fontWeight: casou ? 700 : 500 }}>
                              {mvaBr(l.mva_original)}
                            </td>
                            <td style={{ padding: '5px 8px', whiteSpace: 'nowrap' }}>
                              {origemBr(l.uf_origem)} → {l.uf_destino || '—'}
                              {l.cest ? <div className="mono" style={{ fontSize: 10.5, color: 'var(--text-4)' }}>CEST {l.cest}</div> : null}
                            </td>
                            <td className="tnum" style={{ padding: '5px 8px', whiteSpace: 'nowrap' }}>
                              {vigenciaBr(l.data_inicio_vigencia, l.data_fim_vigencia)}
                            </td>
                            <td style={{ padding: '5px 8px', color: casou ? 'var(--ok-text)' : 'var(--text-3)' }}>
                              {casou
                                ? <><i className="ti ti-check" style={{ marginRight: 3 }} />Serve para esta nota</>
                                : (l.motivo || 'Não serve para esta nota')}
                              {l.base_legal && (
                                <div style={{ fontSize: 10.5, color: 'var(--text-4)', marginTop: 2 }}>{l.base_legal}</div>
                              )}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              )}

              {veredicto !== 'ENCONTRADA' && (
                <div style={{ marginTop: 8, fontSize: 11.5, color: 'var(--text-4)', lineHeight: 1.5 }}>
                  <i className="ti ti-info-circle" style={{ marginRight: 4 }} />
                  Margem que falta é lacuna da nossa base de regras, não erro de quem emitiu a
                  nota: assim que a linha certa entrar na matriz, é só reprocessar que o
                  cálculo sai completo.
                </div>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}
