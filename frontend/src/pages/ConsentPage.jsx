import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Bot, ArrowLeft } from 'lucide-react'
import { oauthApi } from '../services/api'
import { useAuth } from '../contexts/AuthContext'
import AuthShell from '../components/AuthShell'
import { Button, Badge, CheckRow, Alert, Spinner, SectionLabel } from '../components/ui'

/**
 * OAuth 同意頁:/consent?rid=<authorization request id>
 * 後端 /oauth/authorize 把使用者導來這裡;決定後整頁跳回 client 的 redirect_uri。
 */
export default function ConsentPage() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const [searchParams] = useSearchParams()
  const rid = searchParams.get('rid')

  const [req, setReq] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState('')
  const [selected, setSelected] = useState(new Set())
  const [remember, setRemember] = useState(false)
  const [deciding, setDeciding] = useState(null)   // 'approve' | 'deny'

  useEffect(() => {
    if (!rid) {
      setError(t('consent.missingRid'))
      setIsLoading(false)
      return
    }
    let cancelled = false
    oauthApi.authorizeRequest.get(rid)
      .then((data) => {
        if (cancelled) return
        setReq(data)
        setSelected(new Set((data.scopes || []).map((s) => s.name)))
      })
      .catch((err) => { if (!cancelled) setError(err.message || t('consent.loadFailed')) })
      .finally(() => { if (!cancelled) setIsLoading(false) })
    return () => { cancelled = true }
  }, [rid, t])

  const toggleScope = (name) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  const decide = async (approve) => {
    setDeciding(approve ? 'approve' : 'deny')
    setError('')
    try {
      const result = await oauthApi.authorizeRequest.decide(rid, {
        approve,
        scopes: approve ? [...selected] : null,
        remember: approve && remember,
      })
      if (result?.redirect_to) {
        window.location.assign(result.redirect_to)
        return
      }
      setError(t('consent.noRedirect'))
    } catch (err) {
      setError(err.message || t('consent.decideFailed'))
    } finally {
      setDeciding(null)
    }
  }

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-canvas text-ink-subtle">
        <Spinner size="lg" />
      </div>
    )
  }

  if (!req) {
    return (
      <AuthShell maxWidth="max-w-md">
        <h2 className="text-lg font-semibold text-ink">{t('consent.errorTitle')}</h2>
        <Alert tone="danger" className="mt-4">{error || t('consent.loadFailed')}</Alert>
        <Button variant="secondary" icon={ArrowLeft} to="/" className="mt-5 w-full">
          {t('consent.backToDashboard')}
        </Button>
      </AuthShell>
    )
  }

  const client = req.client || {}
  const scopes = req.scopes || []
  const viaLabel = client.created_via === 'dcr'
    ? t('consent.viaDcr')
    : client.created_via === 'system' ? t('consent.viaSystem') : t('consent.viaManual')

  return (
    <AuthShell maxWidth="max-w-md">
      {/* Client */}
      <div className="flex items-start gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center overflow-hidden rounded-md border border-hairline bg-surface-muted text-ink-muted">
          {client.logo_uri ? (
            <img src={client.logo_uri} alt="" className="h-full w-full object-cover" />
          ) : (
            <Bot className="h-5 w-5" aria-hidden="true" />
          )}
        </span>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-tight text-ink">
            {t('consent.title', { name: client.client_name || client.client_id })}
          </h2>
          <p className="mt-1 text-sm text-ink-muted">{t('consent.subtitle', { email: user?.email || '' })}</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Badge tone={client.created_via === 'dcr' ? 'warning' : 'success'}>{viaLabel}</Badge>
            {client.client_uri && (
              <a
                href={client.client_uri}
                target="_blank"
                rel="noreferrer"
                className="max-w-[240px] truncate font-mono text-xs text-ink-muted transition-colors duration-150 hover:text-accent"
              >
                {client.client_uri}
              </a>
            )}
          </div>
        </div>
      </div>

      {error && <Alert tone="danger" className="mt-5">{error}</Alert>}

      {/* Target service / audience */}
      <div className="mt-5 rounded-md border border-hairline bg-surface-muted/50 px-3 py-2.5">
        <SectionLabel>{t('consent.targetService')}</SectionLabel>
        {req.service ? (
          <p className="mt-1 text-sm font-medium text-ink">{req.service.name}</p>
        ) : (
          <p className="mt-1 text-sm text-ink-muted">{req.resource ? t('consent.unknownService') : t('consent.noResource')}</p>
        )}
        {req.resource && (
          <p className="mt-0.5 break-all font-mono text-xs text-ink-muted">{req.resource}</p>
        )}
      </div>

      {/* Scopes */}
      <div className="mt-5">
        <SectionLabel className="mb-2">{t('consent.scopesTitle')}</SectionLabel>
        {scopes.length === 0 ? (
          <p className="text-sm text-ink-muted">{t('consent.noScopes')}</p>
        ) : (
          <div className="divide-y divide-hairline rounded-md border border-hairline">
            {scopes.map((s) => (
              <CheckRow
                key={s.name}
                className="px-3 py-2.5"
                checked={selected.has(s.name)}
                onChange={() => toggleScope(s.name)}
                label={<span className="font-mono text-xs">{s.name}</span>}
                description={s.description || t('consent.noDescription')}
              />
            ))}
          </div>
        )}
      </div>

      {/* Remember */}
      <CheckRow
        className="mt-5"
        checked={remember}
        onChange={(e) => setRemember(e.target.checked)}
        label={t('consent.remember')}
        description={t('consent.rememberHint')}
      />

      {/* Actions */}
      <div className="mt-6 flex gap-3">
        <Button
          variant="secondary"
          className="flex-1"
          onClick={() => decide(false)}
          disabled={!!deciding}
          loading={deciding === 'deny'}
        >
          {deciding === 'deny' ? t('consent.deciding') : t('consent.deny')}
        </Button>
        <Button
          variant="primary"
          className="flex-1"
          onClick={() => decide(true)}
          disabled={!!deciding}
          loading={deciding === 'approve'}
        >
          {deciding === 'approve' ? t('consent.deciding') : t('consent.approve')}
        </Button>
      </div>

      <div className="mt-5 flex flex-wrap items-center justify-between gap-2 border-t border-hairline pt-4 text-xs text-ink-muted">
        <span className="min-w-0 truncate">{t('consent.redirectTo', { host: req.redirect_host })}</span>
        {req.expires_at && (
          <span className="shrink-0 tabular-nums">
            {t('consent.expiresAt', { time: new Date(req.expires_at).toLocaleTimeString() })}
          </span>
        )}
      </div>
    </AuthShell>
  )
}
