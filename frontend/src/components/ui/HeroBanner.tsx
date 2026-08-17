import type { ReactNode } from 'react'

/** The illustrated header every top-level page opens with -- replaces the
 * plain <h1>/<p> block. Every page passes a different Illustrations.tsx
 * component as `illustration`, so the composition (glow, grid texture,
 * float animation, gold kicker) stays identical everywhere and only the
 * artwork + copy change -- one system, not a one-off per page. */
export function HeroBanner({
  illustration,
  kicker,
  title,
  subtitle,
  actions,
}: {
  illustration: ReactNode
  kicker?: string
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
}) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-vigilance-600/20 bg-gradient-to-br from-void-900 via-void-950 to-void-900 dark:block">
      <div className="vigilance-grid pointer-events-none absolute inset-0 opacity-60" />
      <div className="pointer-events-none absolute -right-10 -top-10 h-48 w-48 rounded-full bg-neon-500/10 blur-3xl" />
      <div className="pointer-events-none absolute -left-10 bottom-0 h-40 w-40 rounded-full bg-vigilance-500/10 blur-3xl" />
      {/* Small hints of neon pink and neon blue -- faint accent glows,
          never third/fourth competing "active state" colors, just a bit
          of variety alongside the gold/green language used everywhere
          else. */}
      <div className="pointer-events-none absolute bottom-4 right-1/3 h-24 w-24 rounded-full bg-neon-pink-500/[0.06] blur-2xl" />
      <div className="pointer-events-none absolute left-1/3 top-0 h-20 w-20 rounded-full bg-neon-blue-500/[0.07] blur-2xl" />
      <div className="relative flex flex-col gap-5 p-6 sm:flex-row sm:items-center sm:justify-between sm:p-8">
        <div className="min-w-0">
          {kicker && (
            <p className="text-xs font-semibold uppercase tracking-widest text-neon-400">{kicker}</p>
          )}
          <h1 className="mt-1 text-2xl font-bold text-slate-50">{title}</h1>
          {subtitle && <div className="mt-2 max-w-2xl text-sm text-slate-400">{subtitle}</div>}
          {actions && <div className="mt-4 flex flex-wrap gap-2">{actions}</div>}
        </div>
        <div className="hero-illustration hidden shrink-0 sm:block sm:w-44 md:w-52">{illustration}</div>
      </div>
    </div>
  )
}
