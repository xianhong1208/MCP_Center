import clsx from 'clsx'
import Dialog, { DialogBody } from './ui/Dialog'

/**
 * Modal — Dialog 的相容包裝(既有呼叫端 API 不變)。
 *
 * @param {boolean} isOpen
 * @param {function} onClose
 * @param {string} title
 * @param {React.ReactNode} icon - 已不再顯示(保留參數相容)
 * @param {string} size - 'sm' | 'md' | 'lg' | 'xl' | '2xl'
 * @param {boolean} showCloseButton
 * @param {string} className - 加在 body 上
 */
export default function Modal({
  isOpen,
  onClose,
  title,
  description,
  children,
  size = 'md',
  showCloseButton = true,
  className,
}) {
  return (
    <Dialog open={!!isOpen} onClose={onClose} title={title} description={description} size={size} showClose={showCloseButton}>
      <DialogBody className={className}>{children}</DialogBody>
    </Dialog>
  )
}

/** 放在 Modal 內容底部的動作列(貼齊面板邊緣、以 border 分隔) */
export function ModalFooter({ children, className, between = false }) {
  return (
    <div
      className={clsx(
        '-mx-5 -mb-5 mt-5 flex items-center gap-2 border-t border-border px-5 py-3',
        between ? 'justify-between' : 'justify-end',
        className,
      )}
    >
      {children}
    </div>
  )
}

export function ModalBody({ children, className }) {
  return <div className={clsx('space-y-4', className)}>{children}</div>
}
