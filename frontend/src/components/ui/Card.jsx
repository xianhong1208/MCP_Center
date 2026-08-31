import { Link } from 'react-router-dom'
import clsx from 'clsx'

/**
 * Card — 白底 + hairline 邊框,不投影。
 * padding: 'md'(p-5)| 'sm'(p-4)| 'none'
 * 傳 `to` 變成可點擊的 Link 卡片(hover 邊框加深)。
 */
export default function Card({ as, to, padding = 'md', interactive = false, className, children, ...rest }) {
  const Comp = to ? Link : as || 'div'
  return (
    <Comp
      to={to}
      className={clsx(
        'rounded-lg border border-hairline bg-surface',
        padding === 'md' && 'p-5',
        padding === 'sm' && 'p-4',
        (interactive || to) && 'transition-colors duration-150 hover:border-hairline-strong hover:bg-surface-muted/40',
        className,
      )}
      {...rest}
    >
      {children}
    </Comp>
  )
}

/** 卡片標頭:標題(text-sm semibold)+ 說明 + 右側動作 */
export function CardHeader({ title, description, action, className, divided = false }) {
  return (
    <div
      className={clsx(
        'flex items-start justify-between gap-4',
        divided ? '-mx-5 -mt-5 mb-5 border-b border-hairline px-5 py-4' : 'mb-4',
        className,
      )}
    >
      <div className="min-w-0">
        {title && <h3 className="text-sm font-semibold text-ink">{title}</h3>}
        {description && <p className="mt-0.5 text-xs text-ink-muted">{description}</p>}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  )
}

/** 區段小標:xs uppercase tracking-wide muted(全站唯一允許大寫的地方) */
export function SectionLabel({ className, children, ...rest }) {
  return (
    <p className={clsx('text-xs font-medium uppercase tracking-wide text-ink-muted', className)} {...rest}>
      {children}
    </p>
  )
}

/** 統計磚:label / value / meta */
export function StatTile({ label, value, meta, to, loading = false, className }) {
  return (
    <Card to={to} className={clsx('min-w-0', className)}>
      <SectionLabel>{label}</SectionLabel>
      {loading ? (
        <div className="skeleton mt-2 h-7 w-16" />
      ) : (
        <p className="mt-2 text-2xl font-semibold tabular-nums tracking-tight text-ink">{value}</p>
      )}
      {meta && !loading && <p className="mt-1 truncate text-xs text-ink-muted">{meta}</p>}
    </Card>
  )
}

/** 鍵值列表(detail 頁用):dt 在左、dd 在右 */
export function DescriptionList({ items, className }) {
  return (
    <dl className={clsx('divide-y divide-hairline', className)}>
      {items.filter(Boolean).map(({ label, value, mono }) => (
        <div key={label} className="flex items-start justify-between gap-6 py-2.5 text-sm">
          <dt className="shrink-0 text-ink-muted">{label}</dt>
          <dd className={clsx('min-w-0 text-right text-ink break-all', mono && 'font-mono text-xs')}>{value}</dd>
        </div>
      ))}
    </dl>
  )
}
