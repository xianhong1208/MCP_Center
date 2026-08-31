import clsx from 'clsx'

/** 鍵盤提示 */
export function Kbd({ className, children }) {
  return (
    <kbd
      className={clsx(
        'inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded border border-hairline bg-surface px-1 font-sans text-2xs font-medium text-ink-muted',
        className,
      )}
    >
      {children}
    </kbd>
  )
}

/** 縮寫頭像:zinc 圓形 */
export function Avatar({ name, size = 'md', className }) {
  const initial = (name || 'A').trim()[0]?.toUpperCase() || 'A'
  return (
    <span
      className={clsx(
        'inline-flex shrink-0 select-none items-center justify-center rounded-full bg-zinc-200 font-medium text-zinc-700 dark:bg-zinc-700 dark:text-zinc-200',
        size === 'sm' && 'h-6 w-6 text-xs',
        size === 'md' && 'h-8 w-8 text-sm',
        size === 'lg' && 'h-12 w-12 text-lg',
        className,
      )}
      aria-hidden="true"
    >
      {initial}
    </span>
  )
}

/** 產品 wordmark:16px 標記 + 名稱 */
export function Wordmark({ name, className, size = 'md' }) {
  return (
    <span className={clsx('inline-flex items-center gap-2', className)}>
      <LogoMark className={size === 'lg' ? 'h-6 w-6' : 'h-4 w-4'} />
      <span className={clsx('font-semibold tracking-tight text-ink', size === 'lg' ? 'text-base' : 'text-sm')}>{name}</span>
    </span>
  )
}

/** 16px logo mark:圓角方塊 + 白色鑰匙孔;單色 ink,不用漸層 */
export function LogoMark({ className }) {
  return (
    <svg viewBox="0 0 16 16" className={clsx('shrink-0 text-ink', className)} aria-hidden="true">
      <rect width="16" height="16" rx="4" fill="currentColor" />
      <circle cx="8" cy="6.25" r="2.25" className="fill-surface" />
      <rect x="7" y="7.5" width="2" height="4.5" rx="1" className="fill-surface" />
    </svg>
  )
}

/** 行內 code / id */
export function Code({ className, children, ...rest }) {
  return (
    <code className={clsx('rounded bg-surface-muted px-1 py-0.5 font-mono text-xs text-ink', className)} {...rest}>
      {children}
    </code>
  )
}

/** 水平分隔線 */
export function Divider({ className }) {
  return <hr className={clsx('border-0 border-t border-hairline', className)} />
}

/** 帶文字的分隔線(登入頁 "or") */
export function DividerWithText({ children, className }) {
  return (
    <div className={clsx('flex items-center gap-3 text-xs text-ink-subtle', className)}>
      <span className="h-px flex-1 bg-hairline" />
      {children}
      <span className="h-px flex-1 bg-hairline" />
    </div>
  )
}
