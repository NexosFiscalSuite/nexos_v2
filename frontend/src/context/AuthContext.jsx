import { createContext, useContext, useState, useEffect } from 'react'
import { api, setTokens, clearTokens, getUser, setUser, getAccess } from '../api'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUserState] = useState(getUser)
  const [loading, setLoading] = useState(!!getAccess())

  useEffect(() => {
    if (getAccess() && !user) {
      api.me()
        .then(u => { setUserState(u); setUser(u) })
        .catch(() => clearTokens())
        .finally(() => setLoading(false))
    } else {
      setLoading(false)
    }
    // Roda UMA vez no mount por design (hidratação da sessão): reagir a `user`
    // aqui recriaria o loop login→me→setUser.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  async function login(email, password, tenantSlug) {
    const tokens = await api.login(email, password, tenantSlug)
    setTokens(tokens)
    const u = await api.me()
    setUser(u)
    setUserState(u)
    return u
  }

  function logout() {
    clearTokens()
    setUserState(null)
  }

  return <AuthCtx.Provider value={{ user, login, logout, loading }}>{children}</AuthCtx.Provider>
}

export const useAuth = () => useContext(AuthCtx)
