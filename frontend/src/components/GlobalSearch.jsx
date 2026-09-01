import { useState, useEffect, useRef } from 'react'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Search, Key, Server, Bot, X } from 'lucide-react'
import { oauthApi, servicesApi } from '../services/api'
import clsx from 'clsx'
import { Kbd, Spinner, EmptyState } from './ui'

const EMPTY = { tokens: [], services: [], clients: [] }

/** Ctrl/Cmd+K 全站搜尋:服務、token、OAuth client */
export default function GlobalSearch() {
  const { t } = useTranslation()
  const [isOpen, setIsOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState(EMPTY)
  const [isLoading, setIsLoading] = useState(false)
  const [selectedIndex, setSelectedIndex] = useState(0)
  const inputRef = useRef(null)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsOpen(true)
      }
      if (e.key === 'Escape') setIsOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [])

  // 換頁時關閉
  useEffect(() => {
    setIsOpen(false)
    setQuery('')
  }, [location.pathname])

  useEffect(() => {
    if (isOpen && inputRef.current) inputRef.current.focus()
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

  const handleSelect = (item) => {
    setIsOpen(false)
    setQuery('')
    switch (item.type) {
      case 'token': navigate(`/tokens/${encodeURIComponent(item.key)}`); break
      case 'service': navigate(`/services/${encodeURIComponent(item.key)}`); break
      case 'client': navigate('/clients'); break
      default: break
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setSelectedIndex((i) => Math.min(i + 1, allResults.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setSelectedIndex((i) => Math.max(i - 1, 0))
    } else if (e.key === 'Enter' && allResults[selectedIndex]) {
      e.preventDefault()
      handleSelect(allResults[selectedIndex])
    }
  }

  const totalResults = allResults.length

  const trigger = (
    <button
      type="button"
      onClick={() => setIsOpen(true)}
      className={clsx(
        'flex h-8 w-full items-center gap-2 rounded-md border border-border bg-card px-2.5 text-left text-sm text-subtle-foreground',
        'transition-colors duration-200 hover:border-border-strong hover:text-muted-foreground',
      )}
    >
      <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="flex-1 truncate">{t('components.search.placeholderTrigger')}</span>
      <Kbd className="hidden sm:inline-flex">⌘K</Kbd>
    </button>
  )

  if (!isOpen) return trigger

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

  return (
    <>
      {trigger}
      <div className="fixed inset-0 z-50" role="dialog" aria-modal="true">
        <div
          className="absolute inset-0 bg-black/60 animate-fade-in"
          onClick={() => setIsOpen(false)}
          aria-hidden="true"
        />
        <div className="relative mx-auto mt-[12vh] max-w-xl px-4">
          <div className="overflow-hidden rounded-lg border border-border bg-popover shadow-overlay animate-dialog-in">
            <div className="flex h-12 items-center gap-3 border-b border-border px-4">
              <Search className="h-4 w-4 shrink-0 text-subtle-foreground" aria-hidden="true" />
              <input
                ref={inputRef}
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={handleKeyDown}
                className="h-full flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-subtle-foreground"
                placeholder={t('components.search.placeholderInput')}
              />
              {query && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="flex h-6 w-6 items-center justify-center rounded text-subtle-foreground transition-colors duration-200 hover:bg-muted hover:text-foreground"
                  aria-label="Clear"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
              <Kbd>Esc</Kbd>
            </div>

            <div className="max-h-[50vh] overflow-y-auto">
              {isLoading ? (
                <div className="flex justify-center py-10 text-subtle-foreground"><Spinner size="sm" /></div>
              ) : query && totalResults === 0 ? (
                <EmptyState compact icon={Search} title={t('components.search.noResults', { q: query })} />
              ) : query ? (
                <div className="py-2">
                  {groups.filter((g) => g.items.length > 0).map((g) => (
                    <div key={g.key}>
                      <div className="px-4 pb-1 pt-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">{g.label}</div>
                      {g.items.map((item, i) => {
                        const [line1, line2] = g.render(item)
                        const idx = g.offset + i
                        const active = selectedIndex === idx
                        return (
                          <button
                            key={allResults[idx].key}
                            type="button"
                            onClick={() => handleSelect(allResults[idx])}
                            onMouseEnter={() => setSelectedIndex(idx)}
                            className={clsx(
                              'flex w-full items-center gap-3 px-4 py-2 text-left transition-colors duration-200',
                              active ? 'bg-muted' : 'hover:bg-muted/60',
                            )}
                          >
                            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md border border-border bg-card text-muted-foreground">
                              <g.icon className="h-3.5 w-3.5" aria-hidden="true" />
                            </span>
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-medium text-foreground">{line1}</span>
                              <span className="block truncate text-xs text-muted-foreground">{line2}</span>
                            </span>
                          </button>
                        )
                      })}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="px-4 py-8 text-center">
                  <p className="text-sm text-muted-foreground">{t('components.search.startTyping')}</p>
                  <div className="mt-3 flex items-center justify-center gap-4 text-xs text-subtle-foreground">
                    <span className="flex items-center gap-1"><Server className="h-3 w-3" /> {t('components.search.services')}</span>
                    <span className="flex items-center gap-1"><Key className="h-3 w-3" /> {t('components.search.tokens')}</span>
                    <span className="flex items-center gap-1"><Bot className="h-3 w-3" /> {t('components.search.clients')}</span>
                  </div>
                </div>
              )}
            </div>

            <div className="flex h-9 items-center justify-between border-t border-border px-4 text-xs text-subtle-foreground">
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1">
                  <Kbd>↑</Kbd><Kbd>↓</Kbd>
                  {t('components.search.navigate')}
                </span>
                <span className="flex items-center gap-1">
                  <Kbd>↵</Kbd>
                  {t('components.search.select')}
                </span>
              </div>
              <span className="tabular-nums">{t(totalResults === 1 ? 'components.search.resultsSingular' : 'components.search.resultsPlural', { n: totalResults })}</span>
            </div>
          </div>
        </div>
      </div>
    </>
  )
}
