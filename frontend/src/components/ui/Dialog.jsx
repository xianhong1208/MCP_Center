import { useEffect, useCallback } from 'react'
import { X } from 'lucide-react'
import clsx from 'clsx'
import IconButton from './IconButton'

const sizes = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
}

/**
 * Dialog — 全站唯一的浮層容器。
 * 結構:overlay(black/60,不模糊)+ panel(rounded-lg border popover 底 + 銳利小陰影,200ms fade+slide)。
 * 內容用 DialogHeader / DialogBody / DialogFooter 以 border 分隔。
 * 傳 title 會自動 render DialogHeader(含右上 X)。
 */
export default function Dialog({
  open = true,
  onClose,
  title,
  description,
  children,
  size = 'md',
  showClose = true,
  className,
  panelClassName,
  zIndex = 'z-[60]',
  scrollable = true,
}) {
  const handleEscape = useCallback((e) => {
    if (e.key === 'Escape') onClose?.()
  }, [onClose])

  useEffect(() => {
    if (!open) return undefined
    document.addEventListener('keydown', handleEscape)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleEscape)
      document.body.style.overflow = ''
    }
  }, [open, handleEscape])

  if (!open) return null

  return (
    <div className={clsx('fixed inset-0 flex items-center justify-center p-4', zIndex, className)} role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-black/60 animate-fade-in" onClick={onClose} aria-hidden="true" />
      <div
        className={clsx(
          'relative flex w-full flex-col rounded-lg border border-border-strong bg-popover shadow-overlay animate-dialog-in',
          scrollable && 'max-h-[90vh]',
          sizes[size] || sizes.md,
          panelClassName,
        )}
      >
        {(title || showClose) && (
          <DialogHeader title={title} description={description} onClose={showClose ? onClose : undefined} />
        )}
        {children}
      </div>
    </div>
  )
}

export function DialogHeader({ title, description, onClose, className, children }) {
  return (
    <div className={clsx('flex items-start justify-between gap-4 border-b border-border px-5 py-4', className)}>
      <div className="min-w-0">
        {title && <h2 className="text-base font-semibold text-foreground">{title}</h2>}
        {description && <p className="mt-0.5 text-xs text-muted-foreground">{description}</p>}
        {children}
      </div>
      {onClose && <IconButton icon={X} title="Close" onClick={onClose} className="-mr-1.5 -mt-1" />}
    </div>
  )
}

export function DialogBody({ className, children }) {
  return <div className={clsx('min-h-0 flex-1 overflow-y-auto px-5 py-5', className)}>{children}</div>
}

export function DialogFooter({ className, children, between = false }) {
  return (
    <div className={clsx('flex items-center gap-2 border-t border-border px-5 py-3', between ? 'justify-between' : 'justify-end', className)}>
      {children}
    </div>
  )
}
