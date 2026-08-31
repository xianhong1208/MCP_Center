import { useEffect, useRef } from 'react'

/**
 * 分頁可見時每 intervalMs 執行一次 fn;使用者切回分頁時立即補跑一次。
 * enabled=false 時完全停用(不佔用 timer)。
 *
 * 為什麼要看 visibilityState:背景分頁持續打 API 只會浪費伺服器與電池,
 * 而且使用者回來時看到的仍可能是舊資料 —— 「切回即刷新」才是他們要的。
 */
export default function useVisiblePolling(fn, intervalMs, enabled = true) {
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!enabled || !intervalMs) return
    const run = () => {
      if (document.visibilityState === 'visible') fnRef.current()
    }
    const id = setInterval(run, intervalMs)
    document.addEventListener('visibilitychange', run)
    return () => {
      clearInterval(id)
      document.removeEventListener('visibilitychange', run)
    }
  }, [intervalMs, enabled])
}
