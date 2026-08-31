import { createContext, useContext, useState, useCallback } from 'react'
import { CheckCircle2, XCircle, AlertCircle, Info, X } from 'lucide-react'
import clsx from 'clsx'

const ToastContext = createContext()

const toastConfig = {
  success: { icon: CheckCircle2, iconClass: 'text-emerald-600 dark:text-emerald-400' },
  error: { icon: XCircle, iconClass: 'text-rose-600 dark:text-rose-400' },
  warning: { icon: AlertCircle, iconClass: 'text-amber-600 dark:text-amber-400' },
  info: { icon: Info, iconClass: 'text-accent' },
}

export function useToast() {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((message, type = 'info', duration = 4000) => {
    const id = Date.now() + Math.random()
    setToasts(prev => [...prev, { id, message, type }])

    if (duration > 0) {
      setTimeout(() => {
        setToasts(prev => prev.filter(t => t.id !== id))
      }, duration)
    }

    return id
  }, [])

  const removeToast = useCallback((id) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const toast = {
    success: (message, duration) => addToast(message, 'success', duration),
    error: (message, duration) => addToast(message, 'error', duration),
    warning: (message, duration) => addToast(message, 'warning', duration),
    info: (message, duration) => addToast(message, 'info', duration),
  }

  return (
    <ToastContext.Provider value={toast}>
      {children}

      {/* Toast container */}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-full max-w-sm flex-col gap-2">
        {toasts.map((t) => {
          const config = toastConfig[t.type] || toastConfig.info
          const Icon = config.icon

          return (
            <div
              key={t.id}
              role={t.type === 'error' ? 'alert' : 'status'}
              className={clsx(
                'pointer-events-auto flex items-start gap-3 rounded-lg border border-hairline bg-surface-elevated px-4 py-3 shadow-overlay',
                'animate-toast-in',
              )}
            >
              <Icon className={clsx('mt-0.5 h-4 w-4 shrink-0', config.iconClass)} aria-hidden="true" />
              <p className="flex-1 text-sm text-ink">{t.message}</p>
              <button
                onClick={() => removeToast(t.id)}
                className="-mr-1 -mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded text-ink-subtle transition-colors duration-150 hover:bg-surface-muted hover:text-ink"
                aria-label="Dismiss"
              >
                <X className="h-3.5 w-3.5" />
              </button>
            </div>
          )
        })}
      </div>
    </ToastContext.Provider>
  )
}
