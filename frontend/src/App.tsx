import { Navigate, Route, Routes } from 'react-router-dom'
import { AppShell } from './layout/AppShell'
import { RedirectIfAuthed, RequireAuth, RequireRole } from './auth/RouteGuards'
import { LoginPage } from './pages/LoginPage'
import { RegisterPage } from './pages/RegisterPage'
import { ForgotPasswordPage } from './pages/ForgotPasswordPage'
import { DashboardPage } from './pages/DashboardPage'
import { OrgAdminPage } from './pages/OrgAdminPage'
import { ReportsPage } from './pages/ReportsPage'
import { SearchPage } from './pages/SearchPage'
import { CenterRankingsPage } from './pages/CenterRankingsPage'
import { SettingsPage } from './pages/SettingsPage'
import { DelayedCashResponsePortalPage } from './pages/DelayedCashResponsePortalPage'
import { DelayedCashOpenLinkPage } from './pages/DelayedCashOpenLinkPage'
import { DelayedCashBillingPage } from './pages/DelayedCashBillingPage'
import { WeeklyRevenueClosurePage } from './pages/WeeklyRevenueClosurePage'
import { WeeklyRevenueResponsePortalPage } from './pages/WeeklyRevenueResponsePortalPage'
import { WeeklyRevenueOpenLinkPage } from './pages/WeeklyRevenueOpenLinkPage'

export default function App() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="/register"
        element={
          <RedirectIfAuthed>
            <RegisterPage />
          </RedirectIfAuthed>
        }
      />
      <Route
        path="/forgot-password"
        element={
          <RedirectIfAuthed>
            <ForgotPasswordPage />
          </RedirectIfAuthed>
        }
      />

      {/* Public response portal -- no login. Two access paths, both kept
          working: a per-case token link (below), and the single shared
          link with no token (the manager self-identifies their center) --
          see DelayedCashOpenLinkPage. Deliberately outside RequireAuth/AppShell. */}
      <Route path="/respond/delayed-cash" element={<DelayedCashOpenLinkPage />} />
      <Route path="/respond/delayed-cash/:token" element={<DelayedCashResponsePortalPage />} />
      <Route path="/respond/weekly-revenue" element={<WeeklyRevenueOpenLinkPage />} />
      <Route path="/respond/weekly-revenue/:token" element={<WeeklyRevenueResponsePortalPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route path="/settings" element={<SettingsPage />} />

          {/* Billing data (Dashboard/Reports/Search/Center Rankings/DCB/WRC)
              is Admin/Auditor-only everywhere on the backend -- gate the
              routes the same way so a denied user sees a clean redirect
              instead of a page that 403s on every data fetch. */}
          <Route element={<RequireRole roles={['Admin', 'Auditor']} />}>
            <Route index element={<DashboardPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/center-rankings" element={<CenterRankingsPage />} />
            <Route path="/weekly-revenue-closure" element={<WeeklyRevenueClosurePage />} />
            <Route path="/delayed-cash" element={<DelayedCashBillingPage />} />
          </Route>

          {/* Users moved into Settings' own Users tab -- redirect anyone
              with the old URL bookmarked/linked rather than 404ing them. */}
          <Route path="/admin/users" element={<Navigate to="/settings?tab=users" replace />} />
          {/* Datasets feature removed entirely (nav, page, backend routes,
              and data) per explicit request -- redirect old bookmarks/
              links to the Dashboard rather than 404ing them. */}
          <Route path="/datasets" element={<Navigate to="/" replace />} />
          <Route path="/datasets/:datasetId" element={<Navigate to="/" replace />} />
          <Route element={<RequireRole roles={['Admin']} />}>
            <Route path="/admin/org" element={<OrgAdminPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
