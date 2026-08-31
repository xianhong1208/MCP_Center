import { AlertCircle, CheckCircle2, Info, AlertTriangle } from 'lucide-react'
import clsx from 'clsx'

const tones = {
  danger: {
    icon: AlertCircle,
    className: 'border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-500/20 dark:bg-rose-500/10 dark:text-rose-300',
    iconClass: 'text-rose-600 dark:text-rose-400',
  },
  warning: {
    icon: AlertTriangle,
    className: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-300',
    iconClass: 'text-amber-600 dark:text-amber-400',
  },
  success: {
    icon: CheckCircle2,
    className: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-500/20 dark:bg-emerald-500/10 dark:text-emerald-300',
    iconClass: 'text-emerald-600 dark:text-emerald-400',
  },
  info: {
    icon: Info,
    className: 'border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-500/20 dark:bg-sky-500/10 dark:text-sky-300',
    iconClass: 'text-sky-600 dark:text-sky-400',
  },
  neutral: {
    icon: Info,
    className: 'border-hairline bg-surface-muted/60 text-ink',
    iconClass: 'text-ink-muted',
  },
}

/** 行內訊息框:淡底 + 同色系邊框 + icon */
export default function Alert({ tone = 'danger', title, icon, className, children, action }) {
  const cfg = tones[tone] || tones.danger
  const Icon = icon === null ? null : icon || cfg.icon
  return (
    <div role={tone === 'danger' ? 'alert' : 'status'} className={clsx('flex items-start gap-3 rounded-md border px-3.5 py-3 text-sm', cfg.className, className)}>
      {Icon && <Icon className={clsx('mt-0.5 h-4 w-4 shrink-0', cfg.iconClass)} aria-hidden="true" />}
      <div className="min-w-0 flex-1">
        {title && <p className="font-medium">{title}</p>}
        {children && <div className={clsx(title && 'mt-0.5', 'text-[13px] leading-relaxed opacity-90')}>{children}</div>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  )
}
