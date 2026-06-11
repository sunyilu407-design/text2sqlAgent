/**
 * Toast Notification System
 * Global toast context for user feedback
 */
import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'
import { CheckCircle, AlertCircle, Info, X } from 'lucide-react'

export type ToastType = 'success' | 'error' | 'info'

export interface Toast {
  id: string
  type: ToastType
  message: string
  duration?: number
}

interface ToastContextValue {
  toasts: Toast[]
  toast: (message: string, type?: ToastType, duration?: number) => void
  success: (message: string, duration?: number) => void
  error: (message: string, duration?: number) => void
  info: (message: string, duration?: number) => void
  dismiss: (id: string) => void
  dismissAll: () => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const dismiss = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id))
  }, [])

  const addToast = useCallback((message: string, type: ToastType = 'info', duration = 4000) => {
    const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2)}`
    const toast: Toast = { id, type, message, duration }
    setToasts(prev => [...prev, toast])
    if (duration > 0) {
      setTimeout(() => dismiss(id), duration)
    }
  }, [dismiss])

  const toast = useCallback((message: string, type: ToastType = 'info', duration?: number) => {
    addToast(message, type, duration ?? 4000)
  }, [addToast])

  const success = useCallback((message: string, duration?: number) => addToast(message, 'success', duration ?? 4000), [addToast])
  const error = useCallback((message: string, duration?: number) => addToast(message, 'error', duration ?? 6000), [addToast])
  const info = useCallback((message: string, duration?: number) => addToast(message, 'info', duration ?? 4000), [addToast])
  const dismissAll = useCallback(() => setToasts([]), [])

  return (
    <ToastContext.Provider value={{ toasts, toast, success, error, info, dismiss, dismissAll }}>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    // Return no-op functions when used outside provider
    return {
      toasts: [],
      toast: () => {},
      success: () => {},
      error: () => {},
      info: () => {},
      dismiss: () => {},
      dismissAll: () => {},
    }
  }
  return ctx
}

function ToastContainer({ toasts, onDismiss }: { toasts: Toast[]; onDismiss: (id: string) => void }) {
  if (toasts.length === 0) return null

  const iconMap = {
    success: <CheckCircle className="w-4 h-4 text-emerald-500" />,
    error: <AlertCircle className="w-4 h-4 text-red-500" />,
    info: <Info className="w-4 h-4 text-blue-500" />,
  }

  const bgMap = {
    success: 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-200 dark:border-emerald-800',
    error: 'bg-red-50 dark:bg-red-950/40 border-red-200 dark:border-red-800',
    info: 'bg-blue-50 dark:bg-blue-950/40 border-blue-200 dark:border-blue-800',
  }

  return (
    <div className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 max-w-sm">
      {toasts.map(t => (
        <div
          key={t.id}
          className={`flex items-center gap-3 px-4 py-3 rounded-xl border shadow-lg backdrop-blur-sm ${bgMap[t.type]}`}
        >
          {iconMap[t.type]}
          <span className="flex-1 text-xs font-medium text-slate-700 dark:text-slate-200">{t.message}</span>
          <button
            onClick={() => onDismiss(t.id)}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 transition-colors"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      ))}
    </div>
  )
}
