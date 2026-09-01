import { useState, useEffect, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import useVisiblePolling from '../hooks/usePolling'
import {
  Store,
  Search,
  ExternalLink,
  Play,
  Square,
  Trash2,
  Download,
  Copy,
  Settings,
  Lock,
  Plus,
  Terminal,
  FileText,
  RefreshCw,
} from 'lucide-react'
import clsx from 'clsx'

import { marketplaceApi, managedApi, byoApi } from '../services/api'
import { BYO_COMMANDS, parseMcpConfigJson, buildAgentConfig } from '../utils/mcpConfig'
import { useToast } from '../contexts/ToastContext'
import { useConfirm } from '../contexts/ConfirmContext'
import {
  PageHeader, Button, IconButton, Badge, StatusPill, Card, EmptyState, Alert, LoadingBlock, Spinner,
  Field, Input, Textarea, SearchInput, Dialog, DialogBody, DialogFooter, DescriptionList,
} from '../components/ui'
import CodeBlock from '../components/CodeBlock'


// ---------- Install Modal ----------

function InstallModal({ stageText, entry, onClose, onInstalled }) {
  const { t } = useTranslation()
  const [formData, setFormData] = useState(() => {
    const init = { _name: entry.id, _port: '' }
    for (const ev of entry.env_vars) {
      init[ev.name] = ev.default || ''
    }
    return init
  })
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState('')
  const [fieldErrors, setFieldErrors] = useState({})

  const handleChange = (name, value) => {
    setFormData((prev) => ({ ...prev, [name]: value }))
    if (fieldErrors[name]) {
      setFieldErrors((prev) => ({ ...prev, [name]: '' }))
    }
  }

  const validate = () => {
    const errors = {}
    for (const ev of entry.env_vars) {
      const value = (formData[ev.name] || '').trim()
      if (ev.required && !value) {
        errors[ev.name] = t('marketplace.install.fieldRequired', { label: ev.label })
        continue
      }
      if (value && ev.pattern) {
        const re = new RegExp(ev.pattern)
        if (!re.test(value)) {
          errors[ev.name] = ev.error_message || t('marketplace.install.fieldInvalid', { label: ev.label })
        }
      }
    }
    return errors
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError('')
    const errs = validate()
    if (Object.keys(errs).length > 0) {
      setFieldErrors(errs)
      return
    }
    setFieldErrors({})
    setIsLoading(true)

    const envVars = {}
    for (const ev of entry.env_vars) {
      const v = (formData[ev.name] || '').trim()
      if (v) envVars[ev.name] = v
    }

    try {
      const result = await managedApi.install({
        catalogId: entry.id,
        name: formData._name || entry.id,
        envVars,
        port: formData._port ? parseInt(formData._port, 10) : null,
        autoStart: true,
      })
      onInstalled(result)
    } catch (err) {
      setError(err.message || t('marketplace.install.installFailed'))
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <Dialog
      open
      onClose={onClose}
      size="lg"
      title={t('marketplace.install.title', { name: entry.name })}
      description={entry.description}
    >
      <form onSubmit={handleSubmit} className="flex min-h-0 flex-1 flex-col">
        <DialogBody className="space-y-5">
          {error && <Alert tone="danger">{error}</Alert>}

          {entry.docs_url && (
            <a
              href={entry.docs_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-sm text-link transition-colors duration-200 hover:text-link-hover"
            >
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
              {t('marketplace.install.officialDocs')}
            </a>
          )}

          <div className="grid grid-cols-2 gap-5">
            <Field label={t('marketplace.install.instanceName')} help={t('marketplace.install.instanceNameHint')}>
              <Input
                type="text"
                value={formData._name}
                onChange={(e) => handleChange('_name', e.target.value)}
                placeholder={entry.id}
                pattern="[a-zA-Z0-9_\-]+"
                mono
              />
            </Field>
            <Field label={t('marketplace.install.portRequired')} help={t('marketplace.install.portHint')} required>
              <Input
                type="number"
                value={formData._port}
                onChange={(e) => handleChange('_port', e.target.value)}
                placeholder="3457"
                min={1024}
                max={65535}
                required
              />
            </Field>
          </div>

          {/* Dynamic env vars from catalog schema */}
          {entry.env_vars.map((ev) => (
            <Field
              key={ev.name}
              required={ev.required}
              help={ev.help}
              error={fieldErrors[ev.name]}
              label={
                <span className="inline-flex items-center gap-1.5">
                  {ev.label}
                  {ev.secret && <Lock className="h-3 w-3 text-subtle-foreground" aria-hidden="true" />}
                </span>
              }
            >
              <Input
                type={ev.secret ? 'password' : 'text'}
                value={formData[ev.name] || ''}
                onChange={(e) => handleChange(ev.name, e.target.value)}
                invalid={!!fieldErrors[ev.name]}
                placeholder={ev.secret ? '••••••••••' : ''}
                required={ev.required}
                mono
              />
            </Field>
          ))}
        </DialogBody>

        <DialogFooter>
          <Button type="button" variant="secondary" onClick={onClose}>
            {t('services.common.cancel')}
          </Button>
          <Button type="submit" variant="primary" icon={Download} loading={isLoading}>
            {isLoading ? (stageText || t('marketplace.install.submitting')) : t('marketplace.install.submit')}
          </Button>
        </DialogFooter>
      </form>
    </Dialog>
  )
}


// ---------- Connection Info Modal (after install success, or from Info button) ----------

function ConnectionInfoModal({ process, onClose }) {
  const { t } = useTranslation()
  const toast = useToast()
  const url = process.connection_url || ''
  // 與服務詳情頁同一個 builder → 兩處複製出來的格式一致(標準 mcpServers 包裝)。
  // Managed service 預設 requires_auth=false;若之後改成需驗證,詳情頁複製的版本會帶 Bearer 佔位符。
  const configJson = JSON.stringify(buildAgentConfig({ name: process.name, url }), null, 2)

  const copy = async (text) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(t('marketplace.connection.copied'))
    } catch {
      toast.error(t('marketplace.connection.copyFailed'))
    }
  }

  return (
    <Dialog open onClose={onClose} size="xl" title={t('marketplace.connection.title', { name: process.name })}>
      <DialogBody className="space-y-5">
        <Field label={t('marketplace.connection.connectionUrl')} help={t('marketplace.connection.connectionUrlHint')}>
          <div className="flex items-center gap-2">
            <code className="flex-1 break-all rounded-md border border-border bg-muted/50 px-3 py-2 font-mono text-xs text-foreground">
              {url}
            </code>
            <IconButton icon={Copy} title={t('services.detail.copy')} onClick={() => copy(url)} />
          </div>
        </Field>

        <Field label={t('marketplace.connection.agentConfigExample')}>
          <CodeBlock value={configJson} language="json" />
        </Field>

        <div className="rounded-md border border-border px-4 py-1">
          <p className="py-2 text-sm font-medium text-foreground">{t('marketplace.connection.statusLabel', { state: process.actual_state })}</p>
          <DescriptionList
            items={[
              { label: t('marketplace.connection.containerLabel'), value: process.container_id || '-', mono: true },
              { label: t('marketplace.connection.portLabel'), value: process.port || '-', mono: true },
            ]}
          />
        </div>
      </DialogBody>
      <DialogFooter>
        <Button variant="primary" onClick={onClose}>
          {t('marketplace.connection.done')}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}


// ---------- Catalog Card ----------

function StatusBadge({ state }) {
  const { t } = useTranslation()
  const conf = {
    running: { tone: 'success', label: t('marketplace.status.running') },
    stopped: { tone: 'neutral', label: t('marketplace.status.stopped') },
    starting: { tone: 'warning', pulse: true, label: t('marketplace.status.starting') },
    failed: { tone: 'danger', label: t('marketplace.status.failed') },
    unknown: { tone: 'neutral', label: t('marketplace.status.unknown') },
  }[state] || { tone: 'neutral', label: state }

  return (
    <StatusPill tone={conf.tone} pulse={!!conf.pulse}>
      {conf.label}
    </StatusPill>
  )
}

function CatalogCard({ entry, process, canInstall, canControl, canDelete,
                      onInstall, onInstallImage, onDeployCustom, onShowLogs, onStart, onStop,
                      onUninstall, onShowInfo, actionLoading, stageText }) {
  const { t } = useTranslation()
  const installed = !!process               // 已部署(process 存在)
  const isCustom = !!entry.isCustom         // 自訂(BYO)定義
  const imageInstalled = !!entry.image_installed  // 已安裝(image 已 load)
  const running = process?.actual_state === 'running'
  const busy = actionLoading === process?.id || actionLoading === entry.id

  return (
    <Card className="flex flex-col">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-border bg-card text-muted-foreground">
            {isCustom
              ? <Terminal className="h-4 w-4" aria-hidden="true" />
              : <Store className="h-4 w-4" aria-hidden="true" />}
          </span>
          <div className="min-w-0">
            <h3 className="truncate text-sm font-medium text-foreground">{entry.name}</h3>
            <p className="mt-0.5 text-xs capitalize text-muted-foreground">
              {isCustom ? t('marketplace.card.customBadge') : entry.category}
            </p>
          </div>
        </div>
        {installed && (
          busy
            ? <StatusBadge state="starting" />
            : <StatusBadge state={process?.actual_state} />
        )}
      </div>

      <p className="mb-3 line-clamp-2 text-xs text-muted-foreground">{entry.description}</p>

      <div className="mb-1 truncate font-mono text-xs text-subtle-foreground">
        {isCustom ? entry.description : `${entry.docker?.image}:${entry.docker?.tag}`}
      </div>

      {!installed && isCustom && (
        <div className="mb-4 text-xs text-muted-foreground">
          {t('marketplace.card.stateCustomNotDeployed')}
        </div>
      )}
      {!installed && !isCustom && (
        <div className="mb-4 text-xs">
          {imageInstalled ? (
            <Badge tone="accent">{t('marketplace.card.stateImageReady')}</Badge>
          ) : entry.image_tar_present ? (
            <span className="text-muted-foreground">{t('marketplace.card.stateNotInstalled')}</span>
          ) : (
            // 「尚未安裝」是待設定的正常狀態,不是錯誤 —— 不用紅字嚇人;
            // 技術細節(缺哪個檔、放哪裡)退到第二行,讓人知道下一步該做什麼。
            <span className="block text-muted-foreground">
              {t('marketplace.card.stateNotInstalled')}
              <span
                className="mt-0.5 block truncate font-mono text-2xs text-subtle-foreground"
                title={t('marketplace.card.tarMissingHint', { name: entry.image_tar_name })}
              >
                {t('marketplace.card.tarMissingHint', { name: entry.image_tar_name })}
              </span>
            </span>
          )}
        </div>
      )}
      {installed && <div className="mb-3" />}

      <div className="mt-auto flex items-center gap-1 border-t border-border pt-3">
        {/* 自訂:未部署 → [部署](直接跑 BYO deploy) */}
        {isCustom && !installed && !busy && (
          <Button variant="secondary" size="sm" icon={Play} onClick={() => onDeployCustom(entry)} disabled={!canInstall}>
            {t('marketplace.card.deploy')}
          </Button>
        )}

        {/* catalog 三態:未安裝(image 不在)→[安裝];已安裝未部署 →[部署];已部署 → 啟停 */}
        {!isCustom && !installed && !imageInstalled && !busy && (
          <Button
            variant="secondary"
            size="sm"
            icon={Download}
            onClick={() => onInstallImage(entry)}
            disabled={!canInstall || !entry.image_tar_present}
            title={!entry.image_tar_present
              ? t('marketplace.card.imageTarMissing', { name: entry.image_tar_name })
              : undefined}
          >
            {t('marketplace.card.installImage')}
          </Button>
        )}

        {!isCustom && !installed && imageInstalled && !busy && (
          <Button variant="secondary" size="sm" icon={Play} onClick={() => onInstall(entry)} disabled={!canInstall}>
            {t('marketplace.card.deploy')}
          </Button>
        )}

        {installed && running && !busy && (
          <>
            <Button variant="secondary" size="sm" icon={Settings} onClick={() => onShowInfo(process)}>
              {t('marketplace.card.connection')}
            </Button>
            <IconButton icon={Square} title={t('marketplace.card.stop')} onClick={() => onStop(process)} disabled={!canControl} />
          </>
        )}

        {installed && !running && !busy && (
          <Button variant="secondary" size="sm" icon={Play} onClick={() => onStart(process)} disabled={!canControl}>
            {t('marketplace.card.start')}
          </Button>
        )}

        {busy && (
          <span className="inline-flex h-8 items-center gap-2 px-1 text-xs text-muted-foreground">
            <Spinner size="xs" />
            <span>{stageText || t('marketplace.card.processing')}</span>
          </span>
        )}

        {installed && !busy && (
          <IconButton icon={FileText} title={t('marketplace.card.logsTitle')} onClick={() => onShowLogs(process)} />
        )}

        {installed && !busy && (
          <IconButton
            variant="destructive"
            icon={Trash2}
            title={t('marketplace.card.uninstallTitle')}
            onClick={() => onUninstall(process)}
            disabled={!canDelete}
            className="ml-auto"
          />
        )}

        {entry.docs_url && !installed && (
          <a
            href={entry.docs_url}
            target="_blank"
            rel="noopener noreferrer"
            className="ml-auto inline-flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
            title={t('marketplace.card.docsTitle')}
            aria-label={t('marketplace.card.docsTitle')}
          >
            <ExternalLink className="h-4 w-4" aria-hidden="true" />
          </a>
        )}
      </div>

      {process?.last_error && (
        <Alert tone="danger" className="mt-3 text-xs">{process.last_error}</Alert>
      )}
    </Card>
  )
}


// ---------- Main Page ----------

export default function MarketplacePage() {
  const { t } = useTranslation()
  const toast = useToast()
  const { confirmDelete } = useConfirm()

  const [catalog, setCatalog] = useState([])
  const [processes, setProcesses] = useState([])
  const [byoDefs, setByoDefs] = useState([])   // 自訂(BYO)定義
  const [isLoading, setIsLoading] = useState(true)
  const [loadError, setLoadError] = useState('')
  const [searchTerm, setSearchTerm] = useState('')

  const [installTarget, setInstallTarget] = useState(null)
  const [infoTarget, setInfoTarget] = useState(null)
  const [byoOpen, setByoOpen] = useState(false)
  const [byoDeployTarget, setByoDeployTarget] = useState(null)  // 重新部署時索取 env
  const [logsTarget, setLogsTarget] = useState(null)            // 檢視容器 log
  const [actionLoading, setActionLoading] = useState(null) // process.id 正在操作中
  const [progress, setProgress] = useState({})          // key → 進行中階段(輪詢 /api/managed/progress)

  // 單租戶:登入即管理員,所有操作皆可用
  const canInstall = true
  const canControl = true
  const canDelete = true
  const canByo = true

  const loadData = useCallback(async ({ silent = false } = {}) => {
    // silent:背景自動刷新,不顯示 loading 骨架、不清既有錯誤(避免畫面閃動)
    if (!silent) {
      setIsLoading(true)
      setLoadError('')
    }
    try {
      // allSettled: 一個 API 失敗不影響另一個(例如 managed 權限不足但 catalog 能讀)
      // BYO 定義載入失敗時靜默略過(市集本體仍可用)
      const [catalogResult, managedResult, byoResult] = await Promise.allSettled([
        marketplaceApi.list(),
        managedApi.list(),
        byoApi.list(),
      ])
      if (catalogResult.status === 'fulfilled') {
        setCatalog(catalogResult.value?.catalog || [])
      } else {
        setLoadError(catalogResult.reason?.message || t('marketplace.list.loadCatalogFailed'))
      }
      if (managedResult.status === 'fulfilled') {
        setProcesses(managedResult.value?.processes || [])
      }
      setByoDefs(byoResult.status === 'fulfilled' ? (byoResult.value?.definitions || []) : [])
      // managed list 失敗不 block 頁面(catalog 仍可看)
    } catch (err) {
      setLoadError(err.message || t('marketplace.list.loadFailed'))
    } finally {
      if (!silent) setIsLoading(false)
    }
  }, [t])

  useEffect(() => {
    loadData()
  }, [loadData])

  // 長操作進度:有操作進行中(或某個 process 正在 starting/stopping)時,每 1.5s 拉一次
  // 目前階段,把「等待 port」「暖機下載套件」等翻成文字給使用者看,而不是一顆轉圈。
  const hasTransitional = processes.some(
    (p) => p.actual_state === 'starting' || p.actual_state === 'stopping'
  )
  const progressActive = actionLoading !== null || hasTransitional || !!installTarget || !!byoDeployTarget
  const pollProgress = useCallback(async () => {
    try {
      const res = await managedApi.progress()
      const map = {}
      for (const item of res?.items || []) map[item.key] = item
      setProgress(map)
    } catch {
      // 進度是輔助資訊;拉不到不打擾使用者,主要結果仍由操作本身的回應決定
    }
  }, [])
  useVisiblePolling(pollProgress, 1500, progressActive)
  useEffect(() => {
    if (!progressActive) setProgress({})
  }, [progressActive])

  // 背景自動刷新(分頁可見時每 15s):別人部署、容器崩潰後自動重生等變化,
  // 不必使用者手動按 refresh 才看得到。進度輪詢中暫停,避免兩路請求互相干擾。
  useVisiblePolling(() => loadData({ silent: true }), 15000, !progressActive)

  const stageLabel = (item) => {
    if (!item) return null
    const base = t(`marketplace.progress.${item.stage}`, {
      defaultValue: t('marketplace.card.processing'),
    })
    return item.elapsed_seconds >= 5 ? `${base} · ${Math.round(item.elapsed_seconds)}s` : base
  }
  const stageTextFor = (entry, process) =>
    stageLabel((process && progress[`process:${process.id}`]) || progress[`catalog:${entry.id}`])
  // 部署對話框內 process id 尚未產生,取任一進行中的啟動作為顯示(同時間只會有一個)
  const activeStartStage = stageLabel(Object.values(progress).find((i) => i.kind === 'start'))

  const processForCatalog = (catalogId) =>
    processes.find((p) => p.catalog_id === catalogId)

  const handleInstalled = async (result) => {
    setInstallTarget(null)
    await loadData()
    if (result.success && result.process) {
      toast.success(result.message || t('marketplace.actions.installedSuccess'))
      setInfoTarget(result.process)
    } else {
      toast.error(result.message || t('marketplace.actions.installedFailed'))
    }
  }

  // 既有自訂定義的(重新)部署 —— 卡片上的「部署」按鈕。
  // 定義只存 env 的「鍵」(值不落地),因此重新部署必須重新索取值,
  // 否則會部署出一個沒有金鑰、看似 running 但不能用的服務。
  const handleDeployCustom = (entry) => {
    if ((entry.envSchema || []).length > 0) {
      setByoDeployTarget(entry)
      return
    }
    return runDeployCustom(entry, {})
  }

  const runDeployCustom = async (entry, envVars) => {
    setByoDeployTarget(null)
    setActionLoading(entry.id)
    try {
      const result = await byoApi.deploy(entry.definitionId, {
        env_vars: envVars, auto_start: true,
      })
      await loadData()
      if (result?.success) {
        toast.success(result.message || t('marketplace.byo.deployedSuccess'))
        if (result.process) setInfoTarget(result.process)
      } else {
        toast.error(result?.message || t('marketplace.byo.deployFailed'))
      }
    } catch (err) {
      toast.error(err.message || t('marketplace.byo.deployFailed'))
    } finally {
      setActionLoading(null)
    }
  }

  // BYO:建立定義 + 立即部署(容器化 supergateway → 127.0.0.1:port)
  const handleByoCreated = async (result) => {
    setByoOpen(false)
    await loadData()
    if (result?.success) {
      toast.success(result.message || t('marketplace.byo.deployedSuccess'))
      if (result.process) setInfoTarget(result.process)
    } else {
      toast.error(result?.message || t('marketplace.byo.deployFailed'))
    }
  }

  // 「安裝」= 後端 docker load image(離線兩階段第一步);以 entry.id 當 loading key
  const handleInstallImage = async (entry) => {
    setActionLoading(entry.id)
    try {
      const result = await marketplaceApi.installImage(entry.id)
      toast.success(result.message || t('marketplace.actions.imageInstalledSuccess', { name: entry.name }))
      await loadData()
    } catch (err) {
      toast.error(err.message || t('marketplace.actions.imageInstallFailed'))
    } finally {
      setActionLoading(null)
    }
  }

  const handleStart = async (process) => {
    setActionLoading(process.id)
    try {
      await managedApi.start(process.id)
      toast.success(t('marketplace.actions.startedSuccess', { name: process.name }))
      await loadData()
    } catch (err) {
      toast.error(err.message || t('marketplace.actions.startFailed'))
    } finally {
      setActionLoading(null)
    }
  }

  const handleStop = async (process) => {
    setActionLoading(process.id)
    try {
      await managedApi.stop(process.id)
      toast.success(t('marketplace.actions.stoppedSuccess', { name: process.name }))
      await loadData()
    } catch (err) {
      toast.error(err.message || t('marketplace.actions.stopFailed'))
    } finally {
      setActionLoading(null)
    }
  }

  const handleUninstall = async (process) => {
    const confirmed = await confirmDelete(t('marketplace.actions.uninstallConfirm', { name: process.name }))
    if (!confirmed) return
    setActionLoading(process.id)
    try {
      await managedApi.uninstall(process.id)
      toast.success(t('marketplace.actions.uninstalledSuccess', { name: process.name }))
      await loadData()
    } catch (err) {
      toast.error(err.message || t('marketplace.actions.uninstallFailed'))
    } finally {
      setActionLoading(null)
    }
  }

  // 自訂(BYO)定義也要出現在市集清單 —— 否則部署完會「憑空消失」,
  // 只能到 Services 頁才看得到。轉成與 catalog entry 相同形狀以共用卡片。
  const customEntries = byoDefs.map((d) => ({
    id: `user:${d.id}`,
    name: d.name,
    description: [d.command, ...(d.args || [])].join(' '),
    category: 'custom',
    isCustom: true,
    definitionId: d.id,
    envSchema: d.env_schema || [],
    docker: { image: d.command, tag: '' },
    // 自訂項目不走「安裝 image」階段(基底 image 是平台前置)
    image_installed: true,
    image_tar_present: true,
  }))

  const filtered = [...customEntries, ...catalog].filter((e) => {
    if (!searchTerm) return true
    const q = searchTerm.toLowerCase()
    return (
      e.name.toLowerCase().includes(q) ||
      e.description.toLowerCase().includes(q) ||
      e.category.toLowerCase().includes(q)
    )
  })

  return (
    <div className="space-y-8">
      <PageHeader
        title={t('marketplace.list.title')}
        description={t('marketplace.list.subtitle')}
        actions={canByo && (
          <Button variant="primary" icon={Plus} onClick={() => setByoOpen(true)}>
            {t('marketplace.byo.addButton')}
          </Button>
        )}
      />

      {/* Search */}
      <SearchInput
        icon={Search}
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
        placeholder={t('marketplace.list.searchPlaceholder')}
        className="max-w-md"
      />

      {loadError && <Alert tone="danger">{loadError}</Alert>}

      {isLoading ? (
        <LoadingBlock />
      ) : filtered.length === 0 ? (
        <Card padding="none">
          <EmptyState
            icon={Store}
            title={catalog.length === 0
              ? t('marketplace.list.emptyCatalog')
              : t('marketplace.list.emptySearch')}
          />
        </Card>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {filtered.map((entry) => (
            <CatalogCard
              key={entry.id}
              entry={entry}
              process={processForCatalog(entry.id)}
              canInstall={canInstall}
              canControl={canControl}
              canDelete={canDelete}
              onInstall={setInstallTarget}
              onInstallImage={handleInstallImage}
              onDeployCustom={handleDeployCustom}
              onShowLogs={setLogsTarget}
              onStart={handleStart}
              onStop={handleStop}
              onUninstall={handleUninstall}
              onShowInfo={setInfoTarget}
              actionLoading={actionLoading}
              stageText={stageTextFor(entry, processForCatalog(entry.id))}
            />
          ))}
        </div>
      )}

      {installTarget && (
        <InstallModal stageText={activeStartStage}
          entry={installTarget}
          onClose={() => setInstallTarget(null)}
          onInstalled={handleInstalled}
        />
      )}

      {infoTarget && (
        <ConnectionInfoModal
          process={infoTarget}
          onClose={() => setInfoTarget(null)}
        />
      )}

      {byoOpen && (
        <ByoModal stageText={activeStartStage}
          onClose={() => setByoOpen(false)}
          onDeployed={handleByoCreated}
        />
      )}

      {logsTarget && (
        <LogsModal process={logsTarget} onClose={() => setLogsTarget(null)} />
      )}

      {byoDeployTarget && (
        <ByoDeployModal stageText={activeStartStage}
          entry={byoDeployTarget}
          onClose={() => setByoDeployTarget(null)}
          onSubmit={(envVars) => runDeployCustom(byoDeployTarget, envVars)}
        />
      )}
    </div>
  )
}


// ---------- BYO(自帶啟動指令)Modal:貼 Claude 設定 JSON → 建立 + 部署 ----------
function ByoModal({ stageText, onClose, onDeployed }) {
  const { t } = useTranslation()
  const [pasteText, setPasteText] = useState('')
  // port 不在標準 MCP 設定 JSON 內,是唯一需要獨立輸入的項目(留空 = 自動分配)
  const [port, setPort] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')

  // JSON 本身即表單:command/args/env 都從貼上的內容解析,要改就直接改 JSON
  const parsed = pasteText.trim() ? parseMcpConfigJson(pasteText) : null
  const portNum = port ? Number(port) : null
  const portValid = !portNum || (portNum >= 1024 && portNum <= 65535)
  const commandOk = parsed ? BYO_COMMANDS.includes(parsed.command) : false
  const envEntries = parsed ? Object.entries(parsed.env) : []
  // 市集範例常留 "YOUR-KEY" 這類佔位值,原樣部署會起得來但不能用 → 事先提醒
  const placeholderKeys = envEntries
    .filter(([, v]) => /^(your|<|xxx+|changeme|replace|api[-_]?key$|token$)/i.test(String(v).trim()))
    .map(([k]) => k)
  const canDeploy = !!parsed && commandOk && !!parsed.name && portValid

  const handleSubmit = async () => {
    setError('')
    if (!canDeploy) return
    setSubmitting(true)
    try {
      const def = await byoApi.create({
        name: parsed.name,
        command: parsed.command,
        args: parsed.args,
        container_port: 8000,
        // env 的「鍵」進定義(schema);「值」於部署時傳入並加密儲存
        env_schema: envEntries.map(([k]) => ({ name: k, secret: true })),
      })
      const result = await byoApi.deploy(def.id, {
        env_vars: Object.fromEntries(envEntries.map(([k, v]) => [k, String(v)])),
        port: portNum,          // null → 後端自動分配
        auto_start: true,
      })
      onDeployed(result)
    } catch (err) {
      setError(err.message || t('marketplace.byo.deployFailed'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open onClose={onClose} size="2xl" title={t('marketplace.byo.title')} description={t('marketplace.byo.hint')}>
      <DialogBody className="space-y-4">
        <Textarea
          value={pasteText}
          onChange={(e) => { setPasteText(e.target.value); setError('') }}
          rows={12}
          mono
          className="text-xs"
          placeholder={'{\n  "mcpServers": {\n    "firecrawl-mcp": {\n      "command": "npx",\n      "args": ["-y", "firecrawl-mcp"],\n      "env": { "FIRECRAWL_API_KEY": "fc-xxxx" }\n    }\n  }\n}'}
        />

        {/* port:標準 MCP JSON 不含此項,故獨立輸入(留空自動分配) */}
        <div className="flex items-center gap-3">
          <label className="shrink-0 text-sm font-medium text-foreground">{t('marketplace.byo.port')}</label>
          <Input
            value={port}
            onChange={(e) => setPort(e.target.value.replace(/[^0-9]/g, ''))}
            className="w-32"
            invalid={!portValid}
            placeholder="auto"
            mono
          />
          <span className={clsx('text-xs', portValid ? 'text-muted-foreground' : 'text-danger')}>
            {portValid ? t('marketplace.byo.portHint') : t('marketplace.byo.portInvalid')}
          </span>
        </div>

        {/* 解析結果:確認實際會部署什麼 */}
        {pasteText.trim() && !parsed && (
          <p className="text-xs text-danger">{t('marketplace.byo.parseFailed')}</p>
        )}
        {parsed && (
          <div className="space-y-1 rounded-md border border-border bg-muted/40 p-3 text-xs">
            <div className="flex gap-2">
              <span className="shrink-0 text-muted-foreground">{t('marketplace.byo.name')}</span>
              <span className="truncate font-mono text-foreground">{parsed.name || '—'}</span>
            </div>
            <div className="flex gap-2">
              <span className="shrink-0 text-muted-foreground">{t('marketplace.byo.command')}</span>
              <span className={clsx('truncate font-mono', commandOk ? 'text-foreground' : 'text-danger')}>
                {[parsed.command, ...parsed.args].join(' ')}
              </span>
            </div>
            {envEntries.length > 0 && (
              <div className="flex gap-2">
                <span className="shrink-0 text-muted-foreground">{t('marketplace.byo.env')}</span>
                <span className="truncate font-mono text-foreground">
                  {envEntries.map(([k]) => k).join(', ')}
                </span>
              </div>
            )}
            <div className="flex gap-2">
              <span className="shrink-0 text-muted-foreground">{t('marketplace.byo.endpoint')}</span>
              <span className="truncate font-mono text-foreground">
                127.0.0.1:{portNum || t('marketplace.byo.portAuto')}/sse
              </span>
            </div>
            {!commandOk && (
              <p className="pt-1 text-danger">
                {t('marketplace.byo.unsupportedCommand', {
                  command: parsed.command, allowed: BYO_COMMANDS.join(', '),
                })}
              </p>
            )}
            {parsed.extraCount > 0 && (
              <p className="pt-1 text-info">
                {t('marketplace.byo.multipleServers', { name: parsed.name, n: parsed.extraCount })}
              </p>
            )}
            {placeholderKeys.length > 0 && (
              <p className="pt-1 text-warning">
                {t('marketplace.byo.placeholderWarning', { keys: placeholderKeys.join(', ') })}
              </p>
            )}
          </div>
        )}

        {error && <Alert tone="danger">{error}</Alert>}
      </DialogBody>

      <DialogFooter>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button variant="primary" onClick={handleSubmit} loading={submitting} disabled={!canDeploy}>
          {submitting ? (stageText || t('marketplace.byo.deploying')) : t('marketplace.byo.deploy')}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}


// ---------- 重新部署自訂 MCP:索取 env 值 ----------
// 定義只保存 env 的「鍵」(schema),值不落地。重新部署時必須重新輸入,
// 否則會部署出一個沒有金鑰、狀態看似 running 但實際不可用的服務。
function ByoDeployModal({ stageText, entry, onClose, onSubmit }) {
  const { t } = useTranslation()
  const schema = entry.envSchema || []
  const [values, setValues] = useState(() =>
    Object.fromEntries(schema.map((e) => [e.name, '']))
  )
  const [submitting, setSubmitting] = useState(false)

  const missingRequired = schema.some((e) => e.required !== false && !values[e.name]?.trim())

  return (
    <Dialog open onClose={onClose} size="lg" title={t('marketplace.byo.redeployTitle', { name: entry.name })} description={t('marketplace.byo.redeployHint')}>
      <DialogBody className="space-y-4">
        <div className="truncate font-mono text-xs text-subtle-foreground">{entry.description}</div>

        {schema.map((e) => (
          <Field
            key={e.name}
            required={e.required !== false}
            help={e.help}
            label={
              <span className="inline-flex items-center gap-1.5 font-mono">
                {e.name}
                {e.secret && <Lock className="h-3 w-3 text-subtle-foreground" aria-hidden="true" />}
              </span>
            }
          >
            <Input
              type={e.secret ? 'password' : 'text'}
              value={values[e.name] || ''}
              onChange={(ev) => setValues((p) => ({ ...p, [e.name]: ev.target.value }))}
              placeholder={e.secret ? '••••••••••' : ''}
              mono
            />
          </Field>
        ))}
      </DialogBody>

      <DialogFooter>
        <Button variant="secondary" onClick={onClose}>{t('common.cancel')}</Button>
        <Button
          variant="primary"
          onClick={() => { setSubmitting(true); onSubmit(values) }}
          loading={submitting}
          disabled={missingRequired}
        >
          {submitting ? (stageText || t('marketplace.byo.deploying')) : t('marketplace.card.deploy')}
        </Button>
      </DialogFooter>
    </Dialog>
  )
}


// ---------- 容器 Log 檢視 ----------
// 容器崩潰或啟動失敗時,死因只在它自己的輸出裡。BYO 不用 --rm,
// 因此即使已退出也還撈得到(見 Orchestrator.container_logs)。
function LogsModal({ process, onClose }) {
  const { t } = useTranslation()
  const [logs, setLogs] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const r = await managedApi.logs(process.id, 400)
      setLogs(r.logs || '')
    } catch (err) {
      setError(err.message || 'Failed to load logs')
    } finally {
      setLoading(false)
    }
  }, [process.id])

  useEffect(() => { load() }, [load])

  return (
    <Dialog open onClose={onClose} size="2xl" panelClassName="max-w-4xl" title={t('marketplace.card.logsTitleFor', { name: process.name })}>
      <DialogBody className="space-y-3">
        {error && <Alert tone="danger">{error}</Alert>}

        <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-all rounded-md border border-border bg-muted/50 p-3 font-mono text-xs leading-relaxed text-foreground">
          {loading && !logs ? t('common.loading') : (logs || t('marketplace.card.logsEmpty'))}
        </pre>
      </DialogBody>
      <DialogFooter between>
        <Button variant="secondary" size="sm" icon={RefreshCw} onClick={load} loading={loading}>
          {loading ? t('common.loading') : t('services.common.refresh')}
        </Button>
        <Button variant="primary" onClick={onClose}>{t('services.common.close')}</Button>
      </DialogFooter>
    </Dialog>
  )
}
