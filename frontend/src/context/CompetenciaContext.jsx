import { createContext, useContext, useState, useCallback } from 'react'

const CompetenciaCtx = createContext(null)
const STORAGE_KEY = 'nexos_competencia'

// Competencia global no formato 'YYYY-MM'. Default = mes atual.
function mesAtual() {
  const d = new Date()
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
}

export function CompetenciaProvider({ children }) {
  const [competencia, setCompetenciaState] = useState(() => {
    try { return sessionStorage.getItem(STORAGE_KEY) || mesAtual() } catch { return mesAtual() }
  })

  const setCompetencia = useCallback((c) => {
    const val = c || mesAtual()
    setCompetenciaState(val)
    try { sessionStorage.setItem(STORAGE_KEY, val) } catch {}
  }, [])

  // helpers derivados
  const [ano, mes] = (competencia || mesAtual()).split('-')

  return (
    <CompetenciaCtx.Provider value={{ competencia, setCompetencia, ano, mes }}>
      {children}
    </CompetenciaCtx.Provider>
  )
}

export const useCompetencia = () => useContext(CompetenciaCtx)
