import { createContext, useCallback, useContext, useState, type ReactNode } from 'react'

interface Toast {
  id: number
  message: string
  tone: 'success' | 'error'
}

interface ToastContextValue {
  showToast: (message: string, tone?: Toast['tone']) => void
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

let nextId = 1

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const showToast = useCallback((message: string, tone: Toast['tone'] = 'success') => {
    const id = nextId++
    setToasts((prev) => [...prev, { id, message, tone }])
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 4000)
  }, [])

  return (
    <ToastContext.Provider value={{ showToast }}>
      {children}
      <div className="fixed bottom-4 right-4 z-[100] flex flex-col gap-2">
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={`rounded-md px-4 py-2 text-sm text-white shadow-lg dark:shadow-black/50 ${toast.tone === 'success' ? 'bg-slate-800' : 'bg-red-600'}`}
          >
            {toast.message}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within a ToastProvider')
  return ctx
}
