import { useState, useRef, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useRefresh } from '../context/RefreshContext'
import { api } from '../api'
import CompetenciaPicker from './CompetenciaPicker'
import logoMarca from '../assets/sol-logo.svg'
import logoEmblema from '../assets/sol-emblema.svg'
import { iniciarTour } from '../tour'

const PAGE_TITLES = {
  '/dashboard':  'Dashboard',
  '/upload':     'Upload de XMLs',
  '/notas':      'Notas Fiscais',
  '/conformidade': 'Conformidade',
  '/divergencias-st': 'Divergências de ICMS-ST',
  '/ibs-cbs': 'IBS/CBS — Ano-teste 2026',
  '/relatorios': 'Relatórios',
  '/cadastros':  'Clientes e Fornecedores',
  '/matrizes-fiscais': 'Matrizes Fiscais',
  '/empresas':   'Empresas',
  '/grupos':     'Grupos',
  '/usuarios':   'Usuários',
  '/auditoria':  'Auditoria',
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
  { to:'/ibs-cbs', icon:'ti-flask', label:'IBS/CBS 2026' },
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
      <div style={base(isActive)} data-tour={'nav' + to.replace(/\//g, '-')} onClick={() => setOpen(o => !o)}>
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
    <NavLink to={to} style={({ isActive: a }) => base(a)} data-tour={'nav' + to.replace(/\//g, '-')}
      title={collapsed ? label : undefined}>
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

  // Lista completa (a caixa rola): cortar aqui já escondeu empresa de usuário.
  const filtered = empresas.filter(e =>
    !query || e.razao_social.toLowerCase().includes(query.toLowerCase()) || e.cnpj.includes(query)
  )

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
  // Preferência do usuário persiste entre sessões (estilo SOL Treinamentos).
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('sol_sidebar') === '1')
  function alternarSidebar() {
    setCollapsed(c => { localStorage.setItem('sol_sidebar', c ? '0' : '1'); return !c })
  }
  const [quebraCount, setQuebraCount] = useState(0)
  const [boasVindas, setBoasVindas] = useState(false)
  const pageTitle = PAGE_TITLES[location.pathname] || 'Sol'

  // Primeiro acesso deste usuário neste navegador? Oferece o tour guiado.
  const chaveTour = user ? `sol_tour_v1_${user.id}` : null
  useEffect(() => {
    if (chaveTour && !localStorage.getItem(chaveTour)) setBoasVindas(true)
  }, [chaveTour])

  function responderTour(fazer) {
    localStorage.setItem(chaveTour, fazer ? 'feito' : 'pulado')
    setBoasVindas(false)
    if (fazer) {
      setCollapsed(false)
      navigate('/dashboard')
      setTimeout(iniciarTour, 350)   // espera o modal fechar e a rota assentar
    }
  }

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

      {/* Sidebar — card flutuante (estilo SOL Treinamentos): cantos
          arredondados, respiro das bordas da janela, recolhível pelo
          botão-círculo do topo e usuário no rodapé. */}
      <aside style={{
        width: collapsed ? 'var(--sidebar-w-c)' : 'var(--sidebar-w)',
        flexShrink:0, background:'var(--sidebar-bg)',
        display:'flex', flexDirection:'column',
        transition:'width .22s cubic-bezier(.4,0,.2,1)',
        position:'fixed', left:12, top:12, bottom:12, overflow:'hidden', zIndex:100,
        border:'1px solid var(--hairline)', borderRadius:'var(--radius-lg)',
        boxShadow:'0 2px 14px rgba(29,29,31,0.06)',
      }}>
        {/* Logo + botão-círculo de recolher (chevron), como no Treinamentos. */}
        <div style={{
          padding: collapsed ? '12px 0 10px' : '0 10px 0 14px',
          minHeight:'var(--topbar-h)',
          display:'flex', flexDirection: collapsed ? 'column' : 'row',
          alignItems:'center', justifyContent: collapsed ? 'center' : 'space-between',
          gap:8, borderBottom:'1px solid var(--border-2)', flexShrink:0,
        }}>
          {collapsed
            ? <img src={logoEmblema} alt="Sol Contabilidade" style={{ height:32, width:'auto', maxWidth:40, objectFit:'contain', flexShrink:0 }} />
            : <img src={logoMarca} alt="Sol Contabilidade" style={{ height:42, width:'auto', maxWidth:170, objectFit:'contain', flexShrink:0, minWidth:0 }} />}
          <button onClick={alternarSidebar} title={collapsed ? 'Expandir menu' : 'Recolher menu'}
            style={{
              width:26, height:26, borderRadius:'50%', border:'1px solid var(--border)',
              background:'var(--surface)', color:'var(--text-3)', cursor:'pointer',
              display:'flex', alignItems:'center', justifyContent:'center', flexShrink:0,
            }}>
            <i className={`ti ti-chevron-${collapsed ? 'right' : 'left'}`} style={{ fontSize:14 }} />
          </button>
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

        {/* Usuário no rodapé do card (estilo Treinamentos). */}
        <div style={{
          padding:'12px 10px', borderTop:'1px solid var(--border-2)', flexShrink:0,
          display:'flex', alignItems:'center', gap:10,
          justifyContent: collapsed ? 'center' : 'flex-start',
        }}>
          <div style={{ width:34, height:34, borderRadius:'50%', background:'var(--primary-lt)', display:'flex', alignItems:'center', justifyContent:'center', fontSize:13, fontWeight:700, color:'var(--primary-text)', flexShrink:0 }}>
            {(user?.full_name || 'U')[0].toUpperCase()}
          </div>
          {!collapsed && (
            <div style={{ minWidth:0, lineHeight:1.25 }}>
              <div style={{ fontSize:12.5, fontWeight:600, color:'var(--text-1)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{user?.full_name}</div>
              <div style={{ fontSize:11, color:'var(--text-4)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{user?.email || user?.role}</div>
            </div>
          )}
        </div>
      </aside>

      {/* Main */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', marginLeft: collapsed ? 'calc(var(--sidebar-w-c) + 24px)' : 'calc(var(--sidebar-w) + 24px)', transition:'margin-left .22s cubic-bezier(.4,0,.2,1)', minWidth:0 }}>

        {/* Topbar */}
        <header style={{ height:'var(--topbar-h)', background:'var(--topbar-bg)', borderBottom:'1px solid var(--hairline)', display:'flex', alignItems:'center', padding:'0 24px', gap:12, position:'sticky', top:0, zIndex:90, boxShadow:'none' }}>
          <div style={{ fontWeight:600, fontSize:15, color:'var(--text-1)', flex:1 }}>{pageTitle}</div>

          {/* Competencia global */}
          <div data-tour="topbar-competencia"><CompetenciaPickerTopbar /></div>

          {/* Seletor de empresa global */}
          <div data-tour="topbar-empresa"><EmpresaTopbar /></div>

          {/* Ajuda: refaz o tour guiado a qualquer momento */}
          <button className="btn btn-ghost btn-sm" data-tour="topbar-ajuda" title="Refazer o tour guiado"
            onClick={() => { setCollapsed(false); iniciarTour() }} style={{ color:'var(--text-3)' }}>
            <i className="ti ti-help-circle" style={{ fontSize:17 }} />
          </button>

          {/* Divider */}
          <div style={{ width:1, height:28, background:'var(--border)', flexShrink:0 }} />

          {/* Sair (o usuário agora mora no rodapé da sidebar) */}
          <button onClick={() => { logout(); navigate('/login') }} className="btn btn-ghost btn-sm" title="Sair" style={{ color:'var(--text-3)' }}>
            <i className="ti ti-logout" style={{ fontSize:16 }} />
          </button>
        </header>

        <main style={{ flex:1, padding:'28px 32px', overflow:'auto', minWidth:0 }}>
          <Outlet />
        </main>
      </div>

      {/* Boas-vindas do primeiro acesso: oferece (não impõe) o tour guiado */}
      {boasVindas && (
        <div className="modal-overlay" style={{ zIndex: 10000 }}>
          <div className="modal" style={{ maxWidth: 440, textAlign: 'center' }}>
            <div className="modal-body" style={{ padding: '30px 28px 24px' }}>
              <img src={logoEmblema} alt="" style={{ width: 72, height: 'auto', marginBottom: 14 }} />
              <h2 style={{ margin: '0 0 8px', fontSize: 19 }}>Bem-vindo(a), {user?.full_name?.split(' ')[0]}! 👋</h2>
              <p style={{ margin: 0, fontSize: 13.5, color: 'var(--text-3)', lineHeight: 1.55 }}>
                Primeira vez por aqui? Em <b>2 minutos</b> o tour guiado te mostra onde
                cada coisa vive — apontando na tela, passo a passo. Se você já conhece
                o sistema, é só pular (dá para refazer depois no botão
                {' '}<i className="ti ti-help-circle" /> do topo).
              </p>
            </div>
            <div className="modal-footer" style={{ justifyContent: 'center', gap: 10 }}>
              <button className="btn btn-ghost" onClick={() => responderTour(false)}>Já conheço, pular</button>
              <button className="btn btn-primary" onClick={() => responderTour(true)}>
                <i className="ti ti-route" /> Fazer o tour
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
