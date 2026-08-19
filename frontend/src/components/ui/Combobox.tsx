import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from 'react'

/** A search-as-you-type dropdown -- type any part of a code or a name (e.g.
 * "173" or "ongole") and the option list narrows to substring matches
 * against BOTH; click one, or use Up/Down + Enter, to select it. Unlike a
 * native <select> or <datalist>, filtering is substring (not prefix-only)
 * and always checks every field passed in `searchText`, so a center number
 * typed anywhere finds its center regardless of what the code starts with.
 *
 * Free text is always allowed -- `onChange` fires with whatever's typed
 * even if it never matches an option (see `allowFreeText`), so this is a
 * drop-in for a plain text input that gains a searchable dropdown, not a
 * strict picker that blocks unlisted values. Selecting an option commits
 * immediately via onCommit (defaults to onChange) so callers that want to
 * act the instant a choice is made (e.g. auto-run a lookup) can pass a
 * separate onCommit rather than reacting to every keystroke. */

export interface ComboboxOption {
  value: string
  label: ReactNode
  /** What gets searched, besides `value` itself -- typically the display
   * name, so typing a center's name finds it even though `value` holds
   * only its code. */
  searchText?: string
}

interface ComboboxProps {
  value: string
  onChange: (value: string) => void
  options: ComboboxOption[]
  onCommit?: (value: string) => void
  placeholder?: string
  /** Shown as the first row (only while the query is empty) to reset back
   * to "nothing selected" -- mirrors a native <select>'s placeholder
   * <option>. Omit to not offer a reset row at all. */
  clearLabel?: ReactNode
  id?: string
  className?: string
  disabled?: boolean
  'aria-label'?: string
}

function normalize(s: string): string {
  return s.toLowerCase().trim()
}

export function Combobox({
  value,
  onChange,
  options,
  onCommit,
  placeholder = 'Type to search…',
  clearLabel,
  id,
  className = '',
  disabled,
  ...rest
}: ComboboxProps) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlighted, setHighlighted] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const selected = options.find((o) => o.value === value)
  const displayValue = value === '' ? '' : selected ? String(selected.label) : value

  useEffect(() => {
    if (!open) return
    function onDocMouseDown(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false)
        setQuery('')
      }
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [open])

  const filtered = useMemo(() => {
    const q = normalize(query)
    if (!q) return options
    return options.filter((o) => {
      const haystack = `${o.value} ${o.searchText ?? o.label ?? ''}`
      return normalize(haystack).includes(q)
    })
  }, [options, query])

  function openMenu() {
    setOpen(true)
    setQuery('')
    setHighlighted(0)
    requestAnimationFrame(() => inputRef.current?.select())
  }

  function commit(newValue: string) {
    onChange(newValue)
    onCommit?.(newValue)
    setOpen(false)
    setQuery('')
  }

  function handleKeyDown(e: KeyboardEvent<HTMLInputElement>) {
    if (!open) {
      if (e.key === 'ArrowDown' || e.key === 'Enter') {
        e.preventDefault()
        openMenu()
      }
      return
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted((i) => Math.min(filtered.length - 1, i + 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted((i) => Math.max(0, i - 1))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const opt = filtered[highlighted]
      if (opt) commit(opt.value)
      else if (query.trim()) commit(query.trim())
      else setOpen(false)
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setOpen(false)
      setQuery('')
    } else if (e.key === 'Tab') {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <input
        ref={inputRef}
        id={id}
        type="text"
        autoComplete="off"
        disabled={disabled}
        placeholder={placeholder}
        aria-label={rest['aria-label']}
        role="combobox"
        aria-expanded={open}
        aria-autocomplete="list"
        className="block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/30 disabled:cursor-not-allowed disabled:opacity-50 dark:border-slate-700 dark:bg-void-900 dark:text-slate-100 dark:placeholder:text-slate-400 dark:focus:border-neon-500 dark:focus:outline-neon-500/25"
        value={open ? query : displayValue}
        onFocus={openMenu}
        onChange={(e) => {
          setQuery(e.target.value)
          setHighlighted(0)
          onChange(e.target.value)
          if (!open) setOpen(true)
        }}
        onKeyDown={handleKeyDown}
      />
      {open && (
        <ul
          role="listbox"
          className="absolute z-50 mt-1.5 max-h-64 w-full min-w-max overflow-y-auto rounded-md border border-slate-200 bg-white py-1 shadow-lg dark:border-vigilance-600/30 dark:bg-void-950 dark:shadow-[0_8px_30px_rgba(0,0,0,0.6),0_0_0_1px_rgba(217,169,74,0.08)]"
        >
          {clearLabel && !query.trim() && (
            <li
              role="option"
              aria-selected={value === ''}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => commit('')}
              className="cursor-pointer border-b border-slate-100 px-3 py-1.5 text-sm text-slate-500 hover:bg-brand-50 dark:border-slate-800 dark:text-slate-400 dark:hover:bg-neon-500 dark:hover:text-void-950"
            >
              {clearLabel}
            </li>
          )}
          {filtered.map((opt, i) => (
            <li
              key={opt.value}
              role="option"
              aria-selected={opt.value === value}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => commit(opt.value)}
              className={`cursor-pointer px-3 py-1.5 text-sm transition-colors hover:bg-brand-50 hover:text-brand-700 dark:hover:bg-neon-500 dark:hover:text-void-950 ${
                i === highlighted
                  ? 'bg-brand-50 text-brand-700 font-medium dark:bg-neon-500 dark:text-void-950'
                  : 'text-slate-700 dark:text-slate-200'
              }`}
            >
              {opt.label}
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-3 py-1.5 text-sm text-slate-400 dark:text-slate-500">No matching center</li>
          )}
        </ul>
      )}
    </div>
  )
}
