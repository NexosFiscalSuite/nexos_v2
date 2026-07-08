import { useState, useRef, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useRefresh } from '../context/RefreshContext'
import { api } from '../api'
import CompetenciaPicker from './CompetenciaPicker'
import logoMarca from '../assets/sol-logo.svg'

const PAGE_TITLES = {
  '/dashboard':  'Dashboard',
  '/upload':     'Upload de XMLs',
  '/notas':      'Notas Fiscais',
  '/conformidade': 'Conformidade',
  '/divergencias-st': 'Divergências de ICMS-ST',
  '/relatorios': 'Relatórios',
  '/cadastros':  'Clientes e Fornecedores',
  '/matrizes-fiscais': 'Matrizes Fiscais',
  '/empresas':   'Empresas',
  '/grupos':     'Grupos',
  '/usuarios':   'Usuários',
  '/auditoria':  'Auditoria',
  '/perfil':     'Meu Perfil',
}

const NAV = [
  { to:'/dashboard', icon:'ti-layout-dashboard', label:'Dashboard' },
  { to:'/upload',    icon:'ti-cloud-upload',      label:'Upload' },
  { to:'/documentos', icon:'ti-folders', label:'Documentos Fiscais', subItems: [
    { to:'/notas',       icon:'ti-file-invoice',    label:'Notas' },
    { to:'/relatorios',  icon:'ti-report',          label:'Relatórios' },
    { to:'/cfop-regras', icon:'ti-arrows-exchange', label:'De/Para CFOP' },
  ] },
  { to:'/conformidade', icon:'ti-shield-check',   label:'Conformidade' },
  { to:'/divergencias-st', icon:'ti-alert-triangle', label:'Divergências ST' },
  { to:'/cadastros-grp', icon:'ti-address-book', label:'Cadastros', subItems: [
    { to:'/cadastros',        icon:'ti-users',         label:'Clientes e Fornecedores' },
    { to:'/matrizes-fiscais', icon:'ti-table-options', label:'Matrizes Fiscais' },
  ] },
]
const ADMIN_NAV = [
  { to:'/empresas', icon:'ti-building-store', label:'Empresas' },
  { to:'/acessos', icon:'ti-shield-lock', label:'Acessos', subItems: [
    { to:'/grupos',    icon:'ti-users-group', label:'Grupos' },
    { to:'/usuarios',  icon:'ti-user-shield', label:'Usuários' },
    { to:'/auditoria', icon:'ti-history',     label:'Auditoria' },
  ] },
]

function NavItem({ to, icon, label, collapsed, subItems, badge }) {
  const location = useLocation()
  const matches = (p) => location.pathname === p || location.pathname.startsWith(p + '/')
  // No accordion, o pai fica ativo (e aberto) quando um dos filhos é a rota atual.
  const isActive = subItems?.length ? subItems.some(s => matches(s.to)) : matches(to)
  const [open, setOpen] = useState(isActive)

  // Ponto de notificação (ex.: quebras de sequência pendentes) — sobre o ícone
  const Dot = () => {
    if (!badge) return null
    return (
      <span style={{
        position:'absolute',
        top: collapsed ? 6 : 7,
        left: collapsed ? '50%' : 25,
        marginLeft: collapsed ? 6 : 0,
        width:8, height:8, borderRadius:'50%',
        background:'var(--err-text, #DC2626)',
        boxShadow:'0 0 0 2px var(--surface)',
        pointerEvents:'none',
      }} />
    )
  }

  const base = (a) => ({
    display:'flex', alignItems:'center', gap:10,
    padding: collapsed ? '10px' : '9px 10px',
    borderRadius:'var(--radius)', fontWeight: a ? 600 : 400, fontSize:13,
    color: a ? 'var(--primary-text)' : 'var(--ink)',
    background: a ? 'var(--primary-lt)' : 'transparent',
    borderLeft: a ? '2.5px solid var(--primary)' : '2.5px solid transparent',
    transition:'all .12s', justifyContent: collapsed ? 'center' : 'flex-start',
    textDecoration:'none', cursor:'pointer', marginBottom:2, userSelect:'none',
    position:'relative',
  })

  if (subItems?.length) return (
    <div>
      <div style={base(isActive)} onClick={() => setOpen(o => !o)}>
        <i className={`ti ${icon}`} style={{ fontSize:18, flexShrink:0 }} />
        {!collapsed && (
          <>
            <span style={{ flex:1, whiteSpace:'nowrap' }}>{label}</span>
            <i className={`ti ti-chevron-${open ? 'up' : 'down'}`} style={{ fontSize:13, opacity:.5 }} />
          </>
        )}
      </div>
      {!collapsed && open && (
        <div style={{ marginLeft:16, marginBottom:4 }}>
          {subItems.map(sub => (
            <NavLink key={sub.to} to={sub.to} style={({ isActive: a }) => ({
              display:'flex', alignItems:'center', gap:8,
              padding:'7px 10px 7px 14px', borderRadius:'var(--radius)',
              fontSize:12, fontWeight: a ? 600 : 400,
              color: a ? 'var(--primary-text)' : 'var(--text-2)',
              background: a ? 'var(--primary-lt)' : 'transparent',
              borderLeft: a ? '2px solid var(--primary)' : '2px solid var(--border-2)',
              textDecoration:'none', transition:'all .12s', marginBottom:2,
            })}>
              <i className={`ti ${sub.icon}`} style={{ fontSize:14 }} />
              {sub.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  )

  return (
    <NavLink to={to} style={({ isActive: a }) => base(a)}>
      <i className={`ti ${icon}`} style={{ fontSize:18, flexShrink:0 }} />
      {!collapsed && <span style={{ whiteSpace:'nowrap' }}>{label}</span>}
      <Dot />
    </NavLink>
  )
}

// Seletor de empresa no topbar
function EmpresaTopbar() {
  const { empresas, selectedEmpresa, setSelectedEmpresa } = useEmpresa()
  const [open, setOpen]   = useState(false)
  const [query, setQuery] = useState('')
  const ref = useRef()

  useEffect(() => {
    function h(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', h)
    return () => document.removeEventListener('mousedown', h)
  }, [])

  const filtered = empresas.filter(e =>
    !query || e.razao_social.toLowerCase().includes(query.toLowerCase()) || e.cnpj.includes(query)
  ).slice(0, 6)

  return (
    <div ref={ref} style={{ position:'relative' }}>
      <button
        onClick={() => { setOpen(o => !o); setQuery('') }}
        style={{
          display:'flex', alignItems:'center', gap:8,
          padding:'6px 12px', borderRadius:8, border:'1.5px solid var(--border)',
          background: selectedEmpresa ? 'var(--primary-lt)' : 'var(--surface)',
          color: selectedEmpresa ? 'var(--primary-text)' : 'var(--text-3)',
          cursor:'pointer', fontSize:13, fontWeight: selectedEmpresa ? 600 : 400,
          transition:'all .15s', maxWidth:220,
        }}
      >
        <i className="ti ti-building-store" style={{ fontSize:15, flexShrink:0 }} />
        <span style={{ overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
          {selectedEmpresa ? selectedEmpresa.razao_social : 'Empresa'}
        </span>
        {selectedEmpresa && (
          <span
            onClick={e => { e.stopPropagation(); setSelectedEmpresa(null) }}
            style={{ marginLeft:2, color:'var(--text-4)', fontSize:12, lineHeight:1, cursor:'pointer' }}
          >
            <i className="ti ti-x" />
          </span>
        )}
        {!selectedEmpresa && <i className="ti ti-chevron-down" style={{ fontSize:12, flexShrink:0 }} />}
      </button>

      {open && (
        <div style={{
          position:'absolute', top:'calc(100% + 6px)', right:0, zIndex:500,
          background:'var(--surface)', border:'1px solid var(--border)',
          borderRadius:12, boxShadow:'0 8px 32px rgba(0,0,0,0.12)',
          width:280, overflow:'hidden',
        }}>
          <div style={{ padding:'10px 12px', borderBottom:'1px solid var(--border-2)' }}>
            <div style={{ position:'relative' }}>
              <i className="ti ti-search" style={{ position:'absolute', left:10, top:'50%', transform:'translateY(-50%)', color:'var(--text-4)', fontSize:14 }} />
              <input
                value={query}
                onChange={e => setQuery(e.target.value)}
                placeholder="Buscar empresa..."
                autoFocus
                style={{ width:'100%', paddingLeft:32, paddingRight:12, paddingTop:7, paddingBottom:7, fontSize:13, border:'1.5px solid var(--border)', borderRadius:8, outline:'none', fontFamily:'var(--font)' }}
                onFocus={e => e.target.style.borderColor='var(--primary)'}
                onBlur={e  => e.target.style.borderColor='var(--border)'}
              />
            </div>
          </div>

          <div style={{ maxHeight:240, overflowY:'auto' }}>
            {/* Opção nenhuma empresa */}
            <div
              onClick={() => { setSelectedEmpresa(null); setOpen(false) }}
              style={{ padding:'10px 14px', cursor:'pointer', fontSize:13, color:'var(--text-3)', borderBottom:'1px solid var(--border-2)' }}
              onMouseEnter={e => e.currentTarget.style.background='var(--surface-2)'}
              onMouseLeave={e => e.currentTarget.style.background='transparent'}
            >
              — Sem empresa selecionada —
            </div>

            {filtered.length === 0 ? (
              <div style={{ padding:'20px', textAlign:'center', color:'var(--text-4)', fontSize:13 }}>
                <i className="ti ti-search-off" style={{ fontSize:20, display:'block', marginBottom:6 }} />
                Nenhuma empresa encontrada
              </div>
            ) : filtered.map(e => (
              <div
                key={e.id}
                onClick={() => { setSelectedEmpresa(e); setOpen(false) }}
                style={{
                  display:'flex', alignItems:'center', gap:10,
                  padding:'10px 14px', cursor:'pointer', transition:'background .1s',
                  background: selectedEmpresa?.id === e.id ? 'var(--primary-lt)' : 'transparent',
                  borderBottom:'1px solid var(--border-2)',
                }}
                onMouseEnter={ev => { if (selectedEmpresa?.id !== e.id) ev.currentTarget.style.background='var(--surface-2)' }}
                onMouseLeave={ev => { if (selectedEmpresa?.id !== e.id) ev.currentTarget.style.background='transparent' }}
              >
                <div style={{ width:28, height:28, borderRadius:7, background:'var(--primary-lt)', display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0 }}>
                  <i className="ti ti-building-store" style={{ fontSize:14, color:'var(--primary-text)' }} />
                </div>
                <div style={{ minWidth:0 }}>
                  <div style={{ fontSize:13, fontWeight:500, color:'var(--text-1)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{e.razao_social}</div>
                  <div style={{ fontSize:11, color:'var(--text-4)' }}>{e.cnpj}</div>
                </div>
                {selectedEmpresa?.id === e.id && <i className="ti ti-check" style={{ color:'var(--primary-text)', marginLeft:'auto', fontSize:16 }} />}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// Wrapper que liga a competencia global ao picker
function CompetenciaPickerTopbar() {
  const { competencia, setCompetencia } = useCompetencia()
  return <CompetenciaPicker value={competencia} onChange={setCompetencia} />
}

export default function Layout() {
  const { user, logout } = useAuth()
  const { selectedEmpresa } = useEmpresa()
  const { ano, mes } = useCompetencia()
  const { dataVersion } = useRefresh()
  const navigate  = useNavigate()
  const location  = useLocation()
  const [collapsed, setCollapsed] = useState(false)
  const [quebraCount, setQuebraCount] = useState(0)
  const pageTitle = PAGE_TITLES[location.pathname] || 'Sol'

  // Conta as quebras de sequência da empresa + competência selecionada (badge).
  // Reavalia ao trocar empresa/competência, ao navegar e após importações (dataVersion).
  useEffect(() => {
    let vivo = true
    if (!selectedEmpresa) { setQuebraCount(0); return }
    api.quebras(selectedEmpresa.id, ano, mes)
      .then(r => { if (vivo) setQuebraCount((r.quebras || []).length) })
      .catch(() => { if (vivo) setQuebraCount(0) })
    return () => { vivo = false }
  }, [selectedEmpresa, ano, mes, location.pathname, dataVersion])

  return (
    <div style={{ display:'flex', minHeight:'100vh', background:'var(--bg)' }}>

      {/* Sidebar */}
      <aside style={{
        width: collapsed ? 'var(--sidebar-w-c)' : 'var(--sidebar-w)',
        flexShrink:0, background:'var(--sidebar-bg)',
        display:'flex', flexDirection:'column',
        transition:'width .22s cubic-bezier(.4,0,.2,1)',
        position:'fixed', left:0, top:0, bottom:0, overflow:'hidden', zIndex:100, borderRight:'1px solid var(--hairline)',
      }}>
        {/* Logo (SVG vetorial): mesma altura da topbar — a linha divisória
            continua a linha do "Dashboard". */}
        <div style={{ padding: collapsed ? 0 : '0 14px', height:'var(--topbar-h)', display:'flex', alignItems:'center', justifyContent: collapsed ? 'center' : 'flex-start', borderBottom:'1px solid var(--border-2)', flexShrink:0 }}>
          {collapsed
            ? <img src={logoMarca} alt="Sol Contabilidade" style={{ height:38, width:'auto', maxWidth:46, objectFit:'contain', flexShrink:0 }} />
            : <img src={logoMarca} alt="Sol Contabilidade" style={{ height:42, width:'auto', maxWidth:195, objectFit:'contain', flexShrink:0 }} />}
        </div>

        <nav style={{ flex:1, padding:'12px 8px', overflowY:'auto', overflowX:'hidden' }}>
          {NAV.map(item => (
            <NavItem key={item.to} {...item} collapsed={collapsed}
              badge={item.to === '/conformidade' ? quebraCount : 0} />
          ))}
          {user?.role === 'admin' && (
            <>
              <div style={{ height:1, background:'var(--border-2)', margin:'12px 8px' }} />
              {ADMIN_NAV.map(item => <NavItem key={item.to} {...item} collapsed={collapsed} />)}
            </>
          )}
        </nav>

        <div style={{ padding:'10px 8px', borderTop:'1px solid var(--border-2)', flexShrink:0 }}>
          <button onClick={() => setCollapsed(c => !c)} style={{ width:'100%', display:'flex', alignItems:'center', justifyContent: collapsed ? 'center' : 'flex-end', gap:8, padding:'8px 10px', borderRadius:'var(--radius)', border:'none', background:'transparent', color:'var(--text-4)', cursor:'pointer', fontSize:13 }}>
            {!collapsed && <span style={{ fontSize:12 }}>Recolher</span>}
            <i className={`ti ti-chevron-${collapsed ? 'right' : 'left'}`} style={{ fontSize:16 }} />
          </button>
        </div>
      </aside>

      {/* Main */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', marginLeft: collapsed ? 'var(--sidebar-w-c)' : 'var(--sidebar-w)', transition:'margin-left .22s cubic-bezier(.4,0,.2,1)', minWidth:0 }}>

        {/* Topbar */}
        <header style={{ height:'var(--topbar-h)', background:'var(--topbar-bg)', borderBottom:'1px solid var(--hairline)', display:'flex', alignItems:'center', padding:'0 24px', gap:12, position:'sticky', top:0, zIndex:90, boxShadow:'none' }}>
          <div style={{ fontWeight:600, fontSize:15, color:'var(--text-1)', flex:1 }}>{pageTitle}</div>

          {/* Competencia global */}
          <CompetenciaPickerTopbar />

          {/* Seletor de empresa global */}
          <EmpresaTopbar />

          {/* Divider */}
          <div style={{ width:1, height:28, background:'var(--border)', flexShrink:0 }} />

          {/* Avatar + Sair */}
          <div onClick={() => navigate('/perfil')} style={{ display:'flex', alignItems:'center', gap:8, cursor:'pointer', padding:'4px 8px', borderRadius:8, transition:'background .12s' }}
            onMouseEnter={e => e.currentTarget.style.background='var(--surface-2)'}
            onMouseLeave={e => e.currentTarget.style.background='transparent'}>
            <div style={{ width:30, height:30, borderRadius:'50%', background:'var(--primary-lt)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:12, fontWeight:700, color:'var(--primary-text)' }}>
              {(user?.full_name || 'U')[0].toUpperCase()}
            </div>
            <div style={{ lineHeight:1.2 }}>
              <div style={{ fontSize:12, fontWeight:600, color:'var(--text-1)', maxWidth:100, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{user?.full_name?.split(' ')[0]}</div>
              <div style={{ fontSize:10, color:'var(--text-4)', textTransform:'capitalize' }}>{user?.role}</div>
            </div>
          </div>
          <button onClick={() => { logout(); navigate('/login') }} className="btn btn-ghost btn-sm" style={{ color:'var(--text-3)' }}>
            <i className="ti ti-logout" style={{ fontSize:16 }} />
          </button>
        </header>

        <main style={{ flex:1, padding:'28px 32px', overflow:'auto', minWidth:0 }}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
