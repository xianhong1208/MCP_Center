import clsx from 'clsx'

/** 空狀態:zinc 圓形 icon + 一行標題 + 可選說明 + 可選動作 */
export default function EmptyState({ icon: Icon, title, description, action, className, compact = false }) {
  return (
    <div className={clsx('flex flex-col items-center justify-center text-center', compact ? 'py-8' : 'py-14', className)}>
      {Icon && (
        <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-surface-muted text-ink-subtle">
          <Icon className="h-5 w-5" aria-hidden="true" />
        </div>
      )}
      {title && <p className="text-sm font-medium text-ink">{title}</p>}
      {description && <p className="mt-1 max-w-sm text-xs text-ink-muted">{description}</p>}
      {action && <div className="mt-4 flex items-center gap-2">{action}</div>}
    </div>
  )
}
