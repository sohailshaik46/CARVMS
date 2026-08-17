import type { ReactNode } from 'react'
import { useTheme } from '../../theme/ThemeContext'
import { RadarScanIllustration } from './Illustrations'
import { CheckIcon } from './Icons'

const POINTS = [
  'Every action is logged -- nothing is silent',
  'Role-gated server-side, never just hidden in the UI',
  'Numbers computed once, reused by every dashboard and export',
]

/** Shared two-column shell for Login/Register -- a big illustrated panel
 * on wide screens (the first thing anyone sees before they've even signed
 * in) collapses to just the form card on narrow ones. Both auth pages
 * render an identical left panel so switching between them doesn't jar.
 * Not authenticated yet, so there's no per-user preference to read here --
 * follows whatever theme was last stored locally (see ThemeContext),
 * defaulting to dark. */
export function AuthShell({ children }: { children: ReactNode }) {
  const { theme } = useTheme()
  return (
    <div className={`${theme === 'dark' ? 'dark ' : ''}flex min-h-screen bg-slate-50 dark:bg-void-950`}>
      <div className="vigilance-grid relative hidden w-1/2 flex-col justify-center overflow-hidden border-r border-slate-200 bg-gradient-to-br from-slate-100 via-white to-slate-100 px-12 dark:border-vigilance-600/15 dark:from-void-900 dark:via-void-950 dark:to-void-900 lg:flex">
        <div className="pointer-events-none absolute -right-16 top-10 h-64 w-64 rounded-full bg-brand-200/20 blur-3xl dark:bg-neon-500/10" />
        <div className="pointer-events-none absolute -left-16 bottom-10 h-56 w-56 rounded-full bg-vigilance-500/10 blur-3xl" />
        <div className="pointer-events-none absolute left-1/2 top-1/3 h-32 w-32 rounded-full bg-brand-200/[0.15] blur-2xl dark:bg-neon-pink-500/[0.06]" />
        <div className="hero-illustration relative mx-auto w-72 max-w-full">
          <RadarScanIllustration className="h-full w-full" />
        </div>
        <p className="relative mt-4 text-center text-xs font-semibold uppercase tracking-widest text-brand-600 dark:text-neon-400">
          Always Watching
        </p>
        <h2 className="relative mt-2 text-center text-2xl font-bold text-slate-900 dark:text-slate-50">
          Billing Data Validation
        </h2>
        <p className="relative mx-auto mt-2 max-w-sm text-center text-sm text-slate-600 dark:text-slate-400">
          Central audit, revenue vigilance, and penalty automation -- one source of truth for every number.
        </p>
        <ul className="relative mx-auto mt-6 max-w-sm space-y-2">
          {POINTS.map((p) => (
            <li key={p} className="flex items-start gap-2 text-sm text-slate-600 dark:text-slate-400">
              <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-vigilance-500 dark:text-vigilance-400" />
              {p}
            </li>
          ))}
        </ul>
      </div>

      <div className="vigilance-grid flex w-full flex-col items-center justify-center px-4 py-12 lg:w-1/2">
        {children}
      </div>
    </div>
  )
}
