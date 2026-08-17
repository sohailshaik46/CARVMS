import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import nephroplusLogo from '../assets/nephroplus-logo-dark.svg'
import { AuthShell } from '../components/ui/AuthShell'
import { Button } from '../components/ui/Button'
import { TextField } from '../components/ui/Field'
import { ErrorBanner } from '../components/ui/Feedback'
import { apiErrorMessage } from '../lib/api'

export function LoginPage() {
  const { login } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setIsSubmitting(true)
    try {
      await login(username, password)
      navigate('/')
    } catch (err) {
      setError(apiErrorMessage(err, 'Invalid username or password'))
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
          <p className="text-sm text-slate-600 dark:text-slate-400">Sign in to continue</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            {error && <ErrorBanner message={error} />}
            <TextField
              id="username"
              label="Username"
              autoComplete="username"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
            />
            <TextField
              id="password"
              label="Password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <Button type="submit" isLoading={isSubmitting} className="w-full">
              Sign in
            </Button>
          </form>

          <p className="mt-3 text-center text-sm">
            <Link
              to="/forgot-password"
              className="font-medium text-np-calming-blue hover:underline dark:text-neon-blue-400"
            >
              Forgot password?
            </Link>
          </p>

          <p className="mt-4 text-center text-sm text-slate-600 dark:text-slate-400">
            Don't have an account?{' '}
            <Link to="/register" className="font-medium text-np-calming-blue hover:underline dark:text-neon-blue-400">
              Register
            </Link>
          </p>
        </div>
        <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-600">Every action is logged. Vigilance sees everything.</p>
      </div>
    </AuthShell>
  )
}
