import { useState, type FormEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { useIdleLogout } from '../auth/useIdleLogout'
import { useTheme } from '../theme/ThemeContext'
import { Badge } from '../components/ui/Badge'
import {
  BuildingIcon,
  CalendarClockIcon,
  ChartIcon,
  CogIcon,
  FolderIcon,
  HomeIcon,
  LogoutIcon,
  ReceiptIcon,
  SearchIcon,
  TrophyIcon,
  UsersIcon,
} from '../components/ui/Icons'
import nephroplusLogoLight from '../assets/nephroplus-logo.svg'
import nephroplusLogoDark from '../assets/nephroplus-logo-dark.svg'
import type { Role } from '../lib/types'

interface NavItem {
  to: string
  label: string
  end?: boolean
  roles?: Role[]
  icon: (props: { className?: string }) => React.ReactElement
}

const NAV_ITEMS: NavItem[] = [
  { to: '/', label: 'Dashboard', end: true, roles: ['Admin', 'Auditor'], icon: HomeIcon },
  { to: '/datasets', label: 'Datasets', icon: FolderIcon },
  { to: '/weekly-revenue-closure', label: 'Weekly Revenue Closure', roles: ['Admin', 'Auditor'], icon: CalendarClockIcon },
  { to: '/delayed-cash', label: 'Delayed Cash Billing', roles: ['Admin', 'Auditor'], icon: ReceiptIcon },
  { to: '/reports', label: 'Reports', roles: ['Admin', 'Auditor'], icon: ChartIcon },
  { to: '/center-rankings', label: 'Center Rankings', roles: ['Admin', 'Auditor'], icon: TrophyIcon },
  { to: '/settings', label: 'Settings', icon: CogIcon },
  { to: '/admin/org', label: 'Org Hierarchy', roles: ['Admin'], icon: BuildingIcon },
  { to: '/admin/users', label: 'Users', roles: ['Admin'], icon: UsersIcon },
]

export function AppShell() {
  const { user, logout } = useAuth()
  const { theme } = useTheme()
  const navigate = useNavigate()
  const [searchInput, setSearchInput] = useState('')
  useIdleLogout()

  function handleSearchSubmit(e: FormEvent) {
    e.preventDefault()
    if (searchInput.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchInput.trim())}`)
    }
  }

  return (
    <div className={`${theme === 'dark' ? 'dark ' : ''}flex h-full min-h-screen w-full bg-slate-50 dark:bg-void-950`}>
      <aside className="vigilance-grid flex w-60 flex-col border-r border-slate-200 bg-white dark:border-vigilance-600/15 dark:bg-void-900">
        <div className="border-b border-slate-200 px-4 py-4 dark:border-vigilance-600/15">
          <div className="flex items-center gap-2.5">
            <img src={theme === 'dark' ? nephroplusLogoDark : nephroplusLogoLight} alt="NephroPlus" className="h-6 w-auto" />
            <div>
              <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">Billing Data Validation</p>
            </div>
          </div>
        </div>
        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {NAV_ITEMS.filter((item) => !item.roles || (!!user && item.roles.includes(user.role))).map((item) => {
            const Icon = item.icon
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={({ isActive }) =>
                  `flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-brand-50 text-brand-700 ring-1 ring-inset ring-brand-200 dark:bg-neon-500/10 dark:text-neon-400 dark:ring-neon-500/40 dark:shadow-[0_0_12px_rgba(18,230,115,0.12)]'
                      : 'text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:text-slate-400 dark:hover:bg-void-800 dark:hover:text-vigilance-300'
                  }`
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
        <div className="border-t border-slate-200 p-3 dark:border-vigilance-600/15">
          <p className="px-1 text-[11px] text-slate-500 dark:text-slate-400">Every action is logged. Vigilance sees everything.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-slate-200 bg-white px-6 py-3 dark:border-vigilance-600/15 dark:bg-void-900">
          <form onSubmit={handleSearchSubmit} className="w-full max-w-sm">
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
              <input
                type="search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search bills, incidents, datasets…"
                className="w-full rounded-md border border-slate-300 bg-slate-50 py-1.5 pl-8 pr-3 text-sm text-slate-800 placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/25 dark:border-vigilance-600/25 dark:bg-void-950 dark:text-slate-100 dark:focus:border-neon-500 dark:focus:outline-neon-500/25"
              />
            </div>
          </form>
          <div className="flex shrink-0 items-center gap-3">
            {user && (
              <>
                <span className="text-sm text-slate-600 dark:text-slate-300">{user.username}</span>
                <Badge>{user.role}</Badge>
                <button
                  onClick={logout}
                  className="flex items-center gap-1.5 text-sm font-medium text-slate-500 hover:text-brand-600 dark:text-slate-400 dark:hover:text-neon-400"
                >
                  <LogoutIcon className="h-4 w-4" /> Log out
                </button>
              </>
            )}
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto bg-slate-50 p-6 dark:bg-void-950">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
