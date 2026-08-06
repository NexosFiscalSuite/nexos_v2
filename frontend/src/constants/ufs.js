// Fonte única das UFs para os seletores da aplicação.
//
// Por que existe: enquanto a UF era campo de texto livre, o usuário digitava
// "Minas Gerais" ou "mg" e a linha entrava torta na matriz — o motor procura
// pela SIGLA em maiúsculas e nunca encontrava, então o cálculo saía errado
// mesmo com a regra cadastrada. Com a lista fechada, a sigla é sempre válida.
//
// O servidor expõe GET /matrizes/ufs como fonte oficial; a lista abaixo é o
// fallback local, que mantém a tela funcionando se o endpoint falhar (ou se o
// servidor ainda não tiver a rota). São dados estáveis: as 27 unidades da
// federação não mudam.

import { useEffect, useState } from 'react'
import { api } from '../api'

export const UFS = [
  { sigla: 'AC', nome: 'Acre' },
  { sigla: 'AL', nome: 'Alagoas' },
  { sigla: 'AM', nome: 'Amazonas' },
  { sigla: 'AP', nome: 'Amapá' },
  { sigla: 'BA', nome: 'Bahia' },
  { sigla: 'CE', nome: 'Ceará' },
  { sigla: 'DF', nome: 'Distrito Federal' },
  { sigla: 'ES', nome: 'Espírito Santo' },
  { sigla: 'GO', nome: 'Goiás' },
  { sigla: 'MA', nome: 'Maranhão' },
  { sigla: 'MG', nome: 'Minas Gerais' },
  { sigla: 'MS', nome: 'Mato Grosso do Sul' },
  { sigla: 'MT', nome: 'Mato Grosso' },
  { sigla: 'PA', nome: 'Pará' },
  { sigla: 'PB', nome: 'Paraíba' },
  { sigla: 'PE', nome: 'Pernambuco' },
  { sigla: 'PI', nome: 'Piauí' },
  { sigla: 'PR', nome: 'Paraná' },
  { sigla: 'RJ', nome: 'Rio de Janeiro' },
  { sigla: 'RN', nome: 'Rio Grande do Norte' },
  { sigla: 'RO', nome: 'Rondônia' },
  { sigla: 'RR', nome: 'Roraima' },
  { sigla: 'RS', nome: 'Rio Grande do Sul' },
  { sigla: 'SC', nome: 'Santa Catarina' },
  { sigla: 'SE', nome: 'Sergipe' },
  { sigla: 'SP', nome: 'São Paulo' },
  { sigla: 'TO', nome: 'Tocantins' },
]

// Coringa das matrizes que aceitam "vale para qualquer origem" (MVA).
export const UF_QUALQUER = '*'
export const UF_QUALQUER_LABEL = 'Qualquer origem (regra geral)'

const NOMES = Object.fromEntries(UFS.map(u => [u.sigla, u.nome]))

// "MG — Minas Gerais": a sigla é o que vai gravado, o nome é para o leigo.
export function rotuloUf(sigla, nome) {
  if (sigla === UF_QUALQUER) return UF_QUALQUER_LABEL
  const completo = nome || NOMES[sigla]
  return completo ? `${sigla} — ${completo}` : sigla
}

// ── Hidratação a partir do servidor ─────────────────────────────────────────
// Uma requisição por sessão, compartilhada por todos os seletores da tela
// (o cache evita 6 chamadas iguais só para abrir um modal). Qualquer falha —
// inclusive o endpoint ainda não existir no servidor — cai no fallback local.
let _cache = null
let _emVoo = null

export function carregarUfs() {
  if (_cache) return Promise.resolve(_cache)
  if (!_emVoo) {
    _emVoo = api.matrizesUfs()
      .then(lista => {
        _cache = Array.isArray(lista) && lista.length ? lista : UFS
        return _cache
      })
      .catch(() => {
        _cache = UFS
        return _cache
      })
  }
  return _emVoo
}

// Devolve a lista de UFs já pronta para uso: começa no fallback (a tela nunca
// aparece vazia) e troca pela do servidor quando ela chega.
export function useUfs() {
  const [ufs, setUfs] = useState(() => _cache || UFS)
  useEffect(() => {
    let vivo = true
    carregarUfs().then(lista => { if (vivo) setUfs(lista) })
    return () => { vivo = false }
  }, [])
  return ufs
}
