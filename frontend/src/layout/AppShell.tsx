import { useState, type FormEvent } from 'react'
import { NavLink, Outlet, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
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
import nephroplusLogo from '../assets/nephroplus-logo-dark.svg'
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
  const navigate = useNavigate()
  const [searchInput, setSearchInput] = useState('')

  function handleSearchSubmit(e: FormEvent) {
    e.preventDefault()
    if (searchInput.trim()) {
      navigate(`/search?q=${encodeURIComponent(searchInput.trim())}`)
    }
  }

  return (
    <div className="dark flex h-full min-h-screen w-full bg-void-950">
      <aside className="vigilance-grid flex w-60 flex-col border-r border-vigilance-600/15 bg-void-900">
        <div className="border-b border-vigilance-600/15 px-4 py-4">
          <div className="flex items-center gap-2.5">
            <img src={nephroplusLogo} alt="NephroPlus" className="h-6 w-auto" />
            <div>
              <p className="text-sm font-semibold text-slate-100">Billing Data Validation</p>
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
                      ? 'bg-neon-500/10 text-neon-400 ring-1 ring-inset ring-neon-500/40 shadow-[0_0_12px_rgba(18,230,115,0.12)]'
                      : 'text-slate-400 hover:bg-void-800 hover:text-vigilance-300'
                  }`
                }
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span className="truncate">{item.label}</span>
              </NavLink>
            )
          })}
        </nav>
        <div className="border-t border-vigilance-600/15 p-3">
          <p className="px-1 text-[11px] text-slate-500">Every action is logged. Vigilance sees everything.</p>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-4 border-b border-vigilance-600/15 bg-void-900 px-6 py-3">
          <form onSubmit={handleSearchSubmit} className="w-full max-w-sm">
            <div className="relative">
              <SearchIcon className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-500" />
              <input
                type="search"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder="Search bills, incidents, datasets…"
                className="w-full rounded-md border border-vigilance-600/25 bg-void-950 py-1.5 pl-8 pr-3 text-sm text-slate-100 placeholder:text-slate-500 focus:border-neon-500 focus:outline focus:outline-2 focus:outline-neon-500/25"
              />
            </div>
          </form>
          <div className="flex shrink-0 items-center gap-3">
            {user && (
              <>
                <span className="text-sm text-slate-300">{user.username}</span>
                <Badge>{user.role}</Badge>
                <button
                  onClick={logout}
                  className="flex items-center gap-1.5 text-sm font-medium text-slate-400 hover:text-neon-400"
                >
                  <LogoutIcon className="h-4 w-4" /> Log out
                </button>
              </>
            )}
          </div>
        </header>
        <main className="min-w-0 flex-1 overflow-y-auto bg-void-950 p-6">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
