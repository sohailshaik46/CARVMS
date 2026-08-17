import { useEffect, useState, type FormEvent } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { TextField } from '../components/ui/Field'
import { Button } from '../components/ui/Button'
import { HeroBanner } from '../components/ui/HeroBanner'
import { GearOrbitIllustration } from '../components/ui/Illustrations'
import { Tooltip } from '../components/ui/Tooltip'
import { useToast } from '../components/ui/ToastProvider'
import { useAuth } from '../auth/AuthContext'
import { useTheme } from '../theme/ThemeContext'
import { apiErrorMessage } from '../lib/api'
import { DASHBOARD_KPIS, resolveVisibleKpis } from '../lib/dashboardKpis'
import { changeMyPassword, updateMyPhoneNumber } from '../lib/resources/auth'
import { getMyPreferences, updateMyPreferences } from '../lib/resources/preferences'
import {
  disconnectEmail,
  getEmailConnectAuthorizationUrl,
  getEmailConnectionStatus,
  listEmailProviders,
} from '../lib/resources/email'
import type { NotificationPrefs, ThemeName } from '../lib/types'

type SettingsTab = 'appearance' | 'dashboard' | 'notifications' | 'security'
const TAB_VALUES: SettingsTab[] = ['appearance', 'dashboard', 'notifications', 'security']
const TABS: { key: SettingsTab; label: string }[] = [
  { key: 'appearance', label: 'Appearance' },
  { key: 'dashboard', label: 'Dashboard' },
  { key: 'notifications', label: 'Notifications' },
  { key: 'security', label: 'Security' },
]

export function SettingsPage() {
  const [params, setParams] = useSearchParams()
  const initialTab = TAB_VALUES.find((t) => t === params.get('tab')) ?? 'appearance'
  const [tab, setTab] = useState<SettingsTab>(initialTab)

  // Same-pathname ?tab= changes (e.g. a future cross-page link into
  // Settings) don't remount this component, so re-sync from the URL
  // whenever it changes rather than only reading it once at mount.
  useEffect(() => {
    const fromUrl = TAB_VALUES.find((t) => t === params.get('tab'))
    if (fromUrl) setTab(fromUrl)
  }, [params])

  function selectTab(next: SettingsTab) {
    setTab(next)
    params.set('tab', next)
    setParams(params, { replace: true })
  }

  return (
    <div className="space-y-6">
      <HeroBanner
        illustration={<GearOrbitIllustration className="h-full w-full" />}
        kicker="Configuration"
        title="Settings"
        subtitle="Personal preferences -- theme, dashboard layout, notifications, and session security. Nothing here is shared with other users."
      />

      <div className="flex gap-1 border-b border-slate-200 dark:border-slate-700">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => selectTab(t.key)}
            className={`relative px-3 py-2 text-sm font-medium ${
              tab === t.key
                ? 'border-b-2 border-brand-600 text-brand-700 dark:border-neon-500 dark:text-neon-400'
                : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'appearance' && <AppearanceTab />}
      {tab === 'dashboard' && <DashboardTab />}
      {tab === 'notifications' && <NotificationsTab />}
      {tab === 'security' && <SecurityTab />}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Appearance
// ---------------------------------------------------------------------------

function AppearanceTab() {
  const { theme, setTheme } = useTheme()

  return (
    <Card>
      <CardHeader title="Theme" />
      <CardBody className="space-y-4">
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Choose how the app looks for you. This is a personal preference -- it doesn't change what anyone else
          sees, and it follows you to any device you log in from.
        </p>
        <div className="flex gap-3">
          <ThemeOption
            active={theme === 'light'}
            label="Light"
            description="Bright background, dark text."
            onClick={() => setTheme('light' as ThemeName)}
            preview="bg-white border-slate-300"
          />
          <ThemeOption
            active={theme === 'dark'}
            label="Dark"
            description="The vigilance/investigation theme -- black with gold and neon accents."
            onClick={() => setTheme('dark' as ThemeName)}
            preview="bg-void-950 border-vigilance-600/40"
          />
        </div>
      </CardBody>
    </Card>
  )
}

function ThemeOption({
  active,
  label,
  description,
  onClick,
  preview,
}: {
  active: boolean
  label: string
  description: string
  onClick: () => void
  preview: string
}) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-lg border-2 p-4 text-left transition-colors ${
        active
          ? 'border-brand-500 bg-brand-50 dark:border-neon-500 dark:bg-neon-500/10'
          : 'border-slate-200 hover:border-slate-300 dark:border-slate-700 dark:hover:border-slate-600'
      }`}
    >
      <div className={`mb-3 h-12 w-full rounded border ${preview}`} />
      <p className="text-sm font-semibold text-slate-800 dark:text-slate-100">
        {label} {active && <span className="text-brand-600 dark:text-neon-400">(current)</span>}
      </p>
      <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{description}</p>
    </button>
  )
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------

function DashboardTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const { data: preferences, isLoading } = useQuery({ queryKey: ['my-preferences'], queryFn: getMyPreferences })
  const [order, setOrder] = useState<string[] | null>(null)

  const visible = order ?? resolveVisibleKpis(preferences?.dashboard_config?.visible_kpis).map((k) => k.key)
  const byKey = new Map(DASHBOARD_KPIS.map((k) => [k.key, k]))

  const saveMutation = useMutation({
    mutationFn: (visible_kpis: string[]) => updateMyPreferences({ dashboard_config: { visible_kpis } }),
    onSuccess: (prefs) => {
      queryClient.setQueryData(['my-preferences'], prefs)
      queryClient.invalidateQueries({ queryKey: ['dashboard-summary'] })
      showToast('Dashboard layout saved')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save'), 'error'),
  })

  function toggle(key: string) {
    const next = visible.includes(key) ? visible.filter((k) => k !== key) : [...visible, key]
    setOrder(next)
    saveMutation.mutate(next)
  }

  function move(key: string, direction: -1 | 1) {
    const i = visible.indexOf(key)
    const j = i + direction
    if (i < 0 || j < 0 || j >= visible.length) return
    const next = [...visible]
    ;[next[i], next[j]] = [next[j], next[i]]
    setOrder(next)
    saveMutation.mutate(next)
  }

  if (isLoading) return <Spinner />

  return (
    <Card>
      <CardHeader title="Dashboard KPI Cards" />
      <CardBody className="space-y-3">
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Choose which KPI cards show on your Dashboard, and the order they appear in. Hidden cards aren't deleted --
          you can turn them back on any time.
        </p>
        <ul className="divide-y divide-slate-200 dark:divide-slate-700">
          {visible.map((key, i) => {
            const kpi = byKey.get(key)
            if (!kpi) return null
            return (
              <li key={key} className="flex items-center justify-between gap-3 py-2">
                <label className="flex items-center gap-2.5 text-sm text-slate-700 dark:text-slate-200">
                  <input
                    type="checkbox"
                    checked
                    onChange={() => toggle(key)}
                    className="h-4 w-4 rounded border-slate-300 text-brand-600 dark:border-slate-600 dark:bg-void-900 dark:text-neon-500"
                  />
                  {kpi.label}
                </label>
                <div className="flex items-center gap-1">
                  <Tooltip text="Move this card earlier">
                    <button
                      type="button"
                      disabled={i === 0}
                      onClick={() => move(key, -1)}
                      className="rounded px-1.5 py-0.5 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-void-800"
                    >
                      ▲
                    </button>
                  </Tooltip>
                  <Tooltip text="Move this card later">
                    <button
                      type="button"
                      disabled={i === visible.length - 1}
                      onClick={() => move(key, 1)}
                      className="rounded px-1.5 py-0.5 text-xs text-slate-500 hover:bg-slate-100 disabled:opacity-30 dark:text-slate-400 dark:hover:bg-void-800"
                    >
                      ▼
                    </button>
                  </Tooltip>
                </div>
              </li>
            )
          })}
        </ul>
        {DASHBOARD_KPIS.filter((k) => !visible.includes(k.key)).length > 0 && (
          <div className="pt-2">
            <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">Hidden</p>
            <ul className="space-y-1.5">
              {DASHBOARD_KPIS.filter((k) => !visible.includes(k.key)).map((kpi) => (
                <li key={kpi.key}>
                  <label className="flex items-center gap-2.5 text-sm text-slate-500 dark:text-slate-500">
                    <input
                      type="checkbox"
                      checked={false}
                      onChange={() => toggle(kpi.key)}
                      className="h-4 w-4 rounded border-slate-300 text-brand-600 dark:border-slate-600 dark:bg-void-900 dark:text-neon-500"
                    />
                    {kpi.label}
                  </label>
                </li>
              ))}
            </ul>
          </div>
        )}
      </CardBody>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Notifications
// ---------------------------------------------------------------------------

const NOTIFICATION_TOGGLES: { key: keyof NotificationPrefs; label: string; hint: string }[] = [
  {
    key: 'email_on_new_case',
    label: 'New case opened',
    hint: 'Email me when a DCB/WRC case is opened for a center.',
  },
  {
    key: 'email_on_decision',
    label: 'Decision recorded',
    hint: 'Email me when a bill/incident is marked considered, not considered, or sent for manual review.',
  },
  {
    key: 'email_on_escalation',
    label: 'Disciplinary escalation',
    hint: 'Email me when a case escalates past its response deadline.',
  },
]

function NotificationsTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const { data: preferences, isLoading } = useQuery({ queryKey: ['my-preferences'], queryFn: getMyPreferences })

  const saveMutation = useMutation({
    mutationFn: (notification_prefs: NotificationPrefs) => updateMyPreferences({ notification_prefs }),
    onSuccess: (prefs) => {
      queryClient.setQueryData(['my-preferences'], prefs)
      showToast('Notification preferences saved')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save'), 'error'),
  })

  function toggle(key: keyof NotificationPrefs) {
    if (!preferences) return
    const next = { ...preferences.notification_prefs, [key]: !preferences.notification_prefs[key] }
    saveMutation.mutate(next)
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader title="Email Notifications" />
        <CardBody className="space-y-1">
          {isLoading && <Spinner />}
          {preferences &&
            NOTIFICATION_TOGGLES.map((n) => (
              <label
                key={n.key}
                className="flex items-start justify-between gap-4 border-b border-slate-100 py-3 last:border-0 dark:border-slate-800"
              >
                <span>
                  <span className="block text-sm font-medium text-slate-800 dark:text-slate-100">{n.label}</span>
                  <span className="block text-xs text-slate-500 dark:text-slate-400">{n.hint}</span>
                </span>
                <input
                  type="checkbox"
                  checked={!!preferences.notification_prefs[n.key]}
                  onChange={() => toggle(n.key)}
                  className="mt-1 h-4 w-4 shrink-0 rounded border-slate-300 text-brand-600 dark:border-slate-600 dark:bg-void-900 dark:text-neon-500"
                />
              </label>
            ))}
        </CardBody>
      </Card>

      <EmailConnectionCard />
    </div>
  )
}

/** The account these notification emails actually send FROM -- moved here
 * (was the whole of Settings before Appearance/Dashboard/Security existed)
 * since it's a direct dependency of the toggles above: none of them can
 * send anything without this connected. */
function EmailConnectionCard() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const [params, setParams] = useSearchParams()
  const [connectError, setConnectError] = useState<string | null>(null)

  const { data: providers, isLoading: providersLoading } = useQuery({
    queryKey: ['email-providers'],
    queryFn: listEmailProviders,
  })
  const { data: status, isLoading: statusLoading } = useQuery({
    queryKey: ['email-status'],
    queryFn: getEmailConnectionStatus,
  })

  useEffect(() => {
    const connected = params.get('email_connected')
    const emailError = params.get('email_error')
    if (connected) {
      showToast('Email connected')
      queryClient.invalidateQueries({ queryKey: ['email-status'] })
    } else if (emailError) {
      setConnectError(`Could not connect email: ${emailError}`)
    }
    if (connected || emailError) {
      params.delete('email_connected')
      params.delete('email_error')
      setParams(params, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const connectMutation = useMutation({
    mutationFn: getEmailConnectAuthorizationUrl,
    onSuccess: (data) => {
      window.location.href = data.authorization_url
    },
    onError: (err) => setConnectError(apiErrorMessage(err, 'Could not start the connection')),
  })

  const disconnectMutation = useMutation({
    mutationFn: disconnectEmail,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['email-status'] })
      showToast('Email disconnected')
    },
    onError: (err) => setConnectError(apiErrorMessage(err, 'Could not disconnect')),
  })

  const gmail = providers?.find((p) => p.provider === 'gmail')
  const loading = providersLoading || statusLoading

  return (
    <Card>
      <CardHeader title="Connect Email" />
      <CardBody>
        {connectError && <ErrorBanner message={connectError} />}
        {loading && <Spinner />}
        {!loading && gmail && (
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-200">Gmail</p>
              {!gmail.configured && (
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Not set up yet — an administrator needs to register a Google OAuth app first. See{' '}
                  <code className="rounded bg-slate-100 px-1 dark:bg-slate-700">docs/EMAIL_SETUP.md</code>.
                </p>
              )}
              {gmail.configured && status?.connected && (
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                  Connected{status.connected_at ? ` on ${new Date(status.connected_at).toLocaleDateString()}` : ''}
                  {status.scope ? ` — scope: ${status.scope}` : ''}
                </p>
              )}
              {gmail.configured && status?.connected && !status.can_send && (
                <p className="mt-1 text-xs text-amber-600 dark:text-amber-400">
                  This connection can't send email yet -- reconnect and grant the send permission to enable
                  decision-notification email for Delayed Cash Billing / Weekly Revenue Closure.
                </p>
              )}
              {gmail.configured && !status?.connected && (
                <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">Not connected.</p>
              )}
            </div>

            {gmail.configured && status?.connected && (
              <div className="flex gap-2">
                {!status.can_send && (
                  <Button isLoading={connectMutation.isPending} onClick={() => connectMutation.mutate()}>
                    Reconnect
                  </Button>
                )}
                <Button variant="secondary" isLoading={disconnectMutation.isPending} onClick={() => disconnectMutation.mutate()}>
                  Disconnect
                </Button>
              </div>
            )}
            {gmail.configured && !status?.connected && (
              <Button isLoading={connectMutation.isPending} onClick={() => connectMutation.mutate()}>
                Connect
              </Button>
            )}
          </div>
        )}
      </CardBody>
    </Card>
  )
}

// ---------------------------------------------------------------------------
// Security
// ---------------------------------------------------------------------------

function SecurityTab() {
  const queryClient = useQueryClient()
  const { showToast } = useToast()
  const { data: preferences, isLoading } = useQuery({ queryKey: ['my-preferences'], queryFn: getMyPreferences })
  const [minutes, setMinutes] = useState('')

  useEffect(() => {
    if (preferences) setMinutes(String(preferences.security_settings.session_timeout_minutes))
  }, [preferences])

  const saveMutation = useMutation({
    mutationFn: (session_timeout_minutes: number) =>
      updateMyPreferences({ security_settings: { session_timeout_minutes } }),
    onSuccess: (prefs) => {
      queryClient.setQueryData(['my-preferences'], prefs)
      showToast('Security settings saved')
    },
    onError: (err) => showToast(apiErrorMessage(err, 'Could not save'), 'error'),
  })

  function handleSave() {
    const n = Number(minutes)
    if (!Number.isFinite(n) || n < 0) return
    saveMutation.mutate(n)
  }

  return (
    <div className="space-y-6">
      <PasswordChangeCard />
      <PhoneNumberCard />

      <Card>
        <CardHeader title="Session Timeout" />
        <CardBody className="space-y-4">
          {isLoading && <Spinner />}
          {!isLoading && (
            <>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                How long the app can sit idle (no mouse/keyboard/scroll activity) before it signs you out
                automatically. Set to 0 to disable. This is a client-side timer -- it protects an unattended screen,
                but a still-valid login token isn't separately expired on the server by this setting.
              </p>
              <div className="flex items-end gap-3">
                <TextField
                  id="session-timeout"
                  label="Minutes"
                  type="number"
                  min={0}
                  value={minutes}
                  onChange={(e) => setMinutes(e.target.value)}
                  className="w-32"
                />
                <Button isLoading={saveMutation.isPending} onClick={handleSave}>
                  Save
                </Button>
              </div>
            </>
          )}
        </CardBody>
      </Card>
    </div>
  )
}

function PasswordChangeCard() {
  const { showToast } = useToast()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => changeMyPassword({ current_password: currentPassword, new_password: newPassword }),
    onSuccess: () => {
      showToast('Password changed')
      setCurrentPassword('')
      setNewPassword('')
      setConfirmPassword('')
      setError(null)
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not change password -- check your current password')),
  })

  function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation don't match")
      return
    }
    if (newPassword.length < 8) {
      setError('New password must be at least 8 characters')
      return
    }
    mutation.mutate()
  }

  return (
    <Card>
      <CardHeader title="Change Password" />
      <CardBody>
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && <ErrorBanner message={error} />}
          <TextField
            id="current-password"
            label="Current password"
            type="password"
            autoComplete="current-password"
            required
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
          />
          <TextField
            id="new-password"
            label="New password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <TextField
            id="confirm-password"
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            required
            minLength={8}
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
          <Button type="submit" isLoading={mutation.isPending}>
            Change password
          </Button>
        </form>
      </CardBody>
    </Card>
  )
}

function PhoneNumberCard() {
  const { user, refreshUser } = useAuth()
  const { showToast } = useToast()
  const [phoneNumber, setPhoneNumber] = useState(user?.phone_number ?? '')
  const [error, setError] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => updateMyPhoneNumber(phoneNumber),
    onSuccess: async () => {
      showToast('Mobile number saved')
      setError(null)
      await refreshUser()
    },
    onError: (err) => setError(apiErrorMessage(err, 'Could not save -- use international format, e.g. +919876543210')),
  })

  return (
    <Card>
      <CardHeader title="Mobile Number" />
      <CardBody className="space-y-4">
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Where your password-reset codes and case-deadline escalation alerts are sent. Include the country code.
        </p>
        {error && <ErrorBanner message={error} />}
        <div className="flex items-end gap-3">
          <TextField
            id="my-phone-number"
            label="Mobile number"
            type="tel"
            placeholder="+919876543210"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            className="w-56"
          />
          <Button isLoading={mutation.isPending} onClick={() => mutation.mutate()}>
            Save
          </Button>
        </div>
      </CardBody>
    </Card>
  )
}
