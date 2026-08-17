import { useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { useTheme } from '../../theme/ThemeContext'

/** Hover/focus explanation for a button, filter pill, or KPI box -- "what
 * is this" and "what happens if I click it", shown without clicking.
 * Positioned via getBoundingClientRect + a portal to document.body (not
 * CSS-only absolute positioning) specifically so it's never clipped by an
 * ancestor's overflow-x-auto -- every batches/review-queue table on these
 * pages scrolls horizontally, which would otherwise cut a plain absolute
 * tooltip off. Portaling to document.body means this renders OUTSIDE
 * AppShell's `.dark`-wrapped subtree, so a `dark:` Tailwind variant would
 * never match here regardless of theme -- hence the explicit theme check
 * below instead of a dark: class. */
export function Tooltip({ text, children }: { text: string; children: ReactNode }) {
  const { theme } = useTheme()
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null)
  const triggerRef = useRef<HTMLSpanElement>(null)

  function show() {
    const rect = triggerRef.current?.getBoundingClientRect()
    if (!rect) return
    setCoords({ top: rect.top - 8, left: rect.left + rect.width / 2 })
  }

  function hide() {
    setCoords(null)
  }

  return (
    <span ref={triggerRef} className="inline-flex" onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {children}
      {coords &&
        createPortal(
          <div
            role="tooltip"
            className={`pointer-events-none fixed z-[100] max-w-[16rem] -translate-x-1/2 -translate-y-full rounded-md border px-2.5 py-1.5 text-xs leading-snug shadow-lg ${
              theme === 'dark'
                ? 'border-vigilance-600/30 bg-void-900 text-slate-200 shadow-black/50'
                : 'border-slate-200 bg-white text-slate-700 shadow-slate-400/30'
            }`}
            style={{ top: coords.top, left: coords.left }}
          >
            {text}
          </div>,
          document.body,
        )}
    </span>
  )
}
