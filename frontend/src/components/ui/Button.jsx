import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'
import Spinner from './Spinner'

/**
 * Button — 全站唯一的按鈕樣式來源。
 *
 * variant:
 *   primary      實心綠 CTA(深字;每個畫面最多一顆)
 *   secondary    卡片底 + border 邊框(outline)
 *   ghost        無邊框,hover 才有底
 *   destructive  danger 文字,hover 淡 danger 底(只在確認 dialog 內用 destructiveSolid)
 *   destructiveSolid  實心 #DC2626 + 白字
 *   soft         實心海軍藍(選中 / 切換狀態用,不要用 className 覆寫 secondary 來做選中)
 * size: md(h-9)| sm(h-8)| xs(h-7)
 * 傳 `to` 會 render 成 <Link>,傳 `href` 會 render 成 <a>。
 */
export const buttonVariants = {
  primary:
    'bg-accent text-accent-foreground hover:bg-accent-hover border border-transparent',
  secondary:
    'bg-card text-foreground border border-border-strong hover:bg-foreground/[0.06]',
  ghost:
    'bg-transparent text-muted-foreground border border-transparent hover:bg-foreground/[0.06] hover:text-foreground',
  destructive:
    'bg-transparent text-danger border border-transparent hover:bg-danger/10',
  destructiveSolid:
    'bg-destructive text-destructive-foreground hover:bg-destructive-hover border border-transparent',
  soft:
    'bg-primary text-primary-foreground border border-transparent hover:bg-primary-hover',
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
    'inline-flex cursor-pointer items-center justify-center whitespace-nowrap rounded-md font-medium',
    'transition-colors duration-200 select-none',
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
