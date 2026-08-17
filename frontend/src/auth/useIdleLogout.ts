import { useEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from './AuthContext'
import { getMyPreferences } from '../lib/resources/preferences'

const ACTIVITY_EVENTS = ['mousemove', 'mousedown', 'keydown', 'scroll', 'touchstart'] as const

/** Logs the user out after N minutes of no mouse/keyboard/scroll/touch
 * activity -- N comes from Settings -> Security
 * (security_settings.session_timeout_minutes), per-user. Purely a
 * client-side timer: nothing server-enforced yet, so a still-valid JWT
 * keeps working against the API directly even past this window (see
 * app/models/user_preference.py's own note on this). 0/missing disables
 * it entirely rather than logging out immediately. */
export function useIdleLogout() {
  const { user, logout } = useAuth()
  const { data: preferences } = useQuery({
    queryKey: ['my-preferences'],
    queryFn: getMyPreferences,
    enabled: !!user,
  })
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const minutes = preferences?.security_settings?.session_timeout_minutes

  useEffect(() => {
    if (!user || !minutes || minutes <= 0) return

    function reset() {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      timeoutRef.current = setTimeout(() => logout(), minutes! * 60 * 1000)
    }

    reset()
    ACTIVITY_EVENTS.forEach((evt) => window.addEventListener(evt, reset))
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      ACTIVITY_EVENTS.forEach((evt) => window.removeEventListener(evt, reset))
    }
  }, [user, minutes, logout])
}
