import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { registerUnauthorizedHandler, TOKEN_STORAGE_KEY } from '../lib/api'
import { fetchMe, login as loginRequest, registerUser } from '../lib/resources/auth'
import type { UserOut } from '../lib/types'

interface AuthContextValue {
  user: UserOut | null
  isLoading: boolean
  login: (username: string, password: string) => Promise<void>
  register: (username: string, email: string, password: string, phoneNumber: string) => Promise<void>
  logout: () => void
  /** Re-fetches /auth/me and updates `user` -- call after a self-service
   * change (e.g. phone number) that isn't reflected until the next login
   * otherwise, since `user` isn't itself backed by react-query. */
  refreshUser: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserOut | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const logout = useCallback(() => {
    localStorage.removeItem(TOKEN_STORAGE_KEY)
    setUser(null)
  }, [])

  useEffect(() => {
    registerUnauthorizedHandler(logout)
  }, [logout])

  useEffect(() => {
    const token = localStorage.getItem(TOKEN_STORAGE_KEY)
    if (!token) {
      setIsLoading(false)
      return
    }
    fetchMe()
      .then(setUser)
      .catch(() => {
        localStorage.removeItem(TOKEN_STORAGE_KEY)
      })
      .finally(() => setIsLoading(false))
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    const token = await loginRequest({ username, password })
    localStorage.setItem(TOKEN_STORAGE_KEY, token.access_token)
    const me = await fetchMe()
    setUser(me)
  }, [])

  const register = useCallback(async (username: string, email: string, password: string, phoneNumber: string) => {
    await registerUser({ username, email, password, phone_number: phoneNumber })
    await login(username, password)
  }, [login])

  const refreshUser = useCallback(async () => {
    if (!localStorage.getItem(TOKEN_STORAGE_KEY)) return
    const me = await fetchMe()
    setUser(me)
  }, [])

  const value = useMemo(
    () => ({ user, isLoading, login, register, logout, refreshUser }),
    [user, isLoading, login, register, logout, refreshUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
