import { useState, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from 'react'
import { EyeIcon, EyeOffIcon } from './Icons'
import { Select } from './Select'

const fieldClasses =
  'block w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 shadow-sm placeholder:text-slate-400 focus:border-brand-500 focus:outline focus:outline-2 focus:outline-brand-500/30 ' +
  'dark:border-slate-700 dark:bg-void-900 dark:text-slate-100 dark:placeholder:text-slate-400 dark:focus:border-neon-500 dark:focus:outline-neon-500/25'

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
  type,
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label?: ReactNode; error?: string }) {
  // Every password field in the app goes through this one component, so
  // the show/hide toggle lives here once rather than being rebuilt at
  // each of the 8 call sites (login, register, forgot/reset, change
  // password, admin create-user). Only activates for type="password" --
  // every other field type (email/tel/number/plain text) is untouched.
  const [showPassword, setShowPassword] = useState(false)
  const isPassword = type === 'password'

  if (!isPassword) {
    return (
      <div>
        <Label htmlFor={id}>{label}</Label>
        <input id={id} type={type} className={`${fieldClasses} ${className}`} {...rest} />
        {error && <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>}
      </div>
    )
  }

  return (
    <div>
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <input
          id={id}
          type={showPassword ? 'text' : 'password'}
          className={`${fieldClasses} pr-9 ${className}`}
          {...rest}
        />
        <button
          type="button"
          onClick={() => setShowPassword((s) => !s)}
          aria-label={showPassword ? 'Hide password' : 'Show password'}
          className="absolute inset-y-0 right-0 flex items-center px-2.5 text-slate-400 hover:text-slate-600 dark:text-slate-500 dark:hover:text-slate-300"
        >
          {showPassword ? <EyeOffIcon className="h-4 w-4" /> : <EyeIcon className="h-4 w-4" />}
        </button>
      </div>
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
