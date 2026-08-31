import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Ban, Clock } from 'lucide-react'
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts'
import { oauthApi, statsApi } from '../services/api'
import { useConfirm } from '../contexts/ConfirmContext'
import { useToast } from '../contexts/ToastContext'
import LastChecked from '../components/LastChecked'
import { KindBadge, StatusBadge } from './TokensPage'
import {
  PageHeader, Button, Badge, Card, CardHeader, Alert, EmptyState, LoadingBlock, StatusDot, DescriptionList,
} from '../components/ui'

// recharts 需要實際色值:indigo-500 / rose-500
const CHART = { success: '#6366f1', failed: '#f43f5e' }

function ChartTooltip({ active, payload, label }) {
  const { t } = useTranslation()
  if (!active || !payload || !payload.length) return null
  const success = payload.find((p) => p.dataKey === 'success')?.value || 0
  const failed = payload.find((p) => p.dataKey === 'failed')?.value || 0
  return (
    <div className="min-w-[10rem] rounded-md border border-hairline bg-surface-elevated p-3 text-xs shadow-overlay">
      <p className="mb-2 font-medium text-ink">{label}</p>
      <div className="flex items-center justify-between gap-4"><span className="flex items-center gap-1.5 text-ink-muted"><StatusDot tone="accent" />{t('tokens.detail.chartSuccess')}</span><span className="tabular-nums text-ink">{success}</span></div>
      <div className="mt-1 flex items-center justify-between gap-4"><span className="flex items-center gap-1.5 text-ink-muted"><StatusDot tone="danger" />{t('tokens.detail.chartFailed')}</span><span className="tabular-nums text-ink">{failed}</span></div>
      <div className="mt-2 flex items-center justify-between gap-4 border-t border-hairline pt-1.5"><span className="text-ink-muted">{t('tokens.detail.total')}</span><span className="tabular-nums font-medium text-ink">{success + failed}</span></div>
    </div>
  )
}

export default function TokenDetailPage() {
  const { t } = useTranslation()
  const { jti } = useParams()
  const { confirmRevoke } = useConfirm()
  const toast = useToast()
  const decodedJti = decodeURIComponent(jti)

  const [token, setToken] = useState(null)
  const [usageStats, setUsageStats] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isLoadingStats, setIsLoadingStats] = useState(false)
  const [isRevoking, setIsRevoking] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    setIsLoading(true)
    setError(null)
    oauthApi.tokens.get(decodedJti)
      .then((data) => { if (!cancelled) setToken(data) })
      .catch((err) => { if (!cancelled) setError(err.message || t('tokens.detail.loadFail')) })
      .finally(() => { if (!cancelled) setIsLoading(false) })
    return () => { cancelled = true }
  }, [decodedJti, t])

  // 統計以服務為單位(token 事件流不分 jti)
  useEffect(() => {
    if (!token?.service_id) return
    let cancelled = false
    setIsLoadingStats(true)
    statsApi.daily(30, token.service_id)
      .then((res) => { if (!cancelled) setUsageStats(res.stats || []) })
      .catch(() => {})
      .finally(() => { if (!cancelled) setIsLoadingStats(false) })
    return () => { cancelled = true }
  }, [token?.service_id])

  const handleRevoke = async () => {
    if (!token) return
    const confirmed = await confirmRevoke(token.label ? `"${token.label}"` : `${token.kind} ${token.jti.slice(0, 8)}…`)
    if (!confirmed) return
    setIsRevoking(true)
    try {
      const updated = await oauthApi.tokens.revoke(token.jti)
      setToken(updated)
      toast.success(t('tokens.detail.revokeSuccess'))
    } catch (err) {
      toast.error(t('tokens.detail.revokeFail', { message: err.message }))
    } finally {
      setIsRevoking(false)
    }
  }

  if (isLoading) {
    return <LoadingBlock className="min-h-[400px]" />
  }

  if (error || !token) {
    return (
      <div className="space-y-8">
        <PageHeader title={t('tokens.detail.title')} backTo="/tokens" backLabel={t('tokens.detail.backToTokens')} />
        <Alert tone="danger">{error || t('tokens.detail.loadFail')}</Alert>
      </div>
    )
  }

  const totalSuccess = usageStats.reduce((s, x) => s + (x.success || 0), 0)
  const totalFailed = usageStats.reduce((s, x) => s + (x.failed || 0), 0)
  const totalUsage = totalSuccess + totalFailed

  const identityItems = [
    {
      label: t('tokens.detail.client'),
      value: (
        <>
          <span className="block">{token.client_name || '—'}</span>
          <span className="block font-mono text-xs text-ink-muted">{token.client_id}</span>
        </>
      ),
    },
    {
      label: t('tokens.detail.service'),
      value: token.service_id ? (
        <Link to={`/services/${encodeURIComponent(token.service_id)}`} className="text-accent transition-colors duration-150 hover:text-accent-hover">
          {token.service_name || token.service_id}
        </Link>
      ) : '—',
    },
    { label: t('tokens.detail.audience'), value: token.audience || '—', mono: true },
    {
      label: t('tokens.detail.subject'),
      value: (
        <>
          <span className="block font-mono text-xs">{token.sub}</span>
          {token.user_email && <span className="block text-xs text-ink-muted">{token.user_email}</span>}
        </>
      ),
    },
    {
      label: t('tokens.detail.scopes'),
      value: token.scopes && token.scopes.length > 0 ? (
        <span className="flex flex-wrap justify-end gap-1">
          {token.scopes.map((s) => <Badge key={s} tone="neutral" mono>{s}</Badge>)}
        </span>
      ) : <span className="text-ink-muted">{t('tokens.detail.noScopes')}</span>,
    },
  ]

  const lifecycleItems = [
    { label: t('tokens.detail.issuedAt'), value: token.issued_at || '—', mono: true },
    { label: t('tokens.detail.expiresAt'), value: token.expires_at || t('tokens.common.never'), mono: true },
    {
      label: t('tokens.detail.lastUsed'),
      value: token.last_used_at ? (
        <>
          <LastChecked value={token.last_used_at} className="justify-end text-ink" />
          <span className="block font-mono text-xs text-ink-muted">{token.last_used_at}{token.last_used_ip ? ` · ${token.last_used_ip}` : ''}</span>
        </>
      ) : <span className="text-ink-muted">{t('tokens.common.neverUsed')}</span>,
    },
    { label: t('tokens.detail.useCount'), value: <span className="tabular-nums">{token.use_count ?? 0}</span> },
  ]

  return (
    <div className="space-y-8">
      <PageHeader
        title={token.label || t('tokens.detail.title')}
        description={<span className="font-mono text-xs">{token.jti}</span>}
        backTo="/tokens"
        backLabel={t('tokens.detail.backToTokens')}
        meta={<><KindBadge kind={token.kind} /><StatusBadge status={token.status} /></>}
        actions={token.status === 'active' && (
          <Button variant="destructive" icon={Ban} onClick={handleRevoke} loading={isRevoking}>
            {isRevoking ? t('tokens.detail.revoking') : t('tokens.detail.revoke')}
          </Button>
        )}
      />

      {token.status === 'revoked' && (
        <Alert tone="neutral" icon={Ban}>
          {t('tokens.detail.revokedNotice', { at: token.revoked_at || '', reason: token.revoke_reason || '—' })}
        </Alert>
      )}

      {/* Fields */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title={t('tokens.detail.client')} />
          <DescriptionList items={identityItems} />
        </Card>
        <Card>
          <CardHeader title={t('tokens.detail.issuedAt')} />
          <DescriptionList items={lifecycleItems} />
        </Card>
      </div>

      {/* Usage chart (per service) */}
      <Card>
        <CardHeader
          title={t('tokens.detail.usageTitle')}
          description={token.service_name ? t('tokens.detail.usageSubtitle', { service: token.service_name }) : t('tokens.detail.usageNoService')}
          action={
            <dl className="flex items-center divide-x divide-hairline text-xs">
              <div className="pr-4 text-right"><dd className="text-lg font-semibold tabular-nums text-ink">{totalUsage}</dd><dt className="text-ink-muted">{t('tokens.detail.total')}</dt></div>
              <div className="px-4 text-right"><dd className="flex items-center justify-end gap-1.5 text-lg font-semibold tabular-nums text-ink"><StatusDot tone="accent" />{totalSuccess}</dd><dt className="text-ink-muted">{t('tokens.detail.success')}</dt></div>
              <div className="pl-4 text-right"><dd className="flex items-center justify-end gap-1.5 text-lg font-semibold tabular-nums text-ink"><StatusDot tone="danger" />{totalFailed}</dd><dt className="text-ink-muted">{t('tokens.detail.failed')}</dt></div>
            </dl>
          }
        />

        {isLoadingStats ? (
          <LoadingBlock className="h-64 py-0" />
        ) : totalUsage === 0 ? (
          <EmptyState className="h-64 py-0" icon={Clock} title={t('tokens.detail.noUsage')} description={t('tokens.detail.noUsageHint')} />
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={usageStats} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid vertical={false} strokeDasharray="0" />
                <XAxis dataKey="date" fontSize={11} tickLine={false} axisLine={false} tickMargin={8}
                  tickFormatter={(v) => { const d = new Date(v); return `${d.getMonth() + 1}/${d.getDate()}` }} />
                <YAxis fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} tickMargin={4} />
                <Tooltip content={<ChartTooltip />} cursor={{ strokeWidth: 1 }} />
                <Line type="monotone" dataKey="success" stroke={CHART.success} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} name={t('tokens.detail.chartSuccess')} />
                <Line type="monotone" dataKey="failed" stroke={CHART.failed} strokeWidth={2} dot={false} activeDot={{ r: 4, strokeWidth: 0 }} name={t('tokens.detail.chartFailed')} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
      </Card>
    </div>
  )
}
