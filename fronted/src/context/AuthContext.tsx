/**
 * AuthContext — 全局认证状态管理
 */
import { createContext, useContext, useState, useCallback, useEffect } from 'react'
import type { ReactNode } from 'react'
import { authApi, removeToken } from '../api'
import type { AuthUser } from '../api'

interface AuthContextValue {
  user: AuthUser | null
  isLoading: boolean
  error: string | null
  login: (username: string, password: string) => Promise<void>
  register: (data: { username: string; password: string; email: string; role?: string; group?: string }) => Promise<void>
  logout: () => void
  clearError: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // 启动时尝试从 localStorage token 恢复会话
  useEffect(() => {
    const token = localStorage.getItem('mgbi_token')
    if (!token) return
    authApi.me()
      .then((u) => setUser(u))
      .catch(() => {
        // token 失效，清除
        removeToken()
      })
  }, [])

  const login = useCallback(async (username: string, password: string) => {
    setIsLoading(true)
    setError(null)
    try {
      const resp = await authApi.login({ username, password })
      localStorage.setItem('mgbi_token', resp.access_token)
      setUser(resp.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  const register = useCallback(async (data: { username: string; password: string; email: string; role?: string; group?: string }) => {
    setIsLoading(true)
    setError(null)
    try {
      const resp = await authApi.register(data)
      localStorage.setItem('mgbi_token', resp.access_token)
      setUser(resp.user)
    } catch (err) {
      setError(err instanceof Error ? err.message : '注册失败')
      throw err
    } finally {
      setIsLoading(false)
    }
  }, [])

  const logout = useCallback(() => {
    removeToken()
    setUser(null)
  }, [])

  const clearError = useCallback(() => setError(null), [])

  return (
    <AuthContext.Provider value={{ user, isLoading, error, login, register, logout, clearError }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>')
  return ctx
}
