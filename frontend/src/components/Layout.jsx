import { useState, useRef, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { useEmpresa } from '../context/EmpresaContext'
import { useCompetencia } from '../context/CompetenciaContext'
import { useRefresh } from '../context/RefreshContext'
import { api } from '../api'
import CompetenciaPicker from './CompetenciaPicker'
import logoEmblema from '../assets/sol-emblema.svg'
import logoConsole from '../assets/sol-logo-console.png'   // mesma marca do SOL Treinamentos
import { iniciarTour } from '../tour'
import { DEMO_EMPRESA, demoAtivo } from '../tourDemo'

// Ações rápidas do topo direito: círculos flutuando no canvas (padrão do
// Console do SOL Treinamentos — a topbar branca saiu; cada página tem título).
const TOP_ICON = {
  width: 36, height: 36, borderRadius: '50%', padding: 0,
  border: '1px solid var(--border)', background: 'var(--surface)',
  color: 'var(--text-3)', cursor: 'pointer',
  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
  boxShadow: '0 1px 2px rgba(0,10,40,0.06)',
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
            {/* Empresa Exemplo do tour: só aparece com o modo demonstração
                ativo — dados fictícios, nada é salvo. */}
            {demoAtivo() && (
              <div
                data-tour="empresa-demo"
                onClick={() => { setSelectedEmpresa(DEMO_EMPRESA); setOpen(false) }}
                style={{ padding:'10px 14px', cursor:'pointer', fontSize:13, fontWeight:600, background:'var(--primary-lt)', color:'var(--primary-text)', borderBottom:'1px solid var(--border-2)' }}
              >
                ☀️ Empresa Exemplo (tour) — dados fictícios
              </div>
            )}
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
  const { selectedEmpresa, setSelectedEmpresa } = useEmpresa()
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

  // Tour em modo demonstração: guarda a empresa atual e devolve no fim —
  // durante o tour a pessoa trabalha na Empresa Exemplo (dados fictícios).
  function abrirTour() {
    setCollapsed(false)
    const antes = selectedEmpresa && selectedEmpresa.id !== DEMO_EMPRESA.id
      ? selectedEmpresa : null
    iniciarTour({ aoEncerrar: () => setSelectedEmpresa(antes) })
  }

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
      setTimeout(abrirTour, 350)   // espera o modal fechar e a rota assentar
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
        position:'sticky', top:12, height:'calc(100vh - 24px)', margin:'12px 0 12px 12px',
        zIndex:100, border:'1px solid var(--hairline)', borderRadius:'var(--radius-lg)',
        boxShadow:'0 2px 14px rgba(29,29,31,0.06)',
      }}>
        {/* Marca compacta (emblema + nome/subtítulo), padrão do Console. */}
        <div style={{ padding: collapsed ? '16px 0 12px' : '16px 14px 12px', borderBottom:'1px solid var(--border-2)', flexShrink:0 }}>
          <NavLink to="/dashboard" title="Sol Contabilidade — Nexos Fiscal" style={{
            display:'flex', alignItems:'center', gap:11, minWidth:0,
            justifyContent: collapsed ? 'center' : 'flex-start', textDecoration:'none',
          }}>
            <img src={logoConsole} alt="Sol" style={{ width:34, height:34, objectFit:'contain', flexShrink:0 }} />
            {!collapsed && (
              <span style={{ display:'flex', flexDirection:'column', minWidth:0, lineHeight:1.2 }}>
                <strong style={{ fontSize:14.5, color:'var(--text-1)', whiteSpace:'nowrap', overflow:'hidden', textOverflow:'ellipsis' }}>Sol Contabilidade</strong>
                <small style={{ fontSize:11.5, color:'var(--text-4)' }}>Nexos Fiscal</small>
              </span>
            )}
          </NavLink>
        </div>

        {/* Botão de recolher — redondo, flutuando na borda direita do card. */}
        <button onClick={alternarSidebar} title={collapsed ? 'Expandir menu' : 'Recolher menu'}
          style={{
            position:'absolute', top:24, right:-13, zIndex:5,
            width:26, height:26, borderRadius:'50%', border:'1px solid var(--border)',
            background:'var(--surface)', color:'var(--text-3)', cursor:'pointer',
            display:'flex', alignItems:'center', justifyContent:'center',
            boxShadow:'0 1px 3px rgba(0,0,0,0.08)',
          }}>
          <i className={`ti ti-chevron-${collapsed ? 'right' : 'left'}`} style={{ fontSize:14 }} />
        </button>

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

      {/* Main — sem topbar branca: controles flutuam no canto superior
          direito, direto no canvas (padrão do Console do Treinamentos). */}
      <div style={{ flex:1, display:'flex', flexDirection:'column', minWidth:0 }}>

        <div style={{ display:'flex', justifyContent:'flex-end', alignItems:'center', gap:10, padding:'14px 24px 0', minHeight:12, flexWrap:'wrap' }}>
          {/* Competencia global */}
          <div data-tour="topbar-competencia"><CompetenciaPickerTopbar /></div>

          {/* Seletor de empresa global */}
          <div data-tour="topbar-empresa"><EmpresaTopbar /></div>

          {/* Ajuda: refaz o tour guiado a qualquer momento */}
          <button style={TOP_ICON} data-tour="topbar-ajuda" title="Refazer o tour guiado (empresa de exemplo, nada é salvo)"
            onClick={abrirTour}>
            <i className="ti ti-help-circle" style={{ fontSize:17 }} />
          </button>

          {/* Sair (o usuário mora no rodapé da sidebar) */}
          <button onClick={() => { logout(); navigate('/login') }} style={TOP_ICON} title="Sair">
            <i className="ti ti-logout" style={{ fontSize:16 }} />
          </button>
        </div>

        <main style={{ flex:1, padding:'14px 32px 28px', minWidth:0 }}>
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
