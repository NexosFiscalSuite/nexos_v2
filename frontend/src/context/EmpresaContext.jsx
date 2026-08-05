import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { api } from '../api'
import { DEMO_EMPRESA } from '../tourDemo'
import { useAuth } from './AuthContext'

const EmpresaCtx = createContext(null)
const STORAGE_KEY = 'nexos_selected_empresa'

export function EmpresaProvider({ children }) {
  const { user } = useAuth()
  const [empresas, setEmpresas] = useState([])
  const [selectedEmpresa, setSelectedEmpresaState] = useState(() => {
    try {
      const emp = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null')
      // A Empresa Exemplo (tour) nunca sobrevive a um recarregamento: sem o
      // modo demonstração ativo, as chamadas dela iriam ao servidor de verdade.
      return emp && emp.id !== DEMO_EMPRESA.id ? emp : null
    } catch { return null }
  })
  const [loading, setLoading] = useState(false)

  // Persiste a empresa selecionada apenas na sessao
  const setSelectedEmpresa = useCallback((emp) => {
    setSelectedEmpresaState(emp)
    try {
      if (emp) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(emp))
      else sessionStorage.removeItem(STORAGE_KEY)
    } catch {}
  }, [])

  const loadEmpresas = useCallback(async () => {
    if (!user) return
    setLoading(true)
    try {
      const list = await api.empresas()
      setEmpresas(list || [])
    } catch {
      setEmpresas([])
    } finally {
      setLoading(false)
    }
  }, [user])

  useEffect(() => { loadEmpresas() }, [loadEmpresas])

  // Limpa empresa selecionada ao fazer logout (corrige vazamento entre usuarios)
  useEffect(() => {
    if (!user) {
      setSelectedEmpresaState(null)
      try { sessionStorage.removeItem(STORAGE_KEY) } catch {}
      setEmpresas([])
    }
  }, [user])

  // Se a empresa selecionada nao esta mais na lista do usuario logado, limpa
  // (a Empresa Exemplo do tour nao esta na lista de proposito — nao limpar).
  useEffect(() => {
    if (!selectedEmpresa || !empresas.length) return
    if (selectedEmpresa.id === DEMO_EMPRESA.id) return
    const ainda_tem = empresas.some(e => e.id === selectedEmpresa.id)
    if (!ainda_tem) setSelectedEmpresa(null)
  }, [empresas, selectedEmpresa, setSelectedEmpresa])

  return (
    <EmpresaCtx.Provider value={{
      empresas, selectedEmpresa, setSelectedEmpresa,
      loading, reload: loadEmpresas
    }}>
      {children}
    </EmpresaCtx.Provider>
  )
}

export const useEmpresa = () => useContext(EmpresaCtx)
