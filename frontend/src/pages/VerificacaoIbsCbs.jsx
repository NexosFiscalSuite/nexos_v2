import { useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import ErroCarga from '../components/ErroCarga'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useToast, ToastContainer } from '../hooks/useToast'

const brl = (v) => Number(v || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })
const pct = (v) => (v == null ? '—' : `${Number(v).toFixed(2)}%`)
const cnpjFmt = (c) => (c && c.length === 14 ? c.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, '$1.$2.$3/$4-$5') : c || '—')

// Ordem de exibição dos cards + tom visual de cada situação.
const STATUS_INFO = [
  ['SEM_DESTAQUE',        { label: 'Sem destaque',       tone: 'err',  icon: 'ti-file-off',        desc: 'Regime normal sem o grupo IBS/CBS no XML' }],
  ['ALIQUOTA_DIVERGENTE', { label: 'Alíquota errada',    tone: 'warn', icon: 'ti-percentage',      desc: 'Fora dos 0,1% (IBS) + 0,9% (CBS) de teste' }],
  ['VALOR_DIVERGENTE',    { label: 'Valor não fecha',    tone: 'warn', icon: 'ti-calculator-off',  desc: 'Alíquota certa, mas base × alíquota ≠ destacado' }],
  ['OK',                  { label: 'Corretos',           tone: 'ok',   icon: 'ti-circle-check',    desc: 'Destaque presente e conferido' }],
  ['DISPENSADO',          { label: 'Dispensados',        tone: 'info', icon: 'ti-user-check',      desc: 'Emitente do Simples/MEI (CRT 1/4)' }],
]
const TONE = Object.fromEntries(STATUS_INFO)

const badge = (txt, tone = 'info') => (
  <span className="badge" style={{ background: `var(--${tone}-bg)`, color: `var(--${tone}-text)` }}>{txt}</span>
)

export default function VerificacaoIbsCbs() {
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { toasts, toast } = useToast()
  const [dados, setDados] = useState(null)
  const [loading, setLoading] = useState(true)
  const [erro, setErro] = useState(null)
  const [busy, setBusy] = useState(false)

  const params = useCallback(() => ({
    empresa_id: selectedEmpresa?.id, ano, mes,
  }), [selectedEmpresa, ano, mes])

  const carregar = useCallback(async () => {
    setLoading(true)
    setErro(null)
    try { setDados(await api.ibsCbsVerificacao(params())) }
    catch (e) { setErro(e.message) }
    finally { setLoading(false) }
  }, [params])

  useEffect(() => { carregar() }, [carregar])

  async function reprocessar() {
    if (!confirm('Reler os XMLs armazenados do período para preencher os campos de IBS/CBS? (necessário só para notas importadas antes deste módulo existir)')) return
    setBusy(true)
    try {
      const r = await api.ibsCbsReprocessar(params())
      toast(`${r.notas_reprocessadas} nota(s) reprocessada(s)` + (r.falhas_leitura ? ` · ${r.falhas_leitura} falha(s) de leitura` : ''), 'ok')
      carregar()
    } catch (e) { toast(e.message, 'error') }
    finally { setBusy(false) }
  }

  const resumo = dados?.resumo || {}
  const conforme = dados?.pct_conforme ?? 100

  return (
    <div>
      <ToastContainer toasts={toasts} />
      <div className="page-header">
        <div>
          <h1 className="page-title">IBS/CBS — Ano-teste 2026</h1>
          <p className="page-breadcrumb">
            Destaque obrigatório de IBS 0,1% + CBS 0,9% (EC 132, ADCT art. 125) ·{' '}
            {selectedEmpresa ? selectedEmpresa.razao_social : 'todas as empresas'} · {mes}/{ano}
          </p>
        </div>
        <button className="btn btn-secondary" disabled={busy} onClick={reprocessar}>
          <i className="ti ti-refresh" /> {busy ? 'Reprocessando…' : 'Reprocessar XMLs'}
        </button>
      </div>

      {loading ? (
        <div className="center-loader"><div className="spinner" /></div>
      ) : erro ? (
        <ErroCarga mensagem={erro} onRetry={carregar} />
      ) : (dados?.total_itens || 0) === 0 ? (
        <div className="empty-state">
          <i className="ti ti-flask" />
          <p className="empty-title">Nenhum item para verificar</p>
          <p className="empty-subtitle">Importe XMLs de 2026 desta competência — ou use "Reprocessar XMLs" se as notas foram importadas antes deste módulo.</p>
        </div>
      ) : (
        <>
          {/* Termômetro + cards por situação */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))', gap: 12, marginBottom: 20 }}>
            <div className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
              <span style={{ fontSize: 12, color: 'var(--text-3)' }}>Conformidade</span>
              <span style={{ fontSize: 26, fontWeight: 800, color: conforme >= 90 ? 'var(--ok-text)' : 'var(--err-text)' }}>{conforme}%</span>
              <span style={{ fontSize: 11, color: 'var(--text-4)' }}>{dados.total_itens} item(ns) verificados</span>
            </div>
            {STATUS_INFO.map(([key, info]) => (
              <div key={key} className="card" style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 4 }}>
                <span style={{ fontSize: 12, color: 'var(--text-3)' }}><i className={`ti ${info.icon}`} /> {info.label}</span>
                <span style={{ fontSize: 22, fontWeight: 700, color: `var(--${info.tone}-text)` }}>{resumo[key]?.itens || 0}</span>
                <span style={{ fontSize: 11, color: 'var(--text-4)' }} title={info.desc}>{brl(resumo[key]?.valor)}</span>
              </div>
            ))}
          </div>

          {/* Ranking de emitentes com problema */}
          {(dados.ranking_emitentes || []).length > 0 && (
            <div className="card" style={{ padding: 0, marginBottom: 20 }}>
              <div style={{ padding: '12px 16px', fontWeight: 600, borderBottom: '1px solid var(--border-2)' }}>
                Emitentes com pendência — priorize o contato pelos maiores valores
              </div>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead><tr><th>Emitente</th><th>CNPJ</th><th style={{ textAlign: 'right' }}>Itens</th><th style={{ textAlign: 'right' }}>Valor movimentado</th><th>Situações</th></tr></thead>
                  <tbody>
                    {dados.ranking_emitentes.map(e => (
                      <tr key={e.cnpj}>
                        <td style={{ fontWeight: 500, color: 'var(--text-1)' }}>{e.nome || '—'}</td>
                        <td className="mono">{cnpjFmt(e.cnpj)}</td>
                        <td style={{ textAlign: 'right' }}>{e.itens}</td>
                        <td style={{ textAlign: 'right', fontWeight: 600 }}>{brl(e.valor)}</td>
                        <td>{Object.entries(e.status).map(([s, n]) => (
                          <span key={s} style={{ marginRight: 6 }}>{badge(`${TONE[s]?.label || s}: ${n}`, TONE[s]?.tone)}</span>
                        ))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Itens apontados */}
          {(dados.itens || []).length > 0 && (
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: '12px 16px', fontWeight: 600, borderBottom: '1px solid var(--border-2)' }}>
                Itens apontados {dados.itens.length >= 500 ? '(primeiros 500)' : `(${dados.itens.length})`}
              </div>
              <div className="tbl-wrap">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th>Situação</th><th>Emissão</th><th>NF / Item</th><th>Emitente</th>
                      <th style={{ textAlign: 'right' }}>Valor item</th>
                      <th style={{ textAlign: 'right' }}>pIBS</th><th style={{ textAlign: 'right' }}>vIBS</th>
                      <th style={{ textAlign: 'right' }}>pCBS</th><th style={{ textAlign: 'right' }}>vCBS</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dados.itens.map((i, idx) => (
                      <tr key={`${i.chave_acesso}-${i.numero_item}-${idx}`}>
                        <td>{badge(TONE[i.status]?.label || i.status, TONE[i.status]?.tone)}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{(i.data_emissao || '').split('-').reverse().join('/')}</td>
                        <td className="mono">{i.numero_nota} / {i.numero_item}</td>
                        <td style={{ maxWidth: 220, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={i.emitente}>{i.emitente}</td>
                        <td style={{ textAlign: 'right' }}>{brl(i.valor_produto)}</td>
                        <td style={{ textAlign: 'right' }}>{pct(i.p_ibs)}</td>
                        <td style={{ textAlign: 'right' }}>{brl(i.v_ibs)}</td>
                        <td style={{ textAlign: 'right' }}>{pct(i.p_cbs)}</td>
                        <td style={{ textAlign: 'right' }}>{brl(i.v_cbs)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
