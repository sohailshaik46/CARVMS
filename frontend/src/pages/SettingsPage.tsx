import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Card, CardBody, CardHeader } from '../components/ui/Card'
import { ErrorBanner, Spinner } from '../components/ui/Feedback'
import { Button } from '../components/ui/Button'
import { HeroBanner } from '../components/ui/HeroBanner'
import { GearOrbitIllustration } from '../components/ui/Illustrations'
import { useToast } from '../components/ui/ToastProvider'
import { apiErrorMessage } from '../lib/api'
import {
  disconnectEmail,
  getEmailConnectAuthorizationUrl,
  getEmailConnectionStatus,
  listEmailProviders,
} from '../lib/resources/email'

export function SettingsPage() {
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

  // Google redirects back here (via our backend's /email/callback) with
  // either ?email_connected=1 or ?email_error=... on the URL -- surface it
  // once, then strip it so a page refresh doesn't re-show a stale toast.
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
    <div className="space-y-6">
      <HeroBanner
        illustration={<GearOrbitIllustration className="h-full w-full" />}
        kicker="Configuration"
        title="Settings"
        subtitle="Connect the email account this app sends notifications from."
      />
      {connectError && <ErrorBanner message={connectError} />}

      <Card>
        <CardHeader title="Connect Email" />
        <CardBody>
          {loading && <Spinner />}
          {!loading && gmail && (
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm font-medium text-slate-200">Gmail</p>
                {!gmail.configured && (
                  <p className="mt-1 text-xs text-slate-500">
                    Not set up yet — an administrator needs to register a Google OAuth app first. See{' '}
                    <code className="rounded bg-slate-800 px-1">docs/EMAIL_SETUP.md</code>.
                  </p>
                )}
                {gmail.configured && status?.connected && (
                  <p className="mt-1 text-xs text-slate-500">
                    Connected{status.connected_at ? ` on ${new Date(status.connected_at).toLocaleDateString()}` : ''}
                    {status.scope ? ` — scope: ${status.scope}` : ''}
                  </p>
                )}
                {gmail.configured && status?.connected && !status.can_send && (
                  <p className="mt-1 text-xs text-amber-400">
                    This connection can't send email yet -- reconnect and grant the send permission to enable
                    decision-notification email for Delayed Cash Billing / Weekly Revenue Closure.
                  </p>
                )}
                {gmail.configured && !status?.connected && (
                  <p className="mt-1 text-xs text-slate-500">Not connected.</p>
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
    </div>
  )
}
