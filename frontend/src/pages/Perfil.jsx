import { useAuth } from '../context/AuthContext'

const ROLE_LABEL = { admin: 'Administrador', supervisor: 'Supervisor', user: 'Usuário' }

export default function Perfil() {
  const { user } = useAuth()
  if (!user) return null

  return (
    <div>
      <div className="page-header"><h1 className="page-title">Meu Perfil</h1></div>

      <div className="card" style={{ maxWidth: 520 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 20 }}>
          <div style={{ width: 56, height: 56, borderRadius: '50%', background: 'var(--primary-lt)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 22, fontWeight: 700, color: 'var(--primary-text)' }}>
            {(user.full_name || 'U')[0].toUpperCase()}
          </div>
          <div>
            <div style={{ fontWeight: 600, fontSize: 16 }}>{user.full_name}</div>
            <span className="badge badge-primary" style={{ marginTop: 4 }}>{ROLE_LABEL[user.role] || user.role}</span>
          </div>
        </div>

        <div className="field">
          <label>Nome completo</label>
          <div className="input-wrap"><input value={user.full_name || ''} readOnly /></div>
        </div>
        <div className="field">
          <label>E-mail</label>
          <div className="input-wrap"><input value={user.email || ''} readOnly /></div>
        </div>

        <p style={{ fontSize: 12, color: 'var(--text-4)', marginTop: 8 }}>
          <i className="ti ti-info-circle" /> A edição de perfil entra quando o endpoint correspondente for adicionado ao backend V2.
        </p>
      </div>
    </div>
  )
}
