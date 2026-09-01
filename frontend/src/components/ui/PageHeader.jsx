import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import clsx from 'clsx'
import GlobalSearch from '../GlobalSearch'

/**
 * 每頁頂部:標題(text-xl semibold)+ 一行說明 + 右側動作(最多一顆 primary)。
 * backTo / backLabel:顯示上一層連結(detail 頁)。
 * meta:標題右側的小元素(StatusPill / Badge)。
 * search:標題右邊(同一行、靠左那側)放全站搜尋框;預設開,detail 頁可傳 false 關掉。
 */
export default function PageHeader({ title, description, actions, backTo, backLabel, meta, className, search = true }) {
  return (
    <div className={clsx('flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between', className)}>
      <div className="flex min-w-0 items-start gap-6">
      <div className="min-w-0">
        {backTo && (
          <Link
            to={backTo}
            className="mb-2 inline-flex items-center gap-1 text-xs font-medium text-muted-foreground transition-colors duration-200 hover:text-foreground"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            {backLabel}
          </Link>
        )}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <h1 className="truncate text-xl font-semibold tracking-tight text-foreground">{title}</h1>
          {meta}
        </div>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {search && <GlobalSearch className="hidden w-72 shrink-0 lg:flex" />}
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
