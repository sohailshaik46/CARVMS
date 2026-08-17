import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { Select } from './Select'

const fieldClasses =
  'block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/30 ' +
  'dark:border-slate-700 dark:bg-void-900 dark:text-slate-100 dark:placeholder:text-slate-500 dark:focus:border-neon-500 dark:focus:outline-neon-500/25'

function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  if (!children) return null
  return (
    <label htmlFor={htmlFor} className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
      {children}
    </label>
  )
}

export function TextField({
  label,
  id,
  error,
  className = '',
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label?: ReactNode; error?: string }) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <input id={id} className={`${fieldClasses} ${className}`} {...rest} />
      {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

export function TextAreaField({
  label,
  id,
  error,
  className = '',
  ...rest
}: TextareaHTMLAttributes<HTMLTextAreaElement> & { label?: ReactNode; error?: string }) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <textarea id={id} className={`${fieldClasses} ${className}`} {...rest} />
      {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}

export function SelectField({
  label,
  id,
  error,
  className = '',
  children,
  value,
  disabled,
  onChange,
  name,
}: SelectHTMLAttributes<HTMLSelectElement> & { label?: ReactNode; error?: string }) {
  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <Select
        id={id}
        name={name}
        value={value as string | number | undefined}
        disabled={disabled}
        className={className}
        onChange={onChange as never}
      >
        {children}
      </Select>
      {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
    </div>
  )
}
