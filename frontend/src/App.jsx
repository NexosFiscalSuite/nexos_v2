import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { AuthProvider, useAuth } from './context/AuthContext'
import { EmpresaProvider } from './context/EmpresaContext'
import { CompetenciaProvider } from './context/CompetenciaContext'
import { RefreshProvider } from './context/RefreshContext'
import Layout from './components/Layout'
import Login from './pages/Login'
import Dashboard from './pages/Dashboard'
import Upload from './pages/Upload'
import Notas from './pages/Notas'
import Cadastros from './pages/Cadastros'
import Empresas from './pages/Empresas'
import Grupos from './pages/Grupos'
import Auditoria from './pages/Auditoria'
import EmpresaDashboard from './pages/EmpresaDashboard'
import Usuarios from './pages/Usuarios'
import Conformidade from './pages/Conformidade'
import Relatorios from './pages/Relatorios'
import DivergenciasST from './pages/DivergenciasST'
import VerificacaoIbsCbs from './pages/VerificacaoIbsCbs'
import CfopRegras from './pages/CfopRegras'
import MatrizesFiscais from './pages/MatrizesFiscais'
import ExcecaoItem from './pages/ExcecaoItem'

function PrivateRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center-loader"><div className="spinner" /></div>
  return user ? children : <Navigate to="/login" replace />
}

function PublicRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center-loader"><div className="spinner" /></div>
  return user ? <Navigate to="/dashboard" replace /> : children
}

function AdminRoute({ children }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center-loader"><div className="spinner" /></div>
  if (!user) return <Navigate to="/login" replace />
  return user.role === 'admin' ? children : <Navigate to="/dashboard" replace />
}

export default function App() {
  return (
    <AuthProvider>
      <EmpresaProvider>
        <CompetenciaProvider>
          <RefreshProvider>
          <BrowserRouter>
            <Routes>
              <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
              <Route element={<PrivateRoute><Layout /></PrivateRoute>}>
                <Route path="/" element={<Navigate to="/dashboard" replace />} />
                <Route path="/dashboard"     element={<Dashboard />} />
                <Route path="/upload"        element={<Upload />} />
                <Route path="/notas"         element={<Notas />} />
                <Route path="/cadastros"     element={<Cadastros />} />
                <Route path="/matrizes-fiscais" element={<MatrizesFiscais />} />
                <Route path="/excecao-item" element={<ExcecaoItem />} />
                <Route path="/conformidade"  element={<Conformidade />} />
                <Route path="/divergencias-st" element={<DivergenciasST />} />
                <Route path="/ibs-cbs"       element={<VerificacaoIbsCbs />} />
                <Route path="/relatorios"    element={<Relatorios />} />
                <Route path="/cfop-regras"   element={<CfopRegras />} />
                <Route path="/empresas"      element={<AdminRoute><Empresas /></AdminRoute>} />
                <Route path="/empresas/:id"  element={<AdminRoute><EmpresaDashboard /></AdminRoute>} />
                <Route path="/usuarios"      element={<AdminRoute><Usuarios /></AdminRoute>} />
                <Route path="/grupos"        element={<AdminRoute><Grupos /></AdminRoute>} />
                <Route path="/auditoria"     element={<AdminRoute><Auditoria /></AdminRoute>} />
              </Route>
            </Routes>
          </BrowserRouter>
          </RefreshProvider>
        </CompetenciaProvider>
      </EmpresaProvider>
    </AuthProvider>
  )
}
