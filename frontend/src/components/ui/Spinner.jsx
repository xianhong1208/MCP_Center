import clsx from 'clsx'

const sizes = {
  xs: 'h-3.5 w-3.5 border-[1.5px]',
  sm: 'h-4 w-4 border-2',
  md: 'h-5 w-5 border-2',
  lg: 'h-6 w-6 border-2',
}

/** 圓形 spinner:用 currentColor,放在任何文字色裡都對 */
export default function Spinner({ size = 'md', className }) {
  return (
    <span
      role="status"
      aria-live="polite"
      className={clsx(
        'inline-block shrink-0 animate-spin rounded-full border-current border-t-transparent',
        sizes[size] || sizes.md,
        className,
      )}
    />
  )
}

/** 區塊載入中(頁面 / 卡片內容) */
export function LoadingBlock({ className, size = 'md' }) {
  return (
    <div className={clsx('flex items-center justify-center py-12 text-ink-subtle', className)}>
      <Spinner size={size} />
    </div>
  )
}
