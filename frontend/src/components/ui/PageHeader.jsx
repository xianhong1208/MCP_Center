import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import clsx from 'clsx'

/**
 * 每頁頂部:標題(text-xl semibold)+ 一行說明 + 右側動作(最多一顆 primary)。
 * backTo / backLabel:顯示上一層連結(detail 頁)。
 * meta:標題右側的小元素(StatusPill / Badge)。
 */
export default function PageHeader({ title, description, actions, backTo, backLabel, meta, className }) {
  return (
    <div className={clsx('flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between', className)}>
      <div className="min-w-0">
        {backTo && (
          <Link
            to={backTo}
            className="mb-2 inline-flex items-center gap-1 text-xs font-medium text-ink-muted transition-colors duration-150 hover:text-ink"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            {backLabel}
          </Link>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="truncate text-xl font-semibold tracking-tight text-ink">{title}</h1>
          {meta}
        </div>
        {description && <p className="mt-1 text-sm text-ink-muted">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** 頁面容器:max-w-7xl,區段間 space-y-8 */
export function Page({ className, children, narrow = false }) {
  return (
    <div className={clsx('mx-auto w-full space-y-8', narrow ? 'max-w-3xl' : 'max-w-7xl', className)}>
      {children}
    </div>
  )
}
