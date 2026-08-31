import clsx from 'clsx'

/**
 * Tabs(受控):items = [{ key, label, count?, icon? }]
 * 底線式;選中用 accent 底線 + ink 文字。
 */
export default function Tabs({ items, value, onChange, className, size = 'md' }) {
  return (
    <div className={clsx('flex items-center gap-1 border-b border-hairline', className)} role="tablist">
      {items.map((item) => {
        const active = item.key === value
        const Icon = item.icon
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={clsx(
              '-mb-px inline-flex items-center gap-1.5 border-b-2 px-3 font-medium transition-colors duration-150',
              size === 'md' ? 'h-10 text-sm' : 'h-9 text-sm',
              active
                ? 'border-accent text-ink'
                : 'border-transparent text-ink-muted hover:border-hairline-strong hover:text-ink',
            )}
          >
            {Icon && <Icon className="h-4 w-4" aria-hidden="true" />}
            {item.label}
            {item.count != null && (
              <span
                className={clsx(
                  'ml-0.5 inline-flex h-5 min-w-[1.25rem] items-center justify-center rounded-md px-1.5 text-xs tabular-nums',
                  active ? 'bg-accent-soft text-accent' : 'bg-surface-muted text-ink-muted',
                )}
              >
                {item.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

/** 分段切換(小型、pill 式):items = [{ key, label }] */
export function SegmentedControl({ items, value, onChange, className, size = 'md' }) {
  return (
    <div className={clsx('inline-flex items-center rounded-md border border-hairline bg-surface-muted/60 p-0.5', className)} role="tablist">
      {items.map((item) => {
        const active = item.key === value
        const Icon = item.icon
        return (
          <button
            key={item.key}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(item.key)}
            className={clsx(
              'inline-flex items-center gap-1.5 rounded px-2.5 font-medium transition-colors duration-150',
              size === 'md' ? 'h-7 text-sm' : 'h-6 text-xs',
              active ? 'bg-surface text-ink shadow-sm' : 'text-ink-muted hover:text-ink',
            )}
          >
            {Icon && <Icon className="h-3.5 w-3.5" aria-hidden="true" />}
            {item.label}
          </button>
        )
      })}
    </div>
  )
}
