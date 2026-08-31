/**
 * MCP Center API client.
 *
 * 登入狀態是 httpOnly cookie(mcp_session),前端不碰任何 session token。
 *
 * Error envelope(後端 i18n 化):
 *   1. HTTPException: detail 為 dict {error: "code", params: {...}, fallback: "english"}
 *   2. session routes / OAuth endpoints: top-level {error: "code", message?, params?, error_description?}
 *   3. 純字串 detail / message
 * handler 自動偵測,優先用 code 查 i18n(errors.<code>),沒對應就 fallback。
 */
import i18n from '../i18n'

const API_BASE = ''  // same origin

class ApiError extends Error {
  constructor(message, status, data, code) {
    super(message)
    this.status = status
    this.data = data
    this.code = code  // 後端 error code(若有),供 caller 做 case-by-case 判斷
  }
}

/**
 * 從 response body 抽出「使用者該看到的訊息」
 * 優先序: i18n(errors.<code>) → fallback string → 預設訊息
 */
function extractErrorMessage(data) {
  let code = null
  let params = {}
  let fallback = null

  if (data && typeof data.detail === 'object' && data.detail !== null) {
    code = data.detail.error || null
    params = data.detail.params || {}
    fallback = data.detail.fallback || data.detail.message || null
  } else if (data && typeof data.error === 'string') {
    code = data.error
    params = data.params || {}
    fallback = data.message || data.error_description || data.detail || null
  } else {
    fallback = data?.detail || data?.message || null
  }

  if (code && i18n.exists && i18n.exists(`errors.${code}`)) {
    return { code, message: i18n.t(`errors.${code}`, params) }
  }
  return { code, message: fallback || code || 'Request failed' }
}

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`
  const config = {
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
    credentials: 'include',
    ...options,
  }

  try {
    const response = await fetch(url, config)
    const data = await response.json().catch(() => ({}))

    if (!response.ok) {
      if (response.status === 401) {
        window.dispatchEvent(new CustomEvent('auth-expired', { detail: { reason: 'session_expired' } }))
      }
      const { code, message } = extractErrorMessage(data)
      throw new ApiError(message, response.status, data, code)
    }
    return data
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(error.message || 'Network error', 0, null, null)
  }
}

const qs = (params) => {
  const p = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.append(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

// ==================== Session(管理台登入)====================

export const sessionApi = {
  /** 登入頁資訊:是否需首次設定、可用登入方式、閒置逾時 */
  async status() {
    return request('/api/session/status')
  },

  /** 首次啟動:建立擁有者帳號並直接登入 */
  async setup(email, password, username) {
    return request('/api/session/setup', {
      method: 'POST',
      body: JSON.stringify({ email, password, username: username || null }),
    })
  },

  async login(email, password) {
    return request('/api/session/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    })
  },

  async logout() {
    return request('/api/session/logout', { method: 'POST' })
  },

  /** 目前登入者(cookie 自動攜帶) */
  async me() {
    return request('/api/session/me')
  },

  async updateProfile(username) {
    return request('/api/session/me/profile', {
      method: 'PUT',
      body: JSON.stringify({ username }),
    })
  },

  /** currentPassword 可為 null(第三方登入、尚未設密碼的帳號) */
  async changePassword(currentPassword, newPassword) {
    return request('/api/session/me/password', {
      method: 'PUT',
      body: JSON.stringify({ current_password: currentPassword || null, new_password: newPassword }),
    })
  },

  /** 第三方登入起點(整頁跳轉,非 XHR) */
  oauthStartUrl(provider, next) {
    const base = `/api/session/oauth/${encodeURIComponent(provider)}/start`
    return next ? `${base}?next=${encodeURIComponent(next)}` : base
  },
}

// ==================== Services ====================

function serviceBody({
  name, description, host, port, protocol, mcpPath, tags, requiresAuth, authToken, oauthAudience, oauthScopes, isActive,
}) {
  const body = {}
  if (name !== undefined) body.name = name
  if (description !== undefined) body.description = description
  if (host !== undefined) body.host = host
  if (port !== undefined) body.port = port
  if (protocol !== undefined) body.protocol = protocol
  if (mcpPath !== undefined) body.mcp_path = mcpPath
  if (tags !== undefined) body.tags = tags
  if (requiresAuth !== undefined) body.requires_auth = requiresAuth
  if (authToken !== undefined) body.auth_token = authToken   // '' = 清除(update)
  if (oauthAudience !== undefined) body.oauth_audience = oauthAudience   // '' = 清除,改用 MCP URL
  if (oauthScopes !== undefined) body.oauth_scopes = oauthScopes         // [] = 不限制
  if (isActive !== undefined) body.is_active = isActive
  return body
}

export const servicesApi = {
  async getAll({ healthStatus, source, tag, requiresAuth, includeInactive } = {}) {
    return request(`/api/services${qs({
      health_status: healthStatus, source, tag, requires_auth: requiresAuth,
      include_inactive: includeInactive ? 'true' : undefined,
    })}`)
  },

  async getById(id, includeTools = false) {
    return request(`/api/services/${encodeURIComponent(id)}?include_tools=${includeTools}`)
  },

  async create(fields) {
    return request('/api/services', { method: 'POST', body: JSON.stringify(serviceBody(fields)) })
  },

  async update(id, fields) {
    return request(`/api/services/${encodeURIComponent(id)}`, {
      method: 'PUT',
      body: JSON.stringify(serviceBody(fields)),
    })
  },

  async delete(id) {
    return request(`/api/services/${encodeURIComponent(id)}`, { method: 'DELETE' })
  },

  async getTools(id) {
    return request(`/api/services/${encodeURIComponent(id)}/tools`)
  },

  /** 連到服務抓 tools;受 MCP Center 保護的服務由後端自簽短命 token,不需再挑 token */
  async refreshTools(id) {
    return request(`/api/services/${encodeURIComponent(id)}/refresh-tools`, { method: 'POST' })
  },

  async getHealth(id) {
    return request(`/api/services/${encodeURIComponent(id)}/health`)
  },

  async checkHealth(id) {
    return request(`/api/services/${encodeURIComponent(id)}/health-check`, { method: 'POST' })
  },

  /** 一鍵檢查全部服務(走排程器同一條路徑) */
  async checkAllHealth() {
    return request('/api/services/health-check-all', { method: 'POST' })
  },
}

// ==================== Discovery ====================

export const discoveryApi = {
  async scan({ hosts, ports, portRangeStart, portRangeEnd, autoRegister, authToken, serviceName }) {
    return request('/api/discovery/scan', {
      method: 'POST',
      body: JSON.stringify({
        hosts, ports,
        port_range_start: portRangeStart,
        port_range_end: portRangeEnd,
        auto_register: autoRegister,
        auth_token: authToken,
        service_name: serviceName,
      }),
    })
  },

  async verify({ host, port, protocol, mcpPath, authToken }) {
    return request('/api/discovery/verify', {
      method: 'POST',
      body: JSON.stringify({ host, port, protocol, mcp_path: mcpPath, auth_token: authToken }),
    })
  },
}

// ==================== Stats ====================

export const statsApi = {
  /** 每日 token 事件統計;回 {stats: [{date,total,success,failed}], total, days} */
  async daily(days = 7, serviceId = null, event = null) {
    return request(`/api/stats/daily${qs({ days, service_id: serviceId, event })}`)
  },

  async hourly(hours = 24, serviceId = null, event = null) {
    return request(`/api/stats/hourly${qs({ hours, service_id: serviceId, event })}`)
  },

  async services(days = 7) {
    return request(`/api/stats/services?days=${days}`)
  },

  async summary() {
    return request('/api/stats/summary')
  },
}

// ==================== Audit ====================

export const auditApi = {
  async getLogs({ action, resourceType, actorName, status, page = 1, pageSize = 50 } = {}) {
    return request(`/api/audit/logs${qs({
      action, resource_type: resourceType, actor_name: actorName, status, page, page_size: pageSize,
    })}`)
  },

  async getStats(days = 7) {
    return request(`/api/audit/stats?days=${days}`)
  },

  async cleanup(days = 90) {
    return request(`/api/audit/cleanup?days=${days}`, { method: 'DELETE' })
  },
}

// ==================== System ====================

export const systemApi = {
  async getVersion() {
    return request('/api/system/version')
  },

  async getDashboardOverview() {
    return request('/api/system/dashboard')
  },

  async getSchedulerStatus() {
    return request('/api/system/scheduler/status')
  },

  async runCleanup() {
    return request('/api/system/cleanup/run', { method: 'POST' })
  },
}

// ==================== OAuth 2.1 管理 ====================

export const oauthApi = {
  clients: {
    /** status: all | approved | pending | revoked */
    async list(status = 'all') {
      return request(`/api/oauth/clients${qs({ status })}`)
    },
    /** 管理台手動登記受信任 client(直接核准);secret 只回一次 */
    async create({ clientName, redirectUris, grantTypes, tokenEndpointAuthMethod, scope, clientUri }) {
      return request('/api/oauth/clients', {
        method: 'POST',
        body: JSON.stringify({
          client_name: clientName,
          redirect_uris: redirectUris || [],
          grant_types: grantTypes || ['authorization_code', 'refresh_token'],
          token_endpoint_auth_method: tokenEndpointAuthMethod || 'none',
          scope: scope || null,
          client_uri: clientUri || null,
        }),
      })
    },
    async get(clientId) {
      return request(`/api/oauth/clients/${encodeURIComponent(clientId)}`)
    },
    async approve(clientId) {
      return request(`/api/oauth/clients/${encodeURIComponent(clientId)}/approve`, { method: 'POST' })
    },
    async revoke(clientId) {
      return request(`/api/oauth/clients/${encodeURIComponent(clientId)}/revoke`, { method: 'POST' })
    },
    async delete(clientId) {
      return request(`/api/oauth/clients/${encodeURIComponent(clientId)}`, { method: 'DELETE' })
    },
  },

  scopes: {
    async list() {
      return request('/api/oauth/scopes')
    },
    async upsert(name, { description, isDefault }) {
      return request(`/api/oauth/scopes/${encodeURIComponent(name)}`, {
        method: 'PUT',
        body: JSON.stringify({ description: description || null, is_default: !!isDefault }),
      })
    },
    async delete(name) {
      return request(`/api/oauth/scopes/${encodeURIComponent(name)}`, { method: 'DELETE' })
    },
  },

  tokens: {
    /** kind: pat | access | refresh;預設只列有效的 */
    async list({ kind, serviceId, clientId, includeInactive, limit } = {}) {
      return request(`/api/oauth/tokens${qs({
        kind, service_id: serviceId, client_id: clientId,
        include_inactive: includeInactive ? 'true' : undefined, limit,
      })}`)
    },
    /** 簽發 Personal Access Token;明文 access_token 只回一次 */
    async createPersonal({ serviceId, scopes, expiresDays, label }) {
      return request('/api/oauth/tokens/personal', {
        method: 'POST',
        body: JSON.stringify({
          service_id: serviceId,
          scopes: scopes && scopes.length ? scopes : null,
          expires_days: expiresDays || 30,
          label: label || null,
        }),
      })
    },
    async get(jti) {
      return request(`/api/oauth/tokens/${encodeURIComponent(jti)}`)
    },
    async revoke(jti) {
      return request(`/api/oauth/tokens/${encodeURIComponent(jti)}/revoke`, { method: 'POST' })
    },
  },

  consents: {
    async list() {
      return request('/api/oauth/consents')
    },
    async delete(consentId) {
      return request(`/api/oauth/consents/${encodeURIComponent(consentId)}`, { method: 'DELETE' })
    },
  },

  keys: {
    async list() {
      return request('/api/oauth/keys')
    },
    async rotate() {
      return request('/api/oauth/keys/rotate', { method: 'POST' })
    },
  },

  /** 最近 token 事件(issued / introspect / revoked) */
  async activity(limit = 50) {
    return request(`/api/oauth/activity?limit=${limit}`)
  },

  async overview() {
    return request('/api/oauth/overview')
  },

  /** 接入範例(FastMCP server / Claude Code / mcp.json) */
  async snippets(serviceId) {
    return request(`/api/oauth/snippets/${encodeURIComponent(serviceId)}`)
  },

  /** 同意頁:/oauth/authorize 導過來的授權請求 */
  authorizeRequest: {
    async get(rid) {
      return request(`/oauth/authorize/requests/${encodeURIComponent(rid)}`)
    },
    async decide(rid, { approve, scopes, remember }) {
      return request(`/oauth/authorize/requests/${encodeURIComponent(rid)}/decision`, {
        method: 'POST',
        body: JSON.stringify({ approve: !!approve, scopes: scopes ?? null, remember: !!remember }),
      })
    },
  },
}

// ==================== Marketplace / Managed MCP ====================

export const marketplaceApi = {
  async list() {
    return request('/api/marketplace')
  },

  async get(catalogId) {
    return request(`/api/marketplace/${encodeURIComponent(catalogId)}`)
  },

  /** 「安裝」:後端從 catalog/images/<tar> 載入 docker image(離線兩階段的第一步) */
  async installImage(catalogId) {
    return request(`/api/marketplace/${encodeURIComponent(catalogId)}/install`, { method: 'POST' })
  },
}

// BYO(自帶啟動指令)MCP:貼標準 {command, args, env} → 容器化執行 → 導出 127.0.0.1:port
export const byoApi = {
  async list() {
    return request('/api/byo-mcp')
  },

  /** body: { name, command, args, container_port?, env_schema?, description? } */
  async create(body) {
    return request('/api/byo-mcp', { method: 'POST', body: JSON.stringify(body) })
  },

  async remove(definitionId) {
    return request(`/api/byo-mcp/${encodeURIComponent(definitionId)}`, { method: 'DELETE' })
  },

  /** body: { name?, env_vars?, port?, auto_start? } */
  async deploy(definitionId, body = {}) {
    return request(`/api/byo-mcp/${encodeURIComponent(definitionId)}/deploy`, {
      method: 'POST',
      body: JSON.stringify(body),
    })
  },
}

export const managedApi = {
  /** 進行中的長操作(部署 / 啟停 / 載入 image)目前階段;純記憶體,可高頻輪詢 */
  async progress() {
    return request('/api/managed/progress')
  },

  async list() {
    return request('/api/managed')
  },

  async get(processId) {
    return request(`/api/managed/${encodeURIComponent(processId)}`)
  },

  async install({ catalogId, name, envVars, port, autoStart = true }) {
    return request('/api/managed', {
      method: 'POST',
      body: JSON.stringify({
        catalog_id: catalogId, name, env_vars: envVars, port: port || null, auto_start: autoStart,
      }),
    })
  },

  async start(processId) {
    return request(`/api/managed/${encodeURIComponent(processId)}/start`, { method: 'POST' })
  },

  /** 取容器輸出(含已退出的容器) */
  async logs(processId, tail = 200) {
    return request(`/api/managed/${encodeURIComponent(processId)}/logs?tail=${tail}`)
  },

  async stop(processId) {
    return request(`/api/managed/${encodeURIComponent(processId)}/stop`, { method: 'POST' })
  },

  async updateEnvVars(processId, envVars) {
    return request(`/api/managed/${encodeURIComponent(processId)}/env-vars`, {
      method: 'PUT',
      body: JSON.stringify({ env_vars: envVars }),
    })
  },

  async uninstall(processId) {
    return request(`/api/managed/${encodeURIComponent(processId)}`, { method: 'DELETE' })
  },
}

export { ApiError }
