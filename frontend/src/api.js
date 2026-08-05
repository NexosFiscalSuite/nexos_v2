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
  updateUser: (id, data) => request('PATCH', `/users/${id}`, data),

  // ── Empresas ──
  empresas: () => request('GET', '/empresas'),
  // Cadastro em lote de empresas (planilha CSV — padrão das matrizes)
  exportarEmpresas: () => downloadBlob('/empresas/export', { fallback: 'empresas.csv' }),
  importarEmpresas: (file) => {
    const fd = new FormData()
    fd.append('arquivo', file)
    return request('POST', '/empresas/import', fd, true)
  },
  // Atualização em lote pela Receita (OpenCNPJ) — roda no worker, acompanhar via job
  atualizarCadastrosEmpresas: () => request('POST', '/empresas/atualizar-cadastros'),
  empresa: (id) => request('GET', `/empresas/${id}`),
  criarEmpresa: (data) => request('POST', '/empresas', data),
  editarEmpresa: (id, data) => request('PATCH', `/empresas/${id}`, data),

  // Matrizes Fiscais (MVA) — regras globais do motor de ST
  matrizesMva: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/matrizes/mva' + (q ? `?${q}` : ''))
  },
  criarMatrizMva: (data) => request('POST', '/matrizes/mva', data),
  editarMatrizMva: (id, data) => request('PATCH', `/matrizes/mva/${id}`, data),
  removerMatrizMva: (id) => request('DELETE', `/matrizes/mva/${id}`),

  matrizesEnquadramento: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/matrizes/enquadramento' + (q ? `?${q}` : ''))
  },
  criarMatrizEnquadramento: (data) => request('POST', '/matrizes/enquadramento', data),
  editarMatrizEnquadramento: (id, data) => request('PATCH', `/matrizes/enquadramento/${id}`, data),
  removerMatrizEnquadramento: (id) => request('DELETE', `/matrizes/enquadramento/${id}`),

  matrizesFcp: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/matrizes/fcp' + (q ? `?${q}` : ''))
  },
  criarMatrizFcp: (data) => request('POST', '/matrizes/fcp', data),
  editarMatrizFcp: (id, data) => request('PATCH', `/matrizes/fcp/${id}`, data),
  removerMatrizFcp: (id) => request('DELETE', `/matrizes/fcp/${id}`),

  matrizesProtocolos: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/matrizes/protocolos' + (q ? `?${q}` : ''))
  },
  criarMatrizProtocolo: (data) => request('POST', '/matrizes/protocolos', data),
  editarMatrizProtocolo: (id, data) => request('PATCH', `/matrizes/protocolos/${id}`, data),
  removerMatrizProtocolo: (id) => request('DELETE', `/matrizes/protocolos/${id}`),

  matrizesAliquotas: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/matrizes/aliquotas' + (q ? `?${q}` : ''))
  },
  criarMatrizAliquota: (data) => request('POST', '/matrizes/aliquotas', data),
  editarMatrizAliquota: (id, data) => request('PATCH', `/matrizes/aliquotas/${id}`, data),
  removerMatrizAliquota: (id) => request('DELETE', `/matrizes/aliquotas/${id}`),

  // Fila de revisão da auto-alimentação (robô propõe, curadoria aprova)
  propostasMatrizes: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/matrizes/propostas' + (q ? `?${q}` : ''))
  },
  propostasResumo: () => request('GET', '/matrizes/propostas/resumo'),
  aprovarProposta: (id) => request('POST', `/matrizes/propostas/${id}/aprovar`),
  rejeitarProposta: (id, motivo) => request('POST', `/matrizes/propostas/${id}/rejeitar`, { motivo: motivo || null }),
  aprovarPropostasLote: (payload = {}) => request('POST', '/matrizes/propostas/aprovar-lote', payload),

  // IBS/CBS 2026: destaque das alíquotas de teste da Reforma Tributária
  ibsCbsVerificacao: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/fiscal/ibs-cbs/verificacao' + (q ? `?${q}` : ''))
  },
  ibsCbsReprocessar: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('POST', '/fiscal/ibs-cbs/reprocessar' + (q ? `?${q}` : ''))
  },
  // Carta timbrada (PDF) pedindo a correção dos itens do emitente — p/ enviar ao cliente
  ibsCbsCarta: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return downloadBlob('/fiscal/ibs-cbs/carta' + (q ? `?${q}` : ''), { fallback: 'carta-ibscbs.pdf' })
  },

  // Saúde das matrizes: frescor da base (Fase 2 — radar de verificação)
  saudeMatrizes: () => request('GET', '/matrizes/saude'),
  // Pares interestaduais (Fase 3): movimento real × curadoria de protocolos
  paresInterestaduais: () => request('GET', '/matrizes/pares-interestaduais'),

  // Cobertura: o que a carteira movimenta × o que as matrizes cobrem (fila de curadoria)
  coberturaMatrizes: (params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
    return request('GET', '/matrizes/cobertura' + (q ? `?${q}` : ''))
  },

  // Bulk (planilha CSV) — export = template/base; import = upsert por chave
  exportarMatriz: (tipo) => downloadBlob(`/matrizes/${tipo}/export`, { fallback: `matriz_${tipo}.csv` }),
  importarMatriz: (tipo, file) => {
    const fd = new FormData()
    fd.append('arquivo', file)
    return request('POST', `/matrizes/${tipo}/import`, fd, true)
  },

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
  cfopExportar: () => downloadBlob('/cfop-regras/export', { fallback: 'cfop_regras.csv' }),
  cfopImportar: (file) => {
    const fd = new FormData()
    fd.append('arquivo', file)
    return request('POST', '/cfop-regras/import', fd, true)
  },

  // ── Dashboard (agregações) ──
  geral: () => request('GET', '/dashboard/geral'),
  empresaDashboard: (id) => request('GET', `/dashboard/empresas/${id}`),
  dashSaude: (ano, mes) => request('GET', `/dashboard/saude?ano=${ano}&mes=${mes}`),

  // ── Cadastros (contrapartes) + lookup de CNPJ ──
  contrapartes: (empresaId, params = {}) => {
    const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString()
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
  reprocessarPendentes: (empresaId) =>
    request('POST', '/auditoria/st/reprocessar-pendentes' + (empresaId ? `?empresa_id=${empresaId}` : '')),
  stCatalogoErros: () => request('GET', '/auditoria/st/catalogo-erros'),
  // Confirma que a nota não tem CT-e (gate do frete) e reaudita
  stConfirmarSemCte: (notaId) => request('POST', `/auditoria/st/notas/${notaId}/confirmar-sem-cte`),
  // Carta timbrada (PDF) de cobrança de ST ao fornecedor (sem antecipações)
  stCartaFornecedor: (empresaId, params = {}) => {
    const q = new URLSearchParams(
      Object.entries({ empresa_id: empresaId, ...params }).filter(([, v]) => v)
    ).toString()
    return downloadBlob(`/auditoria/st/carta?${q}`, { fallback: 'carta-st.pdf' })
  },
  // Ciência do aviso de legislação (Fase 2): registra na trilha antes de emitir
  stCienciaLegislacao: (empresaId, destino, competencia) => {
    const q = new URLSearchParams({
      empresa_id: empresaId, destino, ...(competencia ? { competencia } : {}),
    }).toString()
    return request('POST', `/auditoria/st/ciencia-legislacao?${q}`)
  },
  // Triagem das divergências: o que o escritório decidiu sobre cada item
  stDefinirTriagem: (empresaId, itens, status, observacao) =>
    request('POST', `/auditoria/st/triagem?empresa_id=${empresaId}`, {
      itens, status, observacao: observacao || null,
    }),
  // Diagnóstico executivo em PDF (todo o período auditado da empresa)
  stDiagnostico: (empresaId) =>
    downloadBlob(`/auditoria/st/diagnostico?empresa_id=${empresaId}`, { fallback: 'diagnostico-st.pdf' }),
  // Planilha Excel das divergências do filtro atual (sem paginação)
  stExportarDivergencias: (empresaId, params = {}) => {
    const q = new URLSearchParams(
      Object.entries({ empresa_id: empresaId, ...params }).filter(([, v]) => v)
    ).toString()
    return downloadBlob(`/auditoria/st/divergencias/export?${q}`, { fallback: 'divergencias-st.xlsx' })
  },

  // ── Recursos do V1 ainda sem endpoint no V2 (fase futura) ──
  certificado: NAO_IMPL('Certificado A1'),
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
