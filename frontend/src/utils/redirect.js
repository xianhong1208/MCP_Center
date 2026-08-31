/**
 * 登入過期 / 未登入時記住使用者所在頁面,登入後送回去。
 * OAuth 流程也靠這個:後端把未登入的瀏覽器導到 /consent?rid=...,
 * ProtectedRoute 記住它,登入(含第三方登入)後回到同意頁。
 *
 * 只接受同站的相對路徑:以單一 '/' 開頭、不是 '//'(協定相對 URL 會跳去外站)、
 * 不含控制字元與空白、也不是 /login 或 /setup 自己(避免登入後又回登入頁)。
 */
const STORAGE_KEY = 'mcp_redirect_after_login'

export function safeRedirectPath(raw, fallback = '/') {
  if (typeof raw !== 'string' || raw.length === 0 || raw.length > 2048) return fallback
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return fallback
  if (/[\x00-\x20]/.test(raw)) return fallback
  for (const own of ['/login', '/setup']) {
    if (raw === own || raw.startsWith(`${own}?`) || raw.startsWith(`${own}/`)) return fallback
  }
  return raw
}

export function rememberRedirect(path) {
  try { sessionStorage.setItem(STORAGE_KEY, path) } catch { /* storage 不可用時靜默 */ }
}

/** 只看不清除(給第三方登入的 ?next= 用;登入完成後由 callback 直接導向)。 */
export function peekRedirect(fallback = '/') {
  try {
    return safeRedirectPath(sessionStorage.getItem(STORAGE_KEY), fallback)
  } catch {
    return fallback
  }
}

/** 取出並清除;永遠回傳安全路徑。 */
export function consumeRedirect(fallback = '/') {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    sessionStorage.removeItem(STORAGE_KEY)
    return safeRedirectPath(raw, fallback)
  } catch {
    return fallback
  }
}
