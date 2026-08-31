import { forwardRef } from 'react'
import { Link } from 'react-router-dom'
import clsx from 'clsx'

/**
 * IconButton — 8x8(h-8 w-8)的方形 icon 按鈕,一定要給 `title`(同時當 aria-label)。
 * variant: ghost | secondary | destructive
 * size: md(h-8)| sm(h-7)
 */
const variants = {
  ghost: 'text-ink-muted hover:bg-surface-muted hover:text-ink border border-transparent',
  secondary: 'text-ink-muted bg-surface border border-hairline-strong shadow-sm hover:bg-surface-muted hover:text-ink',
  destructive: 'text-ink-muted hover:bg-rose-50 hover:text-rose-600 border border-transparent dark:hover:bg-rose-500/10 dark:hover:text-rose-400',
  accent: 'text-ink-muted hover:bg-accent-soft hover:text-accent border border-transparent',
}

const sizes = {
  md: 'h-8 w-8',
  sm: 'h-7 w-7',
}

const IconButton = forwardRef(function IconButton(
  { icon: Icon, title, variant = 'ghost', size = 'md', className, to, children, type, ...rest },
  ref,
) {
  const classes = clsx(
    'inline-flex shrink-0 items-center justify-center rounded-md transition-colors duration-150',
    'disabled:pointer-events-none disabled:opacity-40',
    variants[variant] || variants.ghost,
    sizes[size] || sizes.md,
    className,
  )
  const content = Icon ? <Icon className="h-4 w-4" aria-hidden="true" /> : children
  if (to) {
    return (
      <Link ref={ref} to={to} title={title} aria-label={title} className={classes} {...rest}>
        {content}
      </Link>
    )
  }
  return (
    <button ref={ref} type={type || 'button'} title={title} aria-label={title} className={classes} {...rest}>
      {content}
    </button>
  )
})

export default IconButton
