import { useState, useEffect } from 'react'
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../contexts/AuthContext'
import { systemApi } from '../services/api'
import GlobalSearch from './GlobalSearch'
import ThemeToggle from './ThemeToggle'
import LanguageSwitcher from './LanguageSwitcher'
import SettingsModal from './SettingsModal'
import ProfileModal from './ProfileModal'
import {
  LayoutDashboard,
  Key,
  Plus,
  Server,
  Store,
  LogOut,
  Bot,
  FileText,
  Settings,
  Menu,
  X,
} from 'lucide-react'
import clsx from 'clsx'
import { IconButton, Avatar, Wordmark } from './ui'

// 單租戶:登入即管理員,選單不做權限過濾
const navItems = [
  { to: '/', icon: LayoutDashboard, labelKey: 'nav.dashboard', end: true },
  { to: '/services', icon: Server, labelKey: 'nav.services' },
  { to: '/tokens', end: true, icon: Key, labelKey: 'nav.tokens' },
  { to: '/tokens/create', icon: Plus, labelKey: 'nav.issueToken' },
  { to: '/clients', icon: Bot, labelKey: 'nav.clients' },
  { to: '/marketplace', icon: Store, labelKey: 'nav.marketplace' },
  { to: '/audit', icon: FileText, labelKey: 'nav.audit' },
]

export default function Layout() {
  const { t } = useTranslation()
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const [showSettings, setShowSettings] = useState(false)
  const [showProfile, setShowProfile] = useState(false)
  const [version, setVersion] = useState(null)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  useEffect(() => {
    systemApi.getVersion().then(setVersion).catch(() => {})
  }, [])

  // Auto-close drawer when navigating on narrow screens
  useEffect(() => {
    setSidebarOpen(false)
  }, [location.pathname])

  const handleLogout = async () => {
    await logout()
    navigate('/login')
  }

  const displayName = user?.username || user?.email || t('layout.adminFallback')

  return (
    <div className="min-h-screen">
      {sidebarOpen && (
        <div
          className="fixed inset-0 z-30 bg-zinc-900/40 backdrop-blur-[2px] lg:hidden"
          onClick={() => setSidebarOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Sidebar */}
      <aside
        className={clsx(
          'fixed inset-y-0 left-0 z-40 flex w-60 flex-col border-r border-hairline bg-canvas',
          'transition-transform duration-150 ease-out lg:translate-x-0',
          sidebarOpen ? 'translate-x-0' : '-translate-x-full',
        )}
      >
        {/* Wordmark + search */}
        <div className="flex h-14 items-center justify-between px-4">
          <Wordmark name={t('layout.appName')} />
          <IconButton
            icon={X}
            title={t('layout.closeMenu')}
            onClick={() => setSidebarOpen(false)}
            className="lg:hidden"
          />
        </div>
        <div className="px-3 pb-2">
          <GlobalSearch />
        </div>

        {/* Navigation */}
        <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-2">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  'flex h-8 items-center gap-2.5 rounded-md px-2 text-sm transition-colors duration-150',
                  isActive
                    ? 'bg-zinc-200/70 font-medium text-ink dark:bg-zinc-800'
                    : 'text-ink-muted hover:bg-zinc-200/60 hover:text-ink dark:hover:bg-zinc-800/70',
                )
              }
            >
              <item.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
              <span className="truncate">{t(item.labelKey)}</span>
            </NavLink>
          ))}
        </nav>

        {/* User block */}
        <div className="border-t border-hairline p-3">
          <button
            onClick={() => setShowProfile(true)}
            className="flex w-full items-center gap-2.5 rounded-md p-1.5 text-left transition-colors duration-150 hover:bg-zinc-200/60 dark:hover:bg-zinc-800/70"
            title={t('layout.profile')}
          >
            <Avatar name={displayName} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-medium text-ink">{displayName}</span>
              <span className="block truncate text-xs text-ink-muted">{user?.email || ''}</span>
            </span>
          </button>
          <div className="mt-2 flex items-center justify-between">
            <div className="flex items-center gap-0.5">
              <IconButton icon={Settings} title={t('layout.settings')} onClick={() => setShowSettings(true)} />
              <ThemeToggle />
              <LanguageSwitcher />
            </div>
            <IconButton icon={LogOut} title={t('layout.logout')} onClick={handleLogout} />
          </div>
          {version && (
            <p className="mt-2 px-1.5 text-2xs text-ink-subtle">
              {t('layout.version', { version: version.version })}
            </p>
          )}
        </div>
      </aside>

      {/* Main content */}
      <main className="min-w-0 lg:pl-60">
        {/* Mobile-only bar */}
        <div className="sticky top-0 z-20 flex h-12 items-center gap-3 border-b border-hairline bg-canvas/95 px-4 backdrop-blur lg:hidden">
          <IconButton
            icon={Menu}
            title={t('layout.openMenu')}
            onClick={() => setSidebarOpen(true)}
          />
          <Wordmark name={t('layout.appName')} />
        </div>

        <div className="mx-auto w-full max-w-7xl px-6 py-8">
          <Outlet />
        </div>
      </main>

      <SettingsModal isOpen={showSettings} onClose={() => setShowSettings(false)} />
      <ProfileModal isOpen={showProfile} onClose={() => setShowProfile(false)} />
    </div>
  )
}
