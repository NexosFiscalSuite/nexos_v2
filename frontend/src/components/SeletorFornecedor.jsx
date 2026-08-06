import { useState, useEffect, useRef, useCallback } from 'react'
import BalaoAjuda from './BalaoAjuda'
import { api } from '../api'

// Documento do fornecedor: CNPJ (14) ou CPF do produtor rural (11). O cadastro
// guarda SÓ os dígitos — a máscara existe para o olho de quem lê a tela.
export const digitosDoc = (v) => (v || '').replace(/\D/g, '')

export function formatarDoc(v) {
  const d = digitosDoc(v)
  if (d.length === 14) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
  if (d.length === 11) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`
  return d || ''
}

export const docValido = (v) => [11, 14].includes(digitosDoc(v).length)

// Cache de nomes por documento, compartilhado pela tela toda: o servidor devolve
// só o CNPJ da exceção, e é o cadastro de contrapartes que sabe o nome. Guardar
// "" (não encontrado) evita perguntar de novo o que já não existe no cadastro.
const nomesConhecidos = new Map()
export const nomeDoFornecedor = (doc) => nomesConhecidos.get(digitosDoc(doc)) || null

// Máximo de consultas disparadas por página da listagem: o servidor não aceita
// buscar vários CNPJs de uma vez, então o resto simplesmente fica só no número.
const LIMITE_LOOKUP = 20

async function resolverNomes(empresaId, docs) {
  const pendentes = [...new Set(docs.map(digitosDoc).filter(Boolean))]
    .filter(d => !nomesConhecidos.has(d))
    .slice(0, LIMITE_LOOKUP)
  if (!empresaId || !pendentes.length) return false
  await Promise.all(pendentes.map(async (d) => {
    try {
      const r = await api.contrapartes(empresaId, { search: d, page_size: 5 })
      const achado = (r?.items || (Array.isArray(r) ? r : []))
        .find(c => digitosDoc(c.cnpj) === d)
      nomesConhecidos.set(d, achado ? (achado.razao_social || achado.nome_fantasia || '') : '')
    } catch { /* sem nome: a tela mostra o documento e segue */ }
  }))
  return true
}

/**
 * Descobre a razão social dos fornecedores que aparecem numa lista de exceções.
 * Devolve um contador que muda quando os nomes chegam, para a tabela redesenhar.
 */
export function useNomesFornecedores(empresaId, docs) {
  const [versao, setVersao] = useState(0)
  const chave = [...new Set((docs || []).map(digitosDoc).filter(Boolean))].sort().join(',')
  useEffect(() => {
    if (!empresaId || !chave) return
    let vivo = true
    resolverNomes(empresaId, chave.split(','))
      .then(mudou => { if (vivo && mudou) setVersao(v => v + 1) })
    return () => { vivo = false }
  }, [empresaId, chave])
  return versao
}

/**
 * Seletor de fornecedor da exceção do item.
 *
 * Regra do produto: o código do produto é do FORNECEDOR. Vazio = "Qualquer
 * fornecedor" (padrão, comportamento de sempre); com documento preenchido a
 * exceção vale só para as notas daquele fornecedor.
 *
 * A busca vai no cadastro de contrapartes da empresa (tipo fornecedor), mas o
 * usuário NÃO fica preso à lista: digitando um CNPJ/CPF completo que ainda não
 * está cadastrado, o seletor oferece usar o documento assim mesmo — fornecedor
 * novo, nota recém-chegada.
 */
export default function SeletorFornecedor({
  empresaId, value, onChange, disabled = false,
  rotuloVazio = 'Qualquer fornecedor', semEmpresaTexto = 'Selecione uma empresa',
}) {
  const [aberto, setAberto] = useState(false)
  const [busca, setBusca] = useState('')
  const [opcoes, setOpcoes] = useState([])
  const [buscando, setBuscando] = useState(false)
  const [nome, setNome] = useState(() => nomeDoFornecedor(value))
  const ref = useRef(null)

  const doc = digitosDoc(value)

  useEffect(() => {
    function fora(e) { if (ref.current && !ref.current.contains(e.target)) setAberto(false) }
    document.addEventListener('mousedown', fora)
    return () => document.removeEventListener('mousedown', fora)
  }, [])

  // Nome do que já está escolhido: usa o cache e, se não souber, pergunta uma
  // vez ao servidor (fornecedor fora do cadastro simplesmente fica sem nome).
  useEffect(() => {
    let vivo = true
    if (!doc) { setNome(null); return }
    setNome(nomeDoFornecedor(doc))
    if (nomesConhecidos.has(doc) || !empresaId) return
    resolverNomes(empresaId, [doc]).then(() => { if (vivo) setNome(nomeDoFornecedor(doc)) })
    return () => { vivo = false }
  }, [doc, empresaId])

  const procurar = useCallback(async (termo) => {
    if (!empresaId) { setOpcoes([]); return }
    setBuscando(true)
    try {
      const r = await api.contrapartes(empresaId, {
        tipo: 'fornecedor', search: termo || undefined, page_size: 25,
      })
      const itens = r?.items || (Array.isArray(r) ? r : [])
      for (const c of itens) {
        nomesConhecidos.set(digitosDoc(c.cnpj), c.razao_social || c.nome_fantasia || '')
      }
      setOpcoes(itens)
    } catch { setOpcoes([]) }
    finally { setBuscando(false) }
  }, [empresaId])

  useEffect(() => {
    if (!aberto) return
    const t = setTimeout(() => procurar(digitosDoc(busca) || busca), 250)
    return () => clearTimeout(t)
  }, [aberto, busca, procurar])

  function escolher(novoDoc) {
    onChange(digitosDoc(novoDoc))
    setAberto(false)
    setBusca('')
  }

  const digitado = digitosDoc(busca)
  const jaNaLista = opcoes.some(c => digitosDoc(c.cnpj) === digitado)
  const rotulo = !doc
    ? rotuloVazio
    : (nome ? `${nome} · ${formatarDoc(doc)}` : formatarDoc(doc))

  return (
    <div ref={ref} style={{ position: 'relative' }}>
      <button type="button" disabled={disabled} onClick={() => !disabled && setAberto(a => !a)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8,
          padding: '9px 12px', fontSize: 13, fontFamily: 'inherit', textAlign: 'left',
          border: '1.5px solid var(--border)', borderRadius: 'var(--radius)',
          background: disabled ? 'var(--surface-2)' : 'var(--surface)',
          color: doc ? 'var(--text-1)' : 'var(--text-4)',
          cursor: disabled ? 'not-allowed' : 'pointer', opacity: disabled ? 0.7 : 1,
          boxShadow: aberto ? '0 0 0 3px rgba(243,146,0,0.18)' : 'none',
          borderColor: aberto ? 'var(--primary)' : 'var(--border)',
        }}>
        <span style={{ display: 'inline-flex', alignItems: 'center', gap: 7, overflow: 'hidden' }}>
          <i className={`ti ${doc ? 'ti-truck-delivery' : 'ti-world'}`} style={{ fontSize: 15, flexShrink: 0, color: 'var(--text-4)' }} />
          <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{rotulo}</span>
        </span>
        <i className={`ti ti-chevron-${aberto ? 'up' : 'down'}`} style={{ fontSize: 14, color: 'var(--text-4)', flexShrink: 0 }} />
      </button>

      {aberto && (
        <div style={{
          position: 'absolute', top: 'calc(100% + 4px)', left: 0, right: 0, zIndex: 60,
          background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 'var(--radius-lg)',
          boxShadow: '0 8px 24px rgba(0,0,0,0.12)', overflow: 'hidden', padding: 4, minWidth: 300,
        }}>
          <div style={{ padding: 4 }}>
            <input autoFocus value={busca} onChange={e => setBusca(e.target.value)}
              placeholder="Buscar por nome ou CNPJ…" style={{ width: '100%', fontSize: 13 }} />
          </div>

          <div style={{ maxHeight: 240, overflowY: 'auto' }}>
            <OpcaoFornecedor selecionado={!doc} onClick={() => escolher('')}
              titulo={rotuloVazio} detalhe="Vale para as notas de todos os fornecedores" icone="ti-world" />

            {!empresaId && (
              <p style={{ padding: '10px 12px', margin: 0, fontSize: 12, color: 'var(--text-4)' }}>{semEmpresaTexto}</p>
            )}

            {empresaId && buscando && (
              <p style={{ padding: '10px 12px', margin: 0, fontSize: 12, color: 'var(--text-4)' }}>Procurando…</p>
            )}

            {empresaId && !buscando && opcoes.map(c => (
              <OpcaoFornecedor key={c.id || c.cnpj} selecionado={digitosDoc(c.cnpj) === doc}
                onClick={() => escolher(c.cnpj)} icone="ti-truck-delivery"
                titulo={c.razao_social || c.nome_fantasia || formatarDoc(c.cnpj)}
                detalhe={formatarDoc(c.cnpj)} />
            ))}

            {empresaId && !buscando && !opcoes.length && busca && !docValido(busca) && (
              <p style={{ padding: '10px 12px', margin: 0, fontSize: 12, color: 'var(--text-4)' }}>
                Nenhum fornecedor com esse nome. Digite o CNPJ completo para usar um
                fornecedor que ainda não está no cadastro.
              </p>
            )}

            {empresaId && docValido(busca) && !jaNaLista && (
              <OpcaoFornecedor selecionado={false} onClick={() => escolher(busca)} icone="ti-plus"
                titulo={`Usar ${formatarDoc(busca)}`}
                detalhe="Ainda não está no cadastro — pode usar assim mesmo" />
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// Explicação do conceito, em linguagem de leigo — usada no rótulo do campo e no
// cabeçalho da coluna. Balão CLICÁVEL, nunca tooltip de hover.
export function AjudaFornecedor() {
  return (
    <BalaoAjuda titulo="Por que a exceção pergunta o fornecedor">
      O código que aparece no item da nota é o código <strong>do fornecedor</strong> —
      cada um numera os produtos do seu jeito. Por isso dois fornecedores podem usar
      o <strong>mesmo código para produtos diferentes</strong>, e o mesmo produto pode
      ter um código em cada fornecedor.
      <br /><br />
      Amarrando a exceção ao fornecedor, a decisão vale só para as notas dele: o
      tratamento não escapa para o produto de outro fornecedor que por acaso usa
      aquele mesmo número.
      <br /><br />
      Deixe em <strong>“Qualquer fornecedor”</strong> quando a decisão valer para
      todos — é o padrão e o comportamento de sempre. Se existirem as duas regras
      para o mesmo código, a do fornecedor específico é a que vale.
    </BalaoAjuda>
  )
}

function OpcaoFornecedor({ selecionado, onClick, titulo, detalhe, icone }) {
  return (
    <button type="button" onClick={onClick}
      style={{
        width: '100%', textAlign: 'left', padding: '8px 10px', fontSize: 13, fontFamily: 'inherit',
        border: 'none', borderRadius: 'var(--radius)', cursor: 'pointer',
        background: selecionado ? 'var(--primary-lt)' : 'transparent',
        color: selecionado ? 'var(--primary-text)' : 'var(--text-1)',
        display: 'flex', alignItems: 'center', gap: 9,
      }}
      onMouseEnter={e => { if (!selecionado) e.currentTarget.style.background = 'var(--surface-2)' }}
      onMouseLeave={e => { if (!selecionado) e.currentTarget.style.background = 'transparent' }}>
      <i className={`ti ${icone}`} style={{ fontSize: 15, flexShrink: 0, opacity: .7 }} />
      <span style={{ overflow: 'hidden' }}>
        <span style={{ display: 'block', fontWeight: selecionado ? 650 : 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{titulo}</span>
        <span className="tnum" style={{ display: 'block', fontSize: 11.5, color: 'var(--text-4)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{detalhe}</span>
      </span>
      {selecionado && <i className="ti ti-check" style={{ marginLeft: 'auto', fontSize: 15, color: 'var(--primary-text)', flexShrink: 0 }} />}
    </button>
  )
}
