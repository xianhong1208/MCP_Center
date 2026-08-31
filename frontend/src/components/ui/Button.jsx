import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import Spinner from './Spinner'

/**
 * Button — 全站唯一的按鈕樣式來源。
 *
 * variant:
 *   primary      實心 indigo(每個畫面最多一顆)
 *   secondary    白底 + zinc 邊框
 *   ghost        無邊框,hover 才有底
 *   destructive  rose 文字,hover 淡 rose 底(只在確認 dialog 內用 destructiveSolid)
 *   destructiveSolid  實心 rose
 *   soft         淡 indigo 底(選中 / 切換狀態用,不要用 className 覆寫 secondary 來做選中)
 * size: md(h-9)| sm(h-8)
 * 傳 `to` 會 render 成 <Link>,傳 `href` 會 render 成 <a>。
 */
export const buttonVariants = {
  primary:
    'bg-accent text-white shadow-sm hover:bg-accent-hover border border-transparent',
  secondary:
    'bg-surface text-ink border border-hairline-strong shadow-sm hover:bg-surface-muted',
  ghost:
    'bg-transparent text-ink-muted border border-transparent hover:bg-surface-muted hover:text-ink',
  destructive:
    'bg-transparent text-rose-600 border border-transparent hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-500/10',
  destructiveSolid:
    'bg-rose-600 text-white shadow-sm hover:bg-rose-700 border border-transparent',
  soft:
    'bg-accent-soft text-accent border border-accent/30 shadow-sm hover:bg-accent-soft',
}

export const buttonSizes = {
  md: 'h-9 px-3.5 text-sm gap-2',
  sm: 'h-8 px-3 text-sm gap-1.5',
  xs: 'h-7 px-2.5 text-xs gap-1.5',
}

const Button = forwardRef(function Button(
  { variant = 'secondary', size = 'md', loading = false, icon: Icon, className, children, to, href, disabled, type, ...rest },
  ref,
) {
  const classes = clsx(
    'inline-flex items-center justify-center whitespace-nowrap rounded-md font-medium',
    'transition-colors duration-150 select-none',
    'disabled:pointer-events-none disabled:opacity-50',
    buttonVariants[variant] || buttonVariants.secondary,
    buttonSizes[size] || buttonSizes.md,
    className,
  )
  const content = (
    <>
      {loading ? <Spinner size="xs" className="shrink-0" /> : Icon ? <Icon className="h-4 w-4 shrink-0" aria-hidden="true" /> : null}
      {children}
    </>
  )
  if (to) {
    return (
      <Link ref={ref} to={to} className={clsx(classes, disabled && 'pointer-events-none opacity-50')} {...rest}>
        {content}
      </Link>
    )
  }
  if (href) {
    return (
      <a ref={ref} href={href} className={classes} {...rest}>
        {content}
      </a>
    )
  }
  return (
    <button ref={ref} type={type || 'button'} className={classes} disabled={disabled || loading} {...rest}>
      {content}
    </button>
  )
})

export default Button
