import { useState, useEffect, useRef, useLayoutEffect } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search, Key, Server, Bot, X } from 'lucide-react'
import { createPortal } from 'react-dom'
import clsx from 'clsx'
import { oauthApi, servicesApi } from '../services/api'
import { Kbd, Spinner } from './ui'

const EMPTY = { tokens: [], services: [], clients: [] }
const PANEL_WIDTH = 520
const PANEL_GAP = 6

/**
 * 側欄搜尋:直接在側欄的輸入框打字,結果以下拉清單貼在輸入框正下方、向右延伸
 * (不是置中彈窗、沒有全螢幕遮罩)。Ctrl/⌘+K 聚焦輸入框,Esc 關閉,換頁自動關閉。
 *
 * 下拉清單用 portal 掛到 body 並依輸入框的 bounding rect 定位:側欄有 transform
 * (抽屜動畫),裡面的 fixed/absolute 元素會被關在側欄寬度內,所以不能直接放在側欄裡。
 */
export default function GlobalSearch() {
  const { t } = useTranslation()
  const [query, setQuery] = useState('')
  const [isFocused, setIsFocused] = useState(false)
  const [results, setResults] = useState(EMPTY)
  const [isLoading, setIsLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [rect, setRect] = useState(null)
  const inputRef = useRef(null)
  const panelRef = useRef(null)
  const navigate = useNavigate()
  const location = useLocation()

  const isOpen = isFocused && query.trim().length > 0

  // ⌘K / Ctrl+K:聚焦輸入框;Esc:清空並失焦
  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
        inputRef.current?.select()
      }
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // 換頁時關閉
  useEffect(() => {
    setQuery('')
    setIsFocused(false)
  }, [location.pathname])

  // 點到輸入框與清單以外的地方 → 關閉
  useEffect(() => {
    if (!isOpen) return
    const onPointerDown = (e) => {
      if (inputRef.current?.parentElement?.contains(e.target)) return
      if (panelRef.current?.contains(e.target)) return
      setIsFocused(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [isOpen])

  // 依輸入框位置放清單;視窗縮放 / 捲動時跟著更新
  useLayoutEffect(() => {
    if (!isOpen) return
    const update = () => {
      const el = inputRef.current?.parentElement
      if (el) setRect(el.getBoundingClientRect())
    }
    update()
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [isOpen])

  useEffect(() => {
    if (!query.trim()) {
      setResults(EMPTY)
      return
    }
    const timer = setTimeout(async () => {
      setIsLoading(true)
      try {
        const [tokensRes, servicesRes, clientsRes] = await Promise.all([
          oauthApi.tokens.list({ includeInactive: true }).catch(() => ({ tokens: [] })),
          servicesApi.getAll().catch(() => ({ services: [] })),
          oauthApi.clients.list('all').catch(() => ({ clients: [] })),
        ])
        const q = query.toLowerCase()
        const tokens = (tokensRes.tokens || [])
          .filter((tk) =>
            tk.jti?.toLowerCase().includes(q) ||
            tk.label?.toLowerCase().includes(q) ||
            tk.service_name?.toLowerCase().includes(q) ||
            tk.client_name?.toLowerCase().includes(q))
          .slice(0, 5)
        const services = (servicesRes.services || [])
          .filter((s) =>
            s.name?.toLowerCase().includes(q) ||
            s.description?.toLowerCase().includes(q) ||
            s.effective_audience?.toLowerCase().includes(q))
          .slice(0, 5)
        const clients = (clientsRes.clients || [])
          .filter((c) =>
            c.client_name?.toLowerCase().includes(q) ||
            c.client_id?.toLowerCase().includes(q))
          .slice(0, 5)
        setResults({ tokens, services, clients })
        setSelectedIndex(0)
      } catch (err) {
        console.error('Search failed:', err)
      } finally {
        setIsLoading(false)
      }
    }, 300)
    return () => clearTimeout(timer)
  }, [query])

  const allResults = [
    ...results.tokens.map((tk) => ({ type: 'token', key: tk.jti, data: tk })),
    ...results.services.map((s) => ({ type: 'service', key: s.id, data: s })),
    ...results.clients.map((c) => ({ type: 'client', key: c.client_id, data: c })),
  ]
  const totalResults = allResults.length

  const handleSelect = (item) => {
    setQuery('')
    setIsFocused(false)
    inputRef.current?.blur()
    switch (item.type) {
      case 'token': navigate(`/tokens/${encodeURIComponent(item.key)}`); break
      case 'service': navigate(`/services/${encodeURIComponent(item.key)}`); break
      case 'client': navigate('/clients'); break
      default: break
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      setQuery('')
      setIsFocused(false)
      inputRef.current?.blur()
    } else if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((i) => Math.min(i + 1, Math.max(allResults.length - 1, 0)))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && allResults[selectedIndex]) {
      e.preventDefault()
      handleSelect(allResults[selectedIndex])
    }
  }

  const groups = [
    { key: 'tokens', label: t('components.search.tokens'), icon: Key,
      items: results.tokens, offset: 0,
      render: (tk) => [tk.label || tk.jti, `${tk.kind} · ${tk.service_name || tk.audience || ''} · ${tk.status}`] },
    { key: 'services', label: t('components.search.services'), icon: Server,
      items: results.services, offset: results.tokens.length,
      render: (s) => [s.name, s.description || s.effective_audience || t('components.search.noDescription')] },
    { key: 'clients', label: t('components.search.clients'), icon: Bot,
      items: results.clients, offset: results.tokens.length + results.services.length,
      render: (c) => [c.client_name, `${c.client_id} · ${c.created_via}`] },
  ]

  // 清單位置:貼在輸入框下方、左緣對齊;寬度固定但不超出視窗
  const panelStyle = rect
    ? {
        position: 'fixed',
        top: rect.bottom + PANEL_GAP,
        left: Math.max(8, Math.min(rect.left, window.innerWidth - PANEL_WIDTH - 8)),
        width: Math.min(PANEL_WIDTH, window.innerWidth - 16),
        maxHeight: `calc(100vh - ${rect.bottom + PANEL_GAP + 16}px)`,
      }
    : null

  const panel = isOpen && panelStyle && (
    <div
      ref={panelRef}
      role="listbox"
      style={panelStyle}
      className="z-50 flex flex-col overflow-hidden rounded-lg border border-border bg-popover shadow-overlay animate-fade-in"
    >
      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex justify-center py-8 text-subtle-foreground"><Spinner size="sm" /></div>
        ) : totalResults === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-muted-foreground">{t('components.search.noResults', { q: query })}</p>
        ) : (
          <div className="py-1.5">
            {groups.filter((g) => g.items.length > 0).map((g) => (
              <div key={g.key}>
                <div className="px-3 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{g.label}</div>
                {g.items.map((item, i) => {
                  const [line1, line2] = g.render(item)
                  const idx = g.offset + i
                  const active = selectedIndex === idx
                  return (
                    <button
                      key={allResults[idx].key}
                      type="button"
                      role="option"
                      aria-selected={active}
                      onMouseDown={(e) => e.preventDefault()}
                      onClick={() => handleSelect(allResults[idx])}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={clsx(
                        'flex h-9 w-full cursor-pointer items-center gap-2.5 px-3 text-left transition-colors duration-200',
                        active ? 'bg-muted' : 'hover:bg-muted/60',
                      )}
                    >
                      <g.icon className="h-4 w-4 shrink-0 text-subtle-foreground" aria-hidden="true" />
                      <span className="max-w-[50%] shrink-0 truncate text-sm font-medium text-foreground">{line1}</span>
                      <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground" title={line2}>{line2}</span>
                    </button>
                  )
                })}
              </div>
            ))}
          </div>
        )}
      </div>
      <div className="flex h-8 items-center justify-between border-t border-border px-3 text-xs text-subtle-foreground">
        <span className="flex items-center gap-1.5">
          <Kbd>↑</Kbd><Kbd>↓</Kbd> {t('components.search.navigate')}
          <span className="mx-1 opacity-40">·</span>
          <Kbd>↵</Kbd> {t('components.search.select')}
        </span>
        <span className="tabular-nums">
          {t(totalResults === 1 ? 'components.search.resultsSingular' : 'components.search.resultsPlural', { n: totalResults })}
        </span>
      </div>
    </div>
  )

  return (
    <>
      <div
        className={clsx(
          'flex h-9 w-full items-center gap-2 rounded-md border bg-card pl-3 pr-2 text-sm transition-colors duration-200',
          isFocused ? 'border-accent ring-2 ring-accent/30' : 'border-border hover:border-border-strong',
        )}
      >
        <Search className="h-4 w-4 shrink-0 text-subtle-foreground" aria-hidden="true" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => setIsFocused(true)}
          onKeyDown={handleKeyDown}
          role="combobox"
          aria-expanded={isOpen}
          aria-autocomplete="list"
          aria-label={t('components.search.placeholderInput')}
          className="h-full min-w-0 flex-1 bg-transparent text-foreground outline-none placeholder:text-subtle-foreground"
          placeholder={t('components.search.placeholderTrigger')}
        />
        {query ? (
          <button
            type="button"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => { setQuery(''); inputRef.current?.focus() }}
            className="flex h-6 w-6 shrink-0 cursor-pointer items-center justify-center rounded text-subtle-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
            aria-label="Clear"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        ) : (
          <Kbd className="hidden shrink-0 border-transparent bg-muted sm:inline-flex">⌘K</Kbd>
        )}
      </div>
      {panel ? createPortal(panel, document.body) : null}
    </>
  )
}
