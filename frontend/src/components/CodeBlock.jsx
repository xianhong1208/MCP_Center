import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Copy, Check } from 'lucide-react'
import clsx from 'clsx'
import { copyToClipboard } from '../utils/clipboard'
import { useToast } from '../contexts/ToastContext'
import IconButton from './ui/IconButton'

/**
 * 可複製的程式碼 / 指令區塊。
 * value 可為字串或物件(物件會 JSON.stringify(…, 2))。
 */
export default function CodeBlock({ title, value, language, className, rows, sensitive = false }) {
  const { t } = useTranslation()
  const toast = useToast()
  const [copied, setCopied] = useState(false)
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)

  const handleCopy = async () => {
    try {
      await copyToClipboard(text)
      setCopied(true)
      toast.success(t('components.code.copied'))
      setTimeout(() => setCopied(false), 2000)
    } catch {
      toast.error(t('components.code.copyFailed'))
    }
  }

  const copyButton = (
    <IconButton
      size="sm"
      icon={copied ? Check : Copy}
      onClick={handleCopy}
      title={t('components.code.copy')}
      className={clsx(copied && 'text-emerald-600 dark:text-emerald-400')}
    />
  )

  return (
    <div className={clsx('overflow-hidden rounded-md border border-hairline bg-surface-muted/50', className)}>
      {(title || language) && (
        <div className="flex h-9 items-center justify-between border-b border-hairline px-3">
          <span className="truncate text-xs font-medium text-ink-muted">{title}</span>
          <div className="flex items-center gap-2">
            {language && <span className="font-mono text-2xs uppercase tracking-wide text-ink-subtle">{language}</span>}
            {copyButton}
          </div>
        </div>
      )}
      <div className="relative">
        <pre
          className={clsx(
            'overflow-x-auto whitespace-pre px-3 py-2.5 font-mono text-xs leading-relaxed text-ink',
            sensitive && 'whitespace-pre-wrap break-all',
          )}
          style={rows ? { maxHeight: `${rows * 1.6}rem`, overflowY: 'auto' } : undefined}
        >
          {text}
        </pre>
        {!title && !language && (
          <div className="absolute right-1.5 top-1.5">{copyButton}</div>
        )}
      </div>
    </div>
  )
}
