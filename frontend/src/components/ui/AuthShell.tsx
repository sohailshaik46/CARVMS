import type { ReactNode } from 'react'
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
 * render an identical left panel so switching between them doesn't jar. */
export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="dark flex min-h-screen bg-void-950">
      <div className="vigilance-grid relative hidden w-1/2 flex-col justify-center overflow-hidden border-r border-vigilance-600/15 bg-gradient-to-br from-void-900 via-void-950 to-void-900 px-12 lg:flex">
        <div className="pointer-events-none absolute -right-16 top-10 h-64 w-64 rounded-full bg-neon-500/10 blur-3xl" />
        <div className="pointer-events-none absolute -left-16 bottom-10 h-56 w-56 rounded-full bg-vigilance-500/10 blur-3xl" />
        <div className="pointer-events-none absolute left-1/2 top-1/3 h-32 w-32 rounded-full bg-neon-pink-500/[0.06] blur-2xl" />
        <div className="hero-illustration relative mx-auto w-72 max-w-full">
          <RadarScanIllustration className="h-full w-full" />
        </div>
        <p className="relative mt-4 text-center text-xs font-semibold uppercase tracking-widest text-neon-400">
          Always Watching
        </p>
        <h2 className="relative mt-2 text-center text-2xl font-bold text-slate-50">
          Billing Data Validation
        </h2>
        <p className="relative mx-auto mt-2 max-w-sm text-center text-sm text-slate-400">
          Central audit, revenue vigilance, and penalty automation -- one source of truth for every number.
        </p>
        <ul className="relative mx-auto mt-6 max-w-sm space-y-2">
          {POINTS.map((p) => (
            <li key={p} className="flex items-start gap-2 text-sm text-slate-400">
              <CheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-vigilance-400" />
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
