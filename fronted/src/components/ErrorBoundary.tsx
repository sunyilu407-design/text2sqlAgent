/**
 * ErrorBoundary — React Error Boundary to prevent white screen on component errors
 * @license SPDX-License-Identifier: Apache-2.0
 */
import { Component, type ReactNode, type ErrorInfo } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
  onError?: (error: Error, errorInfo: ErrorInfo) => void
}

interface State {
  hasError: boolean
  error: Error | null
}

// ts-expect-error needed: React 19 moved state/setState to private internals
// on the public Component type, but they still exist at runtime.
class ErrorBoundaryClass extends Component<Props, State> {
  declare readonly props: Props & { children?: ReactNode }
  declare state: State

  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo)
    this.props.onError?.(error, errorInfo)
  }

  render() {
    const currentState: State = this.state
    const currentProps: Props = this.props

    if (currentState.hasError) {
      if (currentProps.fallback) return currentProps.fallback

      const devMode = (import.meta as unknown as { env: Record<string, unknown> }).env.DEV

      return (
        <div className="flex flex-col items-center justify-center min-h-[60vh] px-6 text-center">
          <div className="panel-elevated p-10 rounded-3xl max-w-md w-full space-y-5">
            <div className="flex justify-center">
              <div className="w-16 h-16 rounded-full bg-red-50 dark:bg-red-950/40 flex items-center justify-center">
                <svg className="w-8 h-8 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z" />
                </svg>
              </div>
            </div>
            <div>
              <h2 className="text-base font-bold text-slate-800 dark:text-slate-100">组件渲染异常</h2>
              <p className="mt-2 text-xs text-slate-500 dark:text-slate-400 leading-relaxed font-medium">
                抱歉，页面渲染遇到问题。请尝试刷新页面。
              </p>
              {devMode && currentState.error && (
                <pre className="mt-3 p-3 bg-red-50 dark:bg-red-950/30 rounded-xl text-[10px] text-red-600 dark:text-red-400 text-left overflow-auto max-h-40 font-mono">
                  {currentState.error.message}
                </pre>
              )}
            </div>
            <button
              onClick={() => window.location.reload()}
              className="w-full py-2.5 px-4 bg-indigo-500 dark:bg-indigo-600 hover:bg-indigo-600 dark:hover:bg-indigo-500 text-white font-bold text-xs rounded-xl transition-colors cursor-pointer"
            >
              刷新页面
            </button>
            <button
              onClick={() => (this as unknown as { setState(s: State): void }).setState({ hasError: false, error: null })}
              className="w-full py-2 px-4 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 font-semibold text-xs rounded-xl transition-colors cursor-pointer"
            >
              重试
            </button>
          </div>
        </div>
      )
    }

    return currentProps.children
  }
}

export const ErrorBoundary = ErrorBoundaryClass
