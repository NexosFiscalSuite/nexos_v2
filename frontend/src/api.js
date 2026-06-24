// Cliente da API Nexos V2. JWT access + refresh (rotação), tenant via token.
const BASE = '/api/v1'
const TIMEOUT_MS = 120_000

// ── Tokens / usuário em cache ────────────────────────────────────────────────
export const getAccess = () => localStorage.getItem('nexos_access')
export const getRefresh = () => localStorage.getItem('nexos_refresh')
export function setTokens({ access_token, refresh_token }) {
  if (access_token) localStorage.setItem('nexos_access', access_token)
  if (refresh_token) localStorage.setItem('nexos_refresh', refresh_token)
}
export function clearTokens() {
  localStorage.removeItem('nexos_access')
  localStorage.removeItem('nexos_refresh')
  localStorage.removeItem('nexos_user')
}
export const getUser = () => { try { return JSON.parse(localStorage.getItem('nexos_user') || 'null') } catch { return null } }
export const setUser = (u) => localStorage.setItem('nexos_user', JSON.stringify(u))

// ── Refresh (rotação) ────────────────────────────────────────────────────────
let _refreshing = null
async function refreshAccess() {
  const refresh_token = getRefresh()
  if (!refresh_token) return false
  if (_refreshing) return _refreshing
  _refreshing = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token }),
      })
      if (!res.ok) return false
      setTokens(await res.json())
      return true
    } catch { return false } finally { _refreshing = null }
  })()
  return _refreshing
}

function fail() {
  clearTokens()
  if (!location.pathname.startsWith('/login')) location.href = '/login'
}

async function request(method, path, body = null, isForm = false, _retried = false) {
  const headers = {}
  const token = getAccess()
  if (token) headers['Authorization'] = `Bearer ${token}`
  if (body && !isForm) headers['Content-Type'] = 'application/json'

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)
  let res
  try {
    res = await fetch(BASE + path, {
      method, headers,
      body: isForm ? body : (body ? JSON.stringify(body) : undefined),
      signal: controller.signal,
    })
  } catch (err) {
    clearTimeout(timer)
    if (err.name === 'AbortError') throw new Error('Tempo esgotado. Tente novamente.')
    throw new Error('Falha de conexão com o servidor')
  }
  clearTimeout(timer)

  // Rotas públicas de auth: um 401/400 é resposta de negócio (credenciais
  // inválidas, escritório necessário…) e NÃO deve virar "sessão expirada".
  const AUTH_PUBLIC = ['/auth/login', '/auth/register', '/auth/refresh']

  if (res.status === 401 && !AUTH_PUBLIC.includes(path)) {
    if (!_retried && getRefresh() && await refreshAccess()) {
      return request(method, path, body, isForm, true)
    }
    fail()
    throw new Error('Sessão expirada')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    // V2 usa { error: { code, message } }; validação FastAPI usa { detail }
    let msg = err?.error?.message
    if (!msg && typeof err?.detail === 'string') msg = err.detail
    if (!msg && Array.isArray(err?.detail)) msg = err.detail.map(d => d.msg).join('; ')
    if (!msg) msg = `Erro ${res.status}`
    const e = new Error(msg)
    e.status = res.status
    e.payload = err
    throw e
  }
  if (res.status === 204) return null
  return res.json()
}

const form = (method, path, fd) => request(method, path, fd, true)

// fetch com Authorization + retry único de 401 (rotação de token). Reusa a
// mesma lógica de sessão do `request`, mas devolve a Response crua p/ blobs.
async function authFetch(path, { method = 'GET', body = null, json = false } = {}) {
  const opts = { method, body: json ? JSON.stringify(body) : body }
  const withAuth = () => {
    const headers = json ? { 'Content-Type': 'application/json' } : {}
    const token = getAccess()
    if (token) headers.Authorization = `Bearer ${token}`
    return { ...opts, headers }
  }
  let res = await fetch(BASE + path, withAuth())
  if (res.status === 401 && await refreshAccess()) res = await fetch(BASE + path, withAuth())
  if (res.status === 401) { fail(); throw new Error('Sessão expirada') }
  return res
}

// Baixa um arquivo (XLSX/ZIP/PDF). GET por padrão; passe body p/ POST JSON
// (ex.: zip de XML/DANFE em lote). `fallback` nomeia o arquivo se faltar header.
async function downloadBlob(path, { body = null, fallback = 'arquivo.xlsx' } = {}) {
  const res = await authFetch(path, { method: body ? 'POST' : 'GET', body, json: body != null })
  if (!res.ok) {
    const err = await res.json().catch(() => ({}))
    throw new Error(err?.error?.message || 'Erro no download')
  }
  const blob = await res.blob()
  const cd = res.headers.get('Content-Disposition') || ''
  const m = cd.match(/filename="?([^"]+)"?/)
  return { blob, filename: m ? m[1] : fallback }
}

const NAO_IMPL = (nome) => () => {
  throw new Error(`"${nome}" estará disponível numa próxima fase do backend.`)
}

export const api = {
  // ── Auth ──
  login: (email, password, tenant_slug) =>
    request('POST', '/auth/login', { email, password, tenant_slug: tenant_slug || null }),
  me: () => request('GET', '/auth/me'),
  listUsers: () => request('GET', '/users'),
  createUser: (data) => request('POST', '/users', data),

  // ── Empresas ──
  empresas: () => request('GET', '/empresas'),
  empresa: (id) => request('GET', `/empresas/${id}`),
  criarEmpresa: (data) => request('POST', '/empresas', data),

  // ── Upload assíncrono + Jobs ──
  upload: (empresaId, formData) => form('POST', `/fiscal/empresas/${empresaId}/upload`, formData),
  job: (id) => request('GET', `/jobs/${id}`),
  jobs: () => request('GET', '/jobs'),

  // ── Notas ──
  notas: (empresaId, params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
    ).toString()
    return request('GET', `/fiscal/empresas/${empresaId}/notas${q ? `?${q}` : ''}`)
  },
  notaDetalhe: (id) => request('GET', `/fiscal/notas/${id}`),
  editarNota: (id, data) => request('PATCH', `/fiscal/notas/${id}`, data),
  editarItem: (notaId, itemId, data) => request('PATCH', `/fiscal/notas/${notaId}/itens/${itemId}`, data),
  cancelarNota: (id) => request('POST', `/fiscal/notas/${id}/cancelar`),
  downloadXml: (id) => downloadBlob(`/fiscal/notas/${id}/xml`),
  downloadDanfe: (id) => downloadBlob(`/fiscal/notas/${id}/danfe`),
  tiposSped: () => request('GET', '/fiscal/tipos-sped'),
  tiposNota: () => request('GET', '/fiscal/tipos-nota'),
  // operações em lote
  cancelarLote: (empresaId, ids) => request('POST', `/fiscal/empresas/${empresaId}/notas/cancelar-lote`, { ids }),
  reativarLote: (empresaId, ids) => request('POST', `/fiscal/empresas/${empresaId}/notas/reativar-lote`, { ids }),
  cfopLote: (empresaId, ids, cfop) => request('POST', `/fiscal/empresas/${empresaId}/notas/cfop-lote`, { ids, cfop }),
  tipoLote: (empresaId, ids, tipo_nota) => request('POST', `/fiscal/empresas/${empresaId}/notas/tipo-lote`, { ids, tipo_nota }),
  xmlLote: (empresaId, ids) => downloadBlob(`/fiscal/empresas/${empresaId}/notas/xml-lote`, { body: { ids }, fallback: 'arquivo.zip' }),
  danfeLote: (empresaId, ids) => downloadBlob(`/fiscal/empresas/${empresaId}/notas/danfe-lote`, { body: { ids }, fallback: 'arquivo.zip' }),

  // ── Conformidade (Layout espera { quebras: [...] }) ──
  quebras: (empresaId, ano, mes) => {
    const q = new URLSearchParams(Object.entries({ ano, mes }).filter(([, v]) => v)).toString()
    return request('GET', `/compliance/empresas/${empresaId}/quebras${q ? `?${q}` : ''}`)
      .then(list => ({ quebras: list || [] }))
  },
  quebraCiencias: (empresaId, classificacao) => {
    const q = classificacao ? `?classificacao=${classificacao}` : ''
    return request('GET', `/compliance/empresas/${empresaId}/ciencias${q}`)
  },
  darCiencia: (empresaId, payload) => request('POST', `/compliance/empresas/${empresaId}/ciencia`, payload),
  darCienciaLote: (empresaId, payload) => request('POST', `/compliance/empresas/${empresaId}/ciencia-lote`, payload),

  // ── Relatórios (gerador avançado) ──
  relTags: () => request('GET', '/reporting/tags'),
  relModelos: (empresaId, fluxo) =>
    request('GET', `/reporting/empresas/${empresaId}/modelos${fluxo ? `?fluxo=${fluxo}` : ''}`),
  relCriarModelo: (empresaId, payload) => request('POST', `/reporting/empresas/${empresaId}/modelos`, payload),
  relEditarModelo: (id, payload) => request('PATCH', `/reporting/modelos/${id}`, payload),
  relExcluirModelo: (id) => request('DELETE', `/reporting/modelos/${id}`),
  relGerar: (empresaId, payload) => request('POST', `/reporting/empresas/${empresaId}/gerar`, payload),
  relDownload: (jobId) => downloadBlob(`/reporting/download/${jobId}`),

  // ── Regras De/Para CFOP -> Tipo de Item ──
  cfopRegras: () => request('GET', '/cfop-regras'),
  cfopRegraCriar: (data) => request('POST', '/cfop-regras', data),
  cfopRegraEditar: (id, data) => request('PATCH', `/cfop-regras/${id}`, data),
  cfopRegraExcluir: (id) => request('DELETE', `/cfop-regras/${id}`),

  // ── Dashboard (agregações) ──
  geral: () => request('GET', '/dashboard/geral'),
  empresaDashboard: (id) => request('GET', `/dashboard/empresas/${id}`),

  // ── Cadastros (contrapartes) + lookup de CNPJ ──
  contrapartes: (empresaId, tipo, search) => {
    const q = new URLSearchParams(Object.entries({ tipo, search }).filter(([, v]) => v)).toString()
    return request('GET', `/contrapartes/empresas/${empresaId}${q ? `?${q}` : ''}`)
  },
  criarContraparte: (empresaId, data) => request('POST', `/contrapartes/empresas/${empresaId}`, data),
  editarContraparte: (id, data) => request('PATCH', `/contrapartes/${id}`, data),
  consultarCNPJ: (cnpj, contexto = 'empresa') => {
    const digits = (cnpj || '').replace(/\D/g, '')
    return request('GET', `/cnpj/${digits}?contexto=${contexto}`)
  },

  // ── Grupos (controle de acesso: empresas + membros + supervisor) ──
  grupos: () => request('GET', '/grupos'),
  grupo: (id) => request('GET', `/grupos/${id}`),
  criarGrupo: (data) => request('POST', '/grupos', data),
  editarGrupo: (id, data) => request('PUT', `/grupos/${id}`, data),
  excluirGrupo: (id) => request('DELETE', `/grupos/${id}`),

  // ── Auditoria (trilha) ──
  auditoria: (params = {}) => {
    const q = new URLSearchParams(
      Object.entries(params).filter(([, v]) => v !== null && v !== undefined && v !== '')
    ).toString()
    return request('GET', `/audit${q ? `?${q}` : ''}`)
  },
  auditAcoes: () => request('GET', '/audit/acoes'),

  // ── Auditoria de ICMS-ST (divergências) ──
  stDivergencias: (empresaId, params = {}) => {
    const q = new URLSearchParams(
      Object.entries({ empresa_id: empresaId, ...params })
        .filter(([, v]) => v !== null && v !== undefined && v !== '')
    ).toString()
    return request('GET', `/auditoria/st/divergencias${q ? `?${q}` : ''}`)
  },

  // ── Recursos do V1 ainda sem endpoint no V2 (fase futura) ──
  certificado: NAO_IMPL('Certificado A1'),
  updateProfile: NAO_IMPL('Editar perfil'),
}

export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
