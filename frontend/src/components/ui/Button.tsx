import type { ButtonHTMLAttributes } from 'react'

type Variant = 'primary' | 'secondary' | 'danger' | 'ghost'

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    'bg-brand-600 text-white hover:bg-brand-700 focus-visible:outline-brand-600 ' +
    // Dark surface: the primary CTA is neon-green, not brand red -- red on
    // the dark app is reserved for NephroPlus-branded contexts only.
    'dark:bg-neon-600 dark:text-void-950 dark:hover:bg-neon-500 dark:focus-visible:outline-neon-500 ' +
    'dark:shadow-[0_0_16px_rgba(18,230,115,0.25)] dark:hover:shadow-[0_0_22px_rgba(57,255,138,0.35)]',
  secondary:
    'bg-white text-slate-700 border border-slate-300 hover:bg-slate-50 focus-visible:outline-slate-400 ' +
    'dark:bg-void-900 dark:text-slate-200 dark:border-vigilance-600/30 dark:hover:border-neon-500/50 dark:hover:bg-void-800 dark:focus-visible:outline-neon-500',
  danger:
    'bg-red-600 text-white hover:bg-red-700 focus-visible:outline-red-600 ' +
    // Dark surface: destructive actions get neon-pink, the one accent
    // color reserved for "this is destructive" -- never literal red here.
    'dark:bg-neon-pink-500 dark:text-void-950 dark:hover:bg-neon-pink-400 dark:focus-visible:outline-neon-pink-500 ' +
    'dark:shadow-[0_0_16px_rgba(240,31,174,0.25)] dark:hover:shadow-[0_0_22px_rgba(255,79,195,0.35)]',
  ghost:
    'bg-transparent text-slate-600 hover:bg-slate-100 focus-visible:outline-slate-400 ' +
    'dark:text-slate-300 dark:hover:bg-void-800 dark:hover:text-neon-400 dark:focus-visible:outline-neon-500',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  isLoading?: boolean
}

export function Button({ variant = 'primary', isLoading, className = '', children, disabled, ...rest }: ButtonProps) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${className}`}
      disabled={disabled || isLoading}
      {...rest}
    >
      {isLoading && (
        <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" />
      )}
      {children}
    </button>
  )
}
