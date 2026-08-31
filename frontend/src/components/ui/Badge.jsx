import clsx from 'clsx'

/**
 * 語意色都是「淡底 + 深字 + inset ring」,dark 用 /10 底 + 400 字。
 * tone: neutral | accent | success | warning | danger | info
 */
export const badgeTones = {
  neutral: 'bg-surface-muted text-ink-muted ring-hairline',
  accent: 'bg-accent-soft text-accent ring-accent/20',
  success: 'bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-400 dark:ring-emerald-500/20',
  warning: 'bg-amber-50 text-amber-700 ring-amber-600/20 dark:bg-amber-500/10 dark:text-amber-400 dark:ring-amber-500/20',
  danger: 'bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-400 dark:ring-rose-500/20',
  info: 'bg-sky-50 text-sky-700 ring-sky-600/20 dark:bg-sky-500/10 dark:text-sky-400 dark:ring-sky-500/20',
}

export const dotTones = {
  neutral: 'bg-zinc-400',
  accent: 'bg-accent',
  success: 'bg-emerald-500',
  warning: 'bg-amber-500',
  danger: 'bg-rose-500',
  info: 'bg-sky-500',
}

/** 小標籤(kind / tag / scope) */
export default function Badge({ tone = 'neutral', mono = false, size = 'sm', className, children, ...rest }) {
  return (
    <span
      className={clsx(
        'inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-md font-medium ring-1 ring-inset',
        size === 'sm' ? 'h-5 px-1.5 text-xs' : 'h-6 px-2 text-xs',
        mono && 'font-mono',
        badgeTones[tone] || badgeTones.neutral,
        className,
      )}
      {...rest}
    >
      {children}
    </span>
  )
}

/** 狀態:圓點 + 文字。`pulse` 用在進行中狀態。 */
export function StatusPill({ tone = 'neutral', pulse = false, className, children, ...rest }) {
  return (
    <span
      className={clsx('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink-muted', className)}
      {...rest}
    >
      <span
        className={clsx('h-1.5 w-1.5 shrink-0 rounded-full', dotTones[tone] || dotTones.neutral, pulse && 'animate-pulse')}
        aria-hidden="true"
      />
      {children}
    </span>
  )
}

/** 單純的顏色圓點(表格首欄用) */
export function StatusDot({ tone = 'neutral', pulse = false, className }) {
  return (
    <span
      className={clsx('inline-block h-2 w-2 shrink-0 rounded-full', dotTones[tone] || dotTones.neutral, pulse && 'animate-pulse', className)}
      aria-hidden="true"
    />
  )
}
