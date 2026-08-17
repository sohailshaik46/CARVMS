import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import nephroplusLogo from '../assets/nephroplus-logo-dark.svg'
import { AuthShell } from '../components/ui/AuthShell'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/Field'
import { ErrorBanner } from '../components/ui/Feedback'
import { apiErrorMessage } from '../lib/api'
import { requestPasswordResetOtp, resetPasswordWithOtp } from '../lib/resources/auth'

/** Two-step "forgot password" -- request a code, then use it. Never
 * reveals whether the phone number entered is actually registered (the
 * backend returns the same generic message either way, see
 * app/services/otp_service.py); this page shows that same message rather
 * than trying to infer anything from it. */
export function ForgotPasswordPage() {
  const navigate = useNavigate()
  const [step, setStep] = useState<'request' | 'reset'>('request')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [code, setCode] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [info, setInfo] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleRequestCode(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      const { message } = await requestPasswordResetOtp(phoneNumber)
      setInfo(message)
      setStep('reset')
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not request a code'))
    } finally {
      setIsSubmitting(false)
    }
  }

  async function handleReset(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (newPassword !== confirmPassword) {
      setError("New password and confirmation don't match")
      return
    }
    setIsSubmitting(true)
    try {
      await resetPasswordWithOtp({ phone_number: phoneNumber, code, new_password: newPassword })
      navigate('/login')
    } catch (err) {
      setError(apiErrorMessage(err, 'Invalid or expired code'))
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <AuthShell>
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center lg:hidden">
          <img src={nephroplusLogo} alt="NephroPlus" className="h-8 w-auto" />
          <h1 className="mt-3 text-lg font-semibold text-slate-900 dark:text-slate-100">Billing Data Validation</h1>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm dark:border-vigilance-600/20 dark:bg-void-900 dark:shadow-lg dark:shadow-black/40">
          {step === 'request' ? (
            <>
              <p className="text-sm text-slate-600 dark:text-slate-400">
                Enter the mobile number on your account. If it's registered, we'll text you a reset code.
              </p>
              <form onSubmit={handleRequestCode} className="mt-6 space-y-4">
                {error && <ErrorBanner message={error} />}
                <TextField
                  id="forgot-phone"
                  label="Mobile number"
                  type="tel"
                  autoComplete="tel"
                  required
                  placeholder="+919876543210"
                  pattern="^\+[1-9]\d{7,14}$"
                  title="Include the country code, e.g. +919876543210"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                />
                <Button type="submit" isLoading={isSubmitting} className="w-full">
                  Send code
                </Button>
              </form>
            </>
          ) : (
            <>
              {info && <p className="text-sm text-slate-600 dark:text-slate-400">{info}</p>}
              <form onSubmit={handleReset} className="mt-4 space-y-4">
                {error && <ErrorBanner message={error} />}
                <TextField
                  id="forgot-code"
                  label="6-digit code"
                  inputMode="numeric"
                  autoComplete="one-time-code"
                  required
                  minLength={4}
                  maxLength={8}
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                />
                <TextField
                  id="forgot-new-password"
                  label="New password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                />
                <TextField
                  id="forgot-confirm-password"
                  label="Confirm new password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                />
                <Button type="submit" isLoading={isSubmitting} className="w-full">
                  Reset password
                </Button>
                <button
                  type="button"
                  onClick={() => setStep('request')}
                  className="w-full text-center text-xs text-slate-500 hover:underline dark:text-slate-400"
                >
                  Use a different number / request a new code
                </button>
              </form>
            </>
          )}

          <p className="mt-4 text-center text-sm text-slate-600 dark:text-slate-400">
            <Link to="/login" className="font-medium text-np-calming-blue hover:underline dark:text-neon-blue-400">
              Back to sign in
            </Link>
          </p>
        </div>
      </div>
    </AuthShell>
  )
}
