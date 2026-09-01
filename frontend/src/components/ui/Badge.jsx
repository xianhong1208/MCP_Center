import clsx from 'clsx'

/**
 * 語意色都是「淡底 /10 + 語意色字 + inset ring /20」,兩個主題共用同一組 class(token 自己換值)。
 * tone: neutral | accent(海軍藍,kind / 標籤)| success | warning | danger | info
 */
export const badgeTones = {
  neutral: 'bg-muted text-muted-foreground ring-border',
  accent: 'bg-primary-soft text-primary-soft-foreground ring-primary/40',
  success: 'bg-success/10 text-success ring-success/20',
  warning: 'bg-warning/10 text-warning ring-warning/20',
  danger: 'bg-danger/10 text-danger ring-danger/20',
  info: 'bg-info/10 text-info ring-info/20',
}

export const dotTones = {
  neutral: 'bg-subtle-foreground',
  accent: 'bg-accent',
  success: 'bg-success',
  warning: 'bg-warning',
  danger: 'bg-danger',
  info: 'bg-info',
}

/** 小標籤(kind / tag / scope) */
export default function Badge({ tone = 'neutral', mono = false, size = 'sm', className, children, ...rest }) {
  return (
    <span
      className={clsx(
        'inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded font-medium ring-1 ring-inset',
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
      className={clsx('inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap text-xs font-medium text-muted-foreground', className)}
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
