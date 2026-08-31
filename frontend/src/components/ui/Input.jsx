import { forwardRef } from 'react'
import clsx from 'clsx'

/** 表單標籤:text-sm medium,置於欄位上方 */
export function Label({ className, children, required, ...rest }) {
  return (
    <label className={clsx('mb-1.5 block text-sm font-medium text-ink', className)} {...rest}>
      {children}
      {required && <span className="ml-0.5 text-rose-500" aria-hidden="true">*</span>}
    </label>
  )
}

/** 欄位下方說明 */
export function Help({ className, children }) {
  if (!children) return null
  return <p className={clsx('mt-1.5 text-xs text-ink-muted', className)}>{children}</p>
}

/** 欄位錯誤 */
export function FieldError({ className, children }) {
  if (!children) return null
  return <p className={clsx('mt-1.5 text-xs text-rose-600 dark:text-rose-400', className)}>{children}</p>
}

/** Field = Label + control + Help/Error 的排版容器 */
export function Field({ label, htmlFor, help, error, required, className, children }) {
  return (
    <div className={clsx('min-w-0', className)}>
      {label && <Label htmlFor={htmlFor} required={required}>{label}</Label>}
      {children}
      {error ? <FieldError>{error}</FieldError> : <Help>{help}</Help>}
    </div>
  )
}

export const Input = forwardRef(function Input({ className, size = 'md', invalid = false, mono = false, ...rest }, ref) {
  return (
    <input
      ref={ref}
      className={clsx('ui-input', size === 'sm' && 'ui-input-sm', invalid && 'ui-input-error', mono && 'font-mono', className)}
      {...rest}
    />
  )
})

export const Select = forwardRef(function Select({ className, size = 'md', invalid = false, children, ...rest }, ref) {
  return (
    <select
      ref={ref}
      className={clsx('ui-input', size === 'sm' && 'ui-input-sm', invalid && 'ui-input-error', className)}
      {...rest}
    >
      {children}
    </select>
  )
})

export const Textarea = forwardRef(function Textarea({ className, invalid = false, mono = false, ...rest }, ref) {
  return (
    <textarea
      ref={ref}
      className={clsx('ui-input resize-none', invalid && 'ui-input-error', mono && 'font-mono', className)}
      {...rest}
    />
  )
})

export const Checkbox = forwardRef(function Checkbox({ className, ...rest }, ref) {
  return <input ref={ref} type="checkbox" className={clsx('ui-checkbox', className)} {...rest} />
})

export const Radio = forwardRef(function Radio({ className, ...rest }, ref) {
  return <input ref={ref} type="radio" className={clsx('ui-radio', className)} {...rest} />
})

/** 帶說明的勾選列(consent scope、表單 boolean 選項) */
export function CheckRow({ label, description, className, disabled, ...inputProps }) {
  return (
    <label
      className={clsx(
        'flex items-start gap-3 text-sm',
        disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer',
        className,
      )}
    >
      <Checkbox className="mt-0.5" disabled={disabled} {...inputProps} />
      <span className="min-w-0">
        <span className="block font-medium text-ink">{label}</span>
        {description && <span className="mt-0.5 block text-xs text-ink-muted">{description}</span>}
      </span>
    </label>
  )
}

/** 搜尋框:左側 icon 的 Input */
export function SearchInput({ className, icon: Icon, size = 'md', ...rest }) {
  return (
    <div className={clsx('relative', className)}>
      {Icon && <Icon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-subtle" aria-hidden="true" />}
      <Input type="search" size={size} className={clsx(Icon && 'pl-8')} {...rest} />
    </div>
  )
}
