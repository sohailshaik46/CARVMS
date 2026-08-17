import type { ComponentPropsWithoutRef, KeyboardEvent, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import { Tooltip } from './Tooltip'

export function Card({
  children,
  className = '',
  ...rest
}: { children: ReactNode; className?: string } & ComponentPropsWithoutRef<'div'>) {
  return (
    <div
      className={`rounded-lg border border-slate-200 bg-white shadow-sm dark:border-vigilance-600/20 dark:bg-void-900 dark:shadow-black/40 ${className}`}
      {...rest}
    >
      {children}
    </div>
  )
}

export function CardHeader({ title, actions }: { title: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-vigilance-600/15">
      <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">{title}</h3>
      {actions}
    </div>
  )
}

export function CardBody({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`p-4 ${className}`}>{children}</div>
}

/** `to`, when given, makes the whole card a navigation target -- e.g. the
 * "Bills Awaiting Review" KPI on the Dashboard links straight to that
 * page's Review Queue tab, per the user's explicit request that these
 * boxes route to the page the number actually comes from, not just
 * display it. Purely a link -- KpiCard itself never re-derives the
 * number, still passed in from the same summary the target page reads. */
export function KpiCard({
  label,
  value,
  hint,
  to,
  onCardClick,
  tooltip,
}: {
  label: string
  value: ReactNode
  hint?: string
  to?: string
  /** Alternative to `to` for a click target that isn't a route change --
   * e.g. opening a local panel/modal that needs state already held by the
   * current component (a specific batch id), rather than navigating away
   * from it. `to` takes precedence if both are given. */
  onCardClick?: () => void
  /** Hover explanation for what this number means -- shown on the label,
   * independent of `hint` (a short caption always visible underneath the
   * value). Use this for the fuller "what is this / where does it come
   * from" explanation that doesn't fit as a permanent caption. */
  tooltip?: string
}) {
  const navigate = useNavigate()
  const handleActivate = to ? () => navigate(to) : onCardClick
  return (
    <Card
      className={`relative overflow-hidden dark:hover:border-neon-500/40 dark:transition-colors ${
        handleActivate ? 'cursor-pointer hover:border-vigilance-400' : ''
      }`}
      {...(handleActivate
        ? {
            role: 'button',
            tabIndex: 0,
            onClick: handleActivate,
            onKeyDown: (e: KeyboardEvent) => {
              if (e.key === 'Enter' || e.key === ' ') handleActivate()
            },
          }
        : {})}
    >
      <div className="pointer-events-none absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-vigilance-500 via-neon-500 to-vigilance-500 opacity-0 dark:opacity-70" />
      <CardBody>
        {tooltip ? (
          <Tooltip text={tooltip}>
            <p className="cursor-help text-xs font-medium uppercase tracking-wide text-slate-500 underline decoration-dotted dark:text-vigilance-400/80">
              {label}
            </p>
          </Tooltip>
        ) : (
          <p className="text-xs font-medium uppercase tracking-wide text-slate-500 dark:text-vigilance-400/80">{label}</p>
        )}
        <p className="mt-1 text-2xl font-semibold text-slate-900 dark:text-slate-50">{value}</p>
        {hint && <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">{hint}</p>}
      </CardBody>
    </Card>
  )
}
