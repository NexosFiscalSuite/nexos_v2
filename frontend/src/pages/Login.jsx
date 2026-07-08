import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import solLogo from '../assets/sol-emblema.svg'

export default function Login() {
  const { login }   = useAuth()
  const navigate    = useNavigate()
  const [form, setForm]       = useState({ email:'', password:'', slug:'' })
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState('')
  const [showPw, setShowPw]   = useState(false)
  const [showSlug, setShowSlug] = useState(false)

  async function handleSubmit(e) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      await login(form.email, form.password, form.slug)
      navigate('/dashboard')
    } catch (err) {
      // Backend pede o escritório quando o e-mail existe em mais de um tenant
      if (err?.payload?.error?.code === 'tenant_required') {
        setShowSlug(true)
        setError('Informe o identificador do escritório (slug) e tente novamente.')
      } else {
        setError(err.message || 'E-mail ou senha incorretos')
      }
    } finally { setLoading(false) }
  }

  return (
    <div className="login-root">
      <div className="login-bg" aria-hidden="true">
        <span className="shape blur s1" />
        <span className="shape blur s2" />
        <span className="shape blur s3" />
        <span className="shape blur s4" />
        <span className="shape blur s5" />
        <span className="shape blur s6" />
        <span className="shape blur s7" />
        <span className="shape ring r1" />
        <span className="shape ring r2" />
        <span className="shape ring r3" />
        <span className="shape dot d1" />
        <span className="shape dot d2" />
        <span className="shape dot d3" />
        <span className="shape dot d4" />
      </div>

      <div className="login-card">
        <div className="login-logo">
          <img src={solLogo} alt="Sol Contabilidade" />
        </div>

        <div className="login-head">
          <h2>Bem-vindo de volta</h2>
          <p>Entre com as suas credenciais para acessar o sistema.</p>
        </div>

        {error && (
          <div className="login-error">
            <i className="ti ti-alert-circle" />{error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <label className="login-field">
            <span>E-mail</span>
            <div className="login-input">
              <i className="ti ti-mail" />
              <input
                type="email" value={form.email} required autoFocus
                placeholder="voce@escritorio.com" autoComplete="username"
                onChange={e => setForm(f => ({...f, email:e.target.value}))}
              />
            </div>
          </label>

          <label className="login-field">
            <span>Senha</span>
            <div className="login-input">
              <i className="ti ti-lock" />
              <input
                type={showPw ? 'text' : 'password'} value={form.password} required
                placeholder="Digite sua senha" autoComplete="current-password"
                onChange={e => setForm(f => ({...f, password:e.target.value}))}
              />
              <button type="button" className="login-eye" onClick={() => setShowPw(v => !v)} tabIndex={-1}>
                <i className={`ti ${showPw ? 'ti-eye-off' : 'ti-eye'}`} />
              </button>
            </div>
          </label>

          {showSlug && (
            <label className="login-field">
              <span>Escritório (slug)</span>
              <div className="login-input">
                <i className="ti ti-building" />
                <input
                  type="text" value={form.slug}
                  placeholder="ex.: sol-contabilidade"
                  onChange={e => setForm(f => ({...f, slug:e.target.value}))}
                />
              </div>
            </label>
          )}

          <div className="login-row">
            <a href="#" onClick={e => { e.preventDefault(); setShowSlug(s => !s) }}>
              {showSlug ? 'Ocultar escritório' : 'Tenho mais de um escritório'}
            </a>
          </div>

          <button type="submit" className="login-submit" disabled={loading}>
            {loading
              ? <><span className="login-spin" /> Entrando...</>
              : <>Entrar <i className="ti ti-arrow-right" /></>
            }
          </button>
        </form>

        <p className="login-foot">Acesso restrito</p>
      </div>
    </div>
  )
}
