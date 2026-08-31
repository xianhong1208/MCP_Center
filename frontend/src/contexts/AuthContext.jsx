import { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react'
import { sessionApi } from '../services/api'
import { useTranslation } from 'react-i18next'
import { useToast } from './ToastContext'
import { rememberRedirect } from '../utils/redirect'

const AuthContext = createContext(null)

const DEFAULT_IDLE_TIMEOUT_MS = 30 * 60 * 1000  // 30 分鐘
const CHECK_INTERVAL_MS = 30 * 1000              // 每 30 秒檢查一次

/**
 * 單租戶:登入即管理員,沒有角色 / 權限。
 * user 形狀:{ id, email, username, auth_provider, has_password, is_active, created_at, last_login }
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)
  const toast = useToast()
  const { t } = useTranslation()
  const lastActivityRef = useRef(Date.now())
  const idleTimeoutMsRef = useRef(DEFAULT_IDLE_TIMEOUT_MS)
  const isLoggingOutRef = useRef(false)

  const applyIdleTimeout = (minutes) => {
    if (minutes) idleTimeoutMsRef.current = minutes * 60 * 1000
  }

  // 強制登出
  const forceLogout = useCallback(async () => {
    if (isLoggingOutRef.current) return
    isLoggingOutRef.current = true
    try { await sessionApi.logout() } catch {}
    setUser(null)
    setTimeout(() => { isLoggingOutRef.current = false }, 0)
  }, [])

  // 啟動時檢查 session(cookie 自動攜帶)
  useEffect(() => {
    const checkAuth = async () => {
      try {
        const userData = await sessionApi.me()
        applyIdleTimeout(userData.idle_timeout_minutes)
        setUser(userData)
      } catch {
        setUser(null)
      } finally {
        setIsLoading(false)
      }
    }
    checkAuth()
  }, [])

  // 監聽使用者活動(用於閒置超時)
  useEffect(() => {
    const updateActivity = () => { lastActivityRef.current = Date.now() }
    const events = ['mousedown', 'keydown', 'scroll', 'touchstart']
    events.forEach(event => window.addEventListener(event, updateActivity, { passive: true }))
    return () => {
      events.forEach(event => window.removeEventListener(event, updateActivity))
    }
  }, [])

  // 定期檢查閒置超時
  useEffect(() => {
    if (!user) return
    const interval = setInterval(() => {
      const idleMs = Date.now() - lastActivityRef.current
      if (idleTimeoutMsRef.current > 0 && idleMs >= idleTimeoutMsRef.current) {
        // 記住所在頁面,重新登入後送回去;並明確告知原因
        rememberRedirect(window.location.pathname + window.location.search)
        toast.info(t('auth.notices.idleLogout'), 8000)
        forceLogout()
      }
    }, CHECK_INTERVAL_MS)
    return () => clearInterval(interval)
  }, [user, forceLogout, toast, t])

  // 監聽 API 401 回應(session 被後端拒絕)
  useEffect(() => {
    const handleAuthExpired = () => {
      if (!user) return
      rememberRedirect(window.location.pathname + window.location.search)
      toast.warning(t('auth.notices.sessionExpired'), 8000)
      forceLogout()
    }
    window.addEventListener('auth-expired', handleAuthExpired)
    return () => window.removeEventListener('auth-expired', handleAuthExpired)
  }, [user, forceLogout, toast, t])

  const login = useCallback(async (email, password) => {
    setError(null)
    try {
      const result = await sessionApi.login(email, password)
      applyIdleTimeout(result.idle_timeout_minutes)
      lastActivityRef.current = Date.now()
      setUser(result.user)
      return result
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  /** 首次啟動建立擁有者帳號,成功即登入 */
  const setup = useCallback(async (email, password, username) => {
    setError(null)
    try {
      const result = await sessionApi.setup(email, password, username)
      applyIdleTimeout(result.idle_timeout_minutes)
      lastActivityRef.current = Date.now()
      setUser(result.user)
      return result
    } catch (err) {
      setError(err.message)
      throw err
    }
  }, [])

  const logout = useCallback(async () => {
    try { await sessionApi.logout() } catch {}
    setUser(null)
  }, [])

  // 重新載入目前使用者(例如改名後)
  const refreshUser = useCallback(async () => {
    try {
      const userData = await sessionApi.me()
      setUser(userData)
      return userData
    } catch {
      setUser(null)
      return null
    }
  }, [])

  const value = {
    user,
    isLoading,
    error,
    isAuthenticated: !!user,
    login,
    setup,
    logout,
    refreshUser,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
