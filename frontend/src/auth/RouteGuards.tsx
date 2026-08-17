import type { ReactNode } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from './AuthContext'
import { Spinner } from '../components/ui/Feedback'
import type { Role } from '../lib/types'

export function RequireAuth() {
  const { user, isLoading } = useAuth()
  if (isLoading) return <Spinner />
  if (!user) return <Navigate to="/login" replace />
  return <Outlet />
}

export function RequireRole({ roles }: { roles: Role[] }) {
  const { user } = useAuth()
  if (!user || !roles.includes(user.role)) {
    return (
      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
        You don't have permission to view this page.
      </div>
    )
  }
  return <Outlet />
}

export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { user, isLoading } = useAuth()
  if (isLoading) return <Spinner />
  if (user) return <Navigate to="/" replace />
  return <>{children}</>
}
