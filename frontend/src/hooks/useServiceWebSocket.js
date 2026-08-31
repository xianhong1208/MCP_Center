import { useEffect, useRef, useCallback, useState } from 'react'

/**
 * WebSocket hook for real-time service updates(/ws/services,認證走 session cookie)
 *
 * 處理:
 *   health_update / service_added / service_removed / service_updated / pong
 *
 * Reconnect 策略:
 *   - close code 1000 (normal):不重連 — 是 user 主動關
 *   - close code 4001 / 4003 (auth 失敗):session 已失效 → emit 'auth-expired',交給 AuthContext 處理
 *   - 其他 (1006 abnormal / 1011 internal):exponential backoff,最多 30s、5 次
 *
 * Cleanup hygiene:
 *   - connect() 前若有舊 ws 先 close 並 null,避免堆積殭屍連線
 *   - reconnect timeout 在 disconnect / re-effect 時清掉
 *   - 用 isMountedRef 防止 unmount 後還跑 setState
 */
export function useServiceWebSocket({ onHealthUpdate, onServiceAdded, onServiceRemoved, onServiceUpdated, enabled = true }) {
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const reconnectAttemptsRef = useRef(0)
  const isMountedRef = useRef(true)
  const [isConnected, setIsConnected] = useState(false)
  const [lastMessage, setLastMessage] = useState(null)

  const closeExistingWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.onerror = null
      try { wsRef.current.close(1000, 'cleanup') } catch {}
      wsRef.current = null
    }
  }, [])

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }
  }, [])

  const connect = useCallback(() => {
    if (!enabled || !isMountedRef.current) return

    closeExistingWs()
    clearReconnectTimer()

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/services`

    let ws
    try {
      ws = new WebSocket(wsUrl)
    } catch (err) {
      console.error('[WS] Failed to construct WebSocket:', err)
      return
    }
    wsRef.current = ws

    ws.onopen = () => {
      if (!isMountedRef.current) {
        try { ws.close(1000, 'unmounted') } catch {}
        return
      }
      reconnectAttemptsRef.current = 0
      setIsConnected(true)
    }

    ws.onmessage = (event) => {
      if (!isMountedRef.current) return
      try {
        const message = JSON.parse(event.data)
        setLastMessage(message)
        switch (message.type) {
          case 'health_update': onHealthUpdate?.(message); break
          case 'service_added': onServiceAdded?.(message); break
          case 'service_removed': onServiceRemoved?.(message); break
          case 'service_updated': onServiceUpdated?.(message); break
          case 'pong': break
          default: break
        }
      } catch (err) {
        console.error('[WS] Failed to parse message:', err)
      }
    }

    ws.onerror = () => {}

    ws.onclose = (event) => {
      if (!isMountedRef.current) return
      setIsConnected(false)
      if (!enabled) return
      if (event.code === 1000) return

      // 後端明示認證失敗:session 已失效,不要無限重連
      if (event.code === 4001 || event.code === 4003) {
        window.dispatchEvent(new CustomEvent('auth-expired', { detail: { reason: 'websocket' } }))
        return
      }

      reconnectAttemptsRef.current += 1
      if (reconnectAttemptsRef.current > 5) return
      const delay = Math.min(1000 * 2 ** (reconnectAttemptsRef.current - 1), 30000)
      reconnectTimeoutRef.current = setTimeout(connect, delay)
    }
  }, [enabled, onHealthUpdate, onServiceAdded, onServiceRemoved, onServiceUpdated, closeExistingWs, clearReconnectTimer])

  const disconnect = useCallback(() => {
    clearReconnectTimer()
    closeExistingWs()
  }, [clearReconnectTimer, closeExistingWs])

  const sendPing = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ type: 'ping' }))
    }
  }, [])

  useEffect(() => {
    isMountedRef.current = true
    if (enabled) connect()
    else disconnect()
    return () => {
      isMountedRef.current = false
      disconnect()
    }
  }, [enabled, connect, disconnect])

  // Heartbeat
  useEffect(() => {
    if (!isConnected) return
    const interval = setInterval(sendPing, 30000)
    return () => clearInterval(interval)
  }, [isConnected, sendPing])

  return { isConnected, lastMessage, reconnect: connect, disconnect }
}

export default useServiceWebSocket
