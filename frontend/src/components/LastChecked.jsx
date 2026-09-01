import { useTranslation } from 'react-i18next'
import { Clock } from 'lucide-react'
import clsx from 'clsx'
import { relativeTimeParts } from '../utils/format'

/**
 * 「上次健康檢查」相對時間(例:3 分鐘前),hover 顯示絕對時間。
 * 沒有資料時不渲染 —— 呼叫端不必先判空。
 */
export default function LastChecked({ value, withIcon = true, className = '' }) {
  const { t } = useTranslation()
  const parts = relativeTimeParts(value)
  if (!parts) return null
  return (
    <span
      className={clsx('inline-flex items-center gap-1 whitespace-nowrap text-xs text-muted-foreground tabular-nums', className)}
      title={`${t('services.list.lastChecked')}: ${value}`}
    >
      {withIcon && <Clock className="h-3 w-3" aria-hidden="true" />}
      {t(`common.relative.${parts.key}`, { n: parts.n })}
    </span>
  )
}
