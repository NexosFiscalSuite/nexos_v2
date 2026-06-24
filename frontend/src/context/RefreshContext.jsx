import { createContext, useContext, useState, useCallback } from 'react'

/**
 * Sinal global de "os dados mudaram" (ex.: após importar XMLs).
 * Telas que listam notas/quebras observam `dataVersion` e recarregam quando ele muda.
 * Quem altera dados (Upload, cancelamento, etc.) chama `bumpData()`.
 */
const RefreshCtx = createContext(null)

export function RefreshProvider({ children }) {
  const [dataVersion, setDataVersion] = useState(0)
  const bumpData = useCallback(() => setDataVersion(v => v + 1), [])
  return (
    <RefreshCtx.Provider value={{ dataVersion, bumpData }}>
      {children}
    </RefreshCtx.Provider>
  )
}

export const useRefresh = () => useContext(RefreshCtx)
