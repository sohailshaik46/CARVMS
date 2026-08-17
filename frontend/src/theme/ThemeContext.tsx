import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import { useAuth } from '../auth/AuthContext'
import { getMyPreferences, updateMyPreferences } from '../lib/resources/preferences'
import type { ThemeName } from '../lib/types'

const THEME_STORAGE_KEY = 'carvms_theme_v1'

interface ThemeContextValue {
  theme: ThemeName
  setTheme: (theme: ThemeName) => void
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined)

function readStoredTheme(): ThemeName {
  try {
    return localStorage.getItem(THEME_STORAGE_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

/** Controls whether AppShell/AuthShell wrap their content in the `.dark`
 * class -- every shared UI component and internal page renders a light
 * default plus a `dark:` override for exactly that class (see index.css).
 * This is the ONLY thing that ever decides light vs dark for the internal
 * app now; it replaces the old hardcoded-always-dark className. The
 * public, unauthenticated response portal never reads this context at
 * all, so it stays light regardless, per its own deliberate design. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth()
  const [theme, setThemeState] = useState<ThemeName>(readStoredTheme)

  // localStorage gives an instant, correct-looking first paint (no flash of
  // the wrong theme); once authenticated, the backend preference -- which
  // follows the user across devices/browsers -- is the source of truth and
  // wins if it differs.
  useEffect(() => {
    if (!user) return
    let cancelled = false
    getMyPreferences()
      .then((prefs) => {
        if (cancelled) return
        setThemeState(prefs.theme)
        try {
          localStorage.setItem(THEME_STORAGE_KEY, prefs.theme)
        } catch {
          // ignore -- storage may be unavailable (private mode, quota)
        }
      })
      .catch(() => {
        // Offline/error -- keep whatever localStorage/default already gave.
      })
    return () => {
      cancelled = true
    }
  }, [user])

  // <body>'s own background AND text color (index.css) are plain,
  // unconditional dark defaults -- neither can see the `.dark` class,
  // which only wraps AppShell/AuthShell's own root div, not <body> itself.
  // The background gap matters wherever that div doesn't fully cover the
  // viewport (a momentary flash before hydration, elastic overscroll, a
  // shorter-than-viewport page); the text-color gap matters for any
  // element anywhere in the app that doesn't set its own explicit text
  // color and so inherits body's -- both would otherwise always render
  // dark-appropriate regardless of the chosen theme. Setting them here
  // (not in CSS) is the override every page inherits, no matter whether
  // its own markup remembered to set an explicit light-mode text color.
  useEffect(() => {
    document.body.style.backgroundColor = theme === 'dark' ? '#0b0b0d' : '#f8fafc'
    document.body.style.color = theme === 'dark' ? '#f1f5f9' : '#1e293b'
  }, [theme])

  function setTheme(next: ThemeName) {
    setThemeState(next)
    try {
      localStorage.setItem(THEME_STORAGE_KEY, next)
    } catch {
      // ignore
    }
    updateMyPreferences({ theme: next }).catch(() => {
      // Best-effort persistence -- the toggle already applied locally; a
      // failed save just means it won't follow the user to another device.
    })
  }

  return <ThemeContext.Provider value={{ theme, setTheme }}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within a ThemeProvider')
  return ctx
}
