import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import nephroplusLogo from '../assets/nephroplus-logo-dark.svg'
import { AuthShell } from '../components/ui/AuthShell'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/Field'
import { ErrorBanner } from '../components/ui/Feedback'
import { apiErrorMessage } from '../lib/api'

export function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [phoneNumber, setPhoneNumber] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await register(username, email, password, phoneNumber)
      navigate('/')
    } catch (err) {
      setError(apiErrorMessage(err, 'Could not register'))
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
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Create an account — new accounts start as <span className="font-medium text-slate-700 dark:text-slate-300">Auditor</span>.
            An Admin can change your role afterward.
          </p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            {error && <ErrorBanner message={error} />}
            <TextField
              id="username"
              label="Username"
              autoComplete="username"
              required
              minLength={3}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <TextField
              id="email"
              label="Email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
            <TextField
              id="password"
              label="Password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <TextField
              id="phone_number"
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
            <p className="text-xs text-slate-500 dark:text-slate-400">
              Password-reset codes and case-deadline alerts go to this number -- include the country code.
            </p>
            <Button type="submit" isLoading={isSubmitting} className="w-full">
              Create account
            </Button>
          </form>

          <p className="mt-4 text-center text-sm text-slate-600 dark:text-slate-400">
            Already have an account?{' '}
            <Link to="/login" className="font-medium text-np-calming-blue hover:underline dark:text-neon-blue-400">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </AuthShell>
  )
}
