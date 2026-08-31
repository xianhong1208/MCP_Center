import { useTranslation } from 'react-i18next'
import { AlertTriangle, Trash2, Ban, Info } from 'lucide-react'
import clsx from 'clsx'
import Dialog, { DialogFooter } from './ui/Dialog'
import Button from './ui/Button'

const iconMap = {
  danger: { icon: AlertTriangle, className: 'bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400', button: 'destructiveSolid' },
  delete: { icon: Trash2, className: 'bg-rose-50 text-rose-600 dark:bg-rose-500/10 dark:text-rose-400', button: 'destructiveSolid' },
  warning: { icon: AlertTriangle, className: 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400', button: 'destructiveSolid' },
  revoke: { icon: Ban, className: 'bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400', button: 'destructiveSolid' },
  info: { icon: Info, className: 'bg-accent-soft text-accent', button: 'primary' },
}

export default function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmText,
  cancelText,
  type = 'danger', // danger, warning, info, delete, revoke
  isLoading = false,
}) {
  const { t } = useTranslation()
  if (!isOpen) return null

  // Defaults via i18n,不能用 fn default 因為 hook 必須在頂端
  const resolvedTitle = title || t('components.confirm.title')
  const resolvedConfirmText = confirmText || t('components.confirm.confirm')
  const resolvedCancelText = cancelText || t('components.confirm.cancel')

  const cfg = iconMap[type] || iconMap.danger
  const Icon = cfg.icon

  const handleConfirm = () => {
    onConfirm()
  }

  return (
    <Dialog open onClose={onClose} size="sm" showClose={false} zIndex="z-[100]">
      <div className="px-5 pt-5 pb-4">
        <div className="flex items-start gap-4">
          <div className={clsx('flex h-10 w-10 shrink-0 items-center justify-center rounded-full', cfg.className)}>
            <Icon className="h-5 w-5" aria-hidden="true" />
          </div>
          <div className="min-w-0 pt-0.5">
            <h2 className="text-base font-semibold text-ink">{resolvedTitle}</h2>
            <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-ink-muted">{message}</p>
          </div>
        </div>
      </div>
      <DialogFooter>
        <Button variant="secondary" onClick={onClose} disabled={isLoading}>
          {resolvedCancelText}
        </Button>
        <Button variant={cfg.button} onClick={handleConfirm} loading={isLoading} autoFocus>
          {resolvedConfirmText}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}
