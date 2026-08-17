import {
  Children,
  isValidElement,
  useEffect,
  useMemo,
  useRef,
  useState,
  type OptionHTMLAttributes,
  type ReactNode,
} from 'react'
import { CheckIcon, ChevronDownIcon } from './Icons'

/** A fully custom dropdown -- native <select> popups are OS-rendered chrome
 * that ignores almost all page CSS (only `color-scheme` gets partial
 * Chromium cooperation), so there is no way to guarantee the "black
 * background, gold = selected, neon = hovered" look on a native element.
 * This renders its own popup instead, with full control over every pixel.
 *
 * Drop-in for a native <select>: pass the same <option value="...">Label</option>
 * children, the same `value`/`onChange`/`disabled` props. `onChange` receives
 * a minimal object shaped like a real ChangeEvent ({ target: { value } }) so
 * every existing caller (`onChange={(e) => setX(e.target.value)}`) keeps
 * working unchanged.
 *
 * Mouse-hover and keyboard-navigation highlighting are deliberately two
 * SEPARATE mechanisms, never one state synced from the other:
 *   - hover uses plain CSS `:hover` -- the browser's own hit-testing, with
 *     zero React state involved.
 *   - keyboard nav uses the `highlighted` state, touched ONLY by arrow
 *     keys and by "sync to the current value when the menu opens".
 * Earlier this used one `highlighted` state for both, driven by
 * `onMouseEnter`/`onMouseMove` -- but Chromium synthesizes a mouseover on
 * whatever element ends up under an already-stationary cursor when new
 * content (like this popup) renders, with no real pointer movement at
 * all. That silently stomped the correct highlight the instant the menu
 * opened. Keeping the two mechanisms fully independent removes that
 * failure mode entirely rather than working around it. */

interface ParsedOption {
  value: string
  label: ReactNode
  disabled?: boolean
}

interface SelectProps {
  id?: string
  value?: string | number
  disabled?: boolean
  className?: string
  onChange?: (event: { target: { value: string; id?: string; name?: string } }) => void
  name?: string
  children?: ReactNode
  'aria-label'?: string
}

function parseOptions(children: ReactNode): ParsedOption[] {
  const options: ParsedOption[] = []
  Children.forEach(children, (child) => {
    if (!isValidElement(child)) return
    const props = child.props as OptionHTMLAttributes<HTMLOptionElement>
    if (child.type !== 'option') return
    options.push({
      value: String(props.value ?? ''),
      label: props.children,
      disabled: props.disabled,
    })
  })
  return options
}

const NEON_HOVER = 'hover:bg-neon-500 hover:text-void-950'

export function Select({ id, value, disabled, className = '', onChange, name, children, ...rest }: SelectProps) {
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLUListElement>(null)

  const options = useMemo(() => parseOptions(children), [children])
  const selectedIndex = Math.max(0, options.findIndex((o) => o.value === String(value ?? '')))
  const selected = options[selectedIndex]

  useEffect(() => {
    if (!open) return
    function onDocClick(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDocClick)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  useEffect(() => {
    if (open) setHighlighted(selectedIndex)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  useEffect(() => {
    if (open) listRef.current?.children[highlighted]?.scrollIntoView({ block: 'nearest' })
  }, [open, highlighted])

  function commit(newValue: string) {
    onChange?.({ target: { value: newValue, id, name } })
    setOpen(false)
  }

  function onTriggerKeyDown(e: React.KeyboardEvent) {
    if (disabled) return
    if (!open && (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
      e.preventDefault()
      setOpen(true)
      return
    }
    if (!open) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((i) => Math.min(options.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      const opt = options[highlighted]
      if (opt && !opt.disabled) commit(opt.value)
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <button
        id={id}
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={rest['aria-label']}
        onClick={() => !disabled && setOpen((o) => !o)}
        onKeyDown={onTriggerKeyDown}
        className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm shadow-sm transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${
          open
            ? 'border-neon-500 bg-void-900 text-slate-100 outline outline-2 outline-neon-500/25'
            : 'border-slate-700 bg-void-900 text-slate-100 hover:border-vigilance-500/50'
        } ${className}`}
      >
        <span className="truncate">{selected ? selected.label : <span className="text-slate-500">Select...</span>}</span>
        <ChevronDownIcon className={`h-4 w-4 shrink-0 text-vigilance-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <ul
          ref={listRef}
          role="listbox"
          className="absolute z-50 mt-1.5 max-h-64 w-full min-w-max overflow-y-auto rounded-md border border-vigilance-600/30 bg-void-950 py-1 shadow-[0_8px_30px_rgba(0,0,0,0.6),0_0_0_1px_rgba(217,169,74,0.08)]"
        >
          {options.map((opt, i) => {
            const isSelected = opt.value === String(value ?? '')
            const isHighlighted = i === highlighted
            return (
              <li
                key={opt.value + i}
                role="option"
                aria-selected={isSelected}
                onClick={() => !opt.disabled && commit(opt.value)}
                className={`flex items-center justify-between gap-2 px-3 py-1.5 text-sm transition-colors ${
                  opt.disabled
                    ? 'cursor-not-allowed text-slate-600'
                    : `cursor-pointer ${NEON_HOVER} ${
                        isHighlighted
                          ? 'bg-neon-500 text-void-950 font-medium'
                          : isSelected
                            ? 'text-vigilance-300'
                            : 'text-slate-200'
                      }`
                }`}
              >
                <span className="truncate">{opt.label}</span>
                {isSelected && !isHighlighted && <CheckIcon className="h-3.5 w-3.5 shrink-0 text-vigilance-400" />}
              </li>
            )
          })}
          {options.length === 0 && <li className="px-3 py-1.5 text-sm text-slate-500">No options</li>}
        </ul>
      )}
    </div>
  )
}
