import clsx from 'clsx'

/**
 * Table primitives。用法:
 *   <Table>
 *     <THead><TR><TH>Name</TH><TH align="right">…</TH></TR></THead>
 *     <TBody><TR hover><TD focal>…</TD></TR></TBody>
 *   </Table>
 * 外層自帶 hairline 邊框 + overflow-x-auto。
 */
export default function Table({ className, wrapperClassName, children, bordered = true, ...rest }) {
  return (
    <div className={clsx('w-full overflow-x-auto', bordered && 'rounded-lg border border-hairline bg-surface', wrapperClassName)}>
      <table className={clsx('w-full min-w-full text-sm', className)} {...rest}>
        {children}
      </table>
    </div>
  )
}

export function THead({ className, children }) {
  return <thead className={clsx('bg-surface-muted/60', className)}>{children}</thead>
}

export function TBody({ className, children }) {
  return <tbody className={clsx('divide-y divide-hairline', className)}>{children}</tbody>
}

export function TR({ className, hover = true, selected = false, group = true, children, ...rest }) {
  return (
    <tr
      className={clsx(
        group && 'group',
        hover && 'transition-colors duration-150 hover:bg-surface-muted/50',
        selected && 'bg-accent-soft/60',
        className,
      )}
      {...rest}
    >
      {children}
    </tr>
  )
}

export function TH({ className, align = 'left', children, ...rest }) {
  return (
    <th
      scope="col"
      className={clsx(
        'h-10 whitespace-nowrap px-4 text-xs font-medium uppercase tracking-wide text-ink-muted',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        align === 'left' && 'text-left',
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  )
}

export function TD({ className, align = 'left', focal = false, mono = false, muted = false, children, ...rest }) {
  return (
    <td
      className={clsx(
        'h-12 px-4 align-middle',
        align === 'right' && 'text-right',
        align === 'center' && 'text-center',
        focal ? 'font-medium text-ink' : muted ? 'text-ink-muted' : 'text-ink',
        mono && 'font-mono text-xs',
        className,
      )}
      {...rest}
    >
      {children}
    </td>
  )
}

/** 首欄:主文字 + 次行 */
export function CellPrimary({ title, subtitle, mono = false, className, titleClassName, children }) {
  return (
    <div className={clsx('min-w-0', className)}>
      <div className={clsx('truncate font-medium text-ink', mono && 'font-mono text-xs', titleClassName)}>{title ?? children}</div>
      {subtitle && <div className="mt-0.5 truncate text-xs text-ink-muted">{subtitle}</div>}
    </div>
  )
}

/** 列的動作群:預設 hover 才出現,但仍可鍵盤 focus 到 */
export function RowActions({ className, children, always = false }) {
  return (
    <div
      className={clsx(
        'flex items-center justify-end gap-0.5',
        !always && 'opacity-0 transition-opacity duration-150 group-hover:opacity-100 focus-within:opacity-100',
        className,
      )}
    >
      {children}
    </div>
  )
}
