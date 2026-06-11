/**
 * App.tsx — 使用 AuthContext 进行全局认证管理
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import { useState } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ScreenType } from './types'
import TopNavBar from './components/TopNavBar'
import DashboardView from './components/DashboardView'
import QueryWorkbenchView from './components/QueryWorkbenchView'
import RegistryView from './components/RegistryView'
import ReportView from './components/ReportView'
import AssistantView from './components/AssistantView'
import AuthView from './components/AuthView'
import SettingsView from './components/SettingsView'
import AdminDashboardView from './components/AdminDashboardView'
import HealthDashboard from './components/HealthDashboard'
import { ErrorBoundary } from './components/ErrorBoundary'
import { useAuth } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import type { LLMConfig } from './types'

const DEFAULT_CONFIG: LLMConfig = {
  endpoint: 'https://api.deepseek.com/v1',
  apiKey: '',
  modelName: 'deepseek-chat',
  temperature: 0.15,
  maxTokens: 2048,
}

function loadConfig(): LLMConfig {
  try {
    const stored = localStorage.getItem('mgbi_llm_config')
    return stored ? { ...DEFAULT_CONFIG, ...JSON.parse(stored) } : DEFAULT_CONFIG
  } catch {
    return DEFAULT_CONFIG
  }
}

export default function App() {
  const [currentScreen, setCurrentScreen] = useState<ScreenType>('dashboard')
  const { user, logout } = useAuth()
  const [llmConfig, setLlmConfig] = useState<LLMConfig>(loadConfig)

  const handleScreenChange = (screen: ScreenType) => {
    setCurrentScreen(screen)
  }

  const handleSaveConfig = (updated: LLMConfig) => {
    setLlmConfig(updated)
    localStorage.setItem('mgbi_llm_config', JSON.stringify(updated))
  }

  const renderActiveScreen = () => {
    if (!user && currentScreen !== 'auth') {
      return (
        <div className="text-center py-16 space-y-4">
          <p className="text-xs text-slate-500 font-semibold uppercase tracking-wider">
            当前处于离线孤立节点，需要验证会话身份
          </p>
          <AuthView />
        </div>
      )
    }

    switch (currentScreen) {
      case 'dashboard':
        return <DashboardView onGoToReport={() => handleScreenChange('reports')} />
      case 'query':
        return <QueryWorkbenchView />
      case 'registry':
        return <RegistryView />
      case 'reports':
        return <ReportView />
      case 'chat':
        return <AssistantView />
      case 'auth':
        return <AuthView />
      case 'settings':
        return (
          <SettingsView
            config={llmConfig}
            onSaveConfig={handleSaveConfig}
          />
        )
      case 'admin':
        if (user?.role !== 'admin') {
          return (
            <div className="glass-panel p-8 rounded-2xl text-center bg-white/40 border border-slate-200 space-y-4 max-w-md mx-auto my-12 text-slate-800">
              <h3 className="text-sm font-bold text-slate-900">权限不足 (Access Denied)</h3>
              <p className="text-xs text-slate-500 leading-relaxed font-medium">
                该后台仅面向具有 SYS_ROOT 安全标志的系统运维管理员开放。
              </p>
              <button
                onClick={() => setCurrentScreen('dashboard')}
                className="mt-4 px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white font-bold text-xs rounded-xl"
              >
                返回仪表盘
              </button>
            </div>
          )
        }
        return <AdminDashboardView />
      case 'health':
        return <HealthDashboard />
      default:
        return <DashboardView onGoToReport={() => handleScreenChange('reports')} />
    }
  }

  return (
    <ToastProvider>
    <div className="flex flex-col min-h-screen bg-[#e8edf5] text-slate-800 overflow-x-hidden relative font-sans">
      <div className="flex flex-col min-h-screen relative z-10">
        <ErrorBoundary>
          <TopNavBar
            currentScreen={currentScreen}
            onScreenChange={handleScreenChange}
            session={user}
            onLogout={logout}
          />
        </ErrorBoundary>
        <ErrorBoundary>
          <div className="flex flex-1 relative w-full px-4 md:px-10 py-6 z-10">
            <main className="flex-1 w-full transition-all duration-300">
              <AnimatePresence mode="wait">
                <motion.div
                  key={currentScreen}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -12 }}
                  transition={{ duration: 0.28, ease: 'easeOut' }}
                  className="h-full"
                >
                  {renderActiveScreen()}
                </motion.div>
              </AnimatePresence>
            </main>
          </div>
        </ErrorBoundary>
        <ErrorBoundary>
          <footer className="h-10 mt-auto flex items-center justify-center border-t border-slate-200/60 select-none px-4 bg-white">
            <p className="text-[10px] text-slate-500 font-semibold font-mono tracking-wider uppercase select-none">
              Micro-GenBI Sandbox Panel · Zero-Copy Federated Secure Environment
            </p>
          </footer>
        </ErrorBoundary>
      </div>
    </div>
    </ToastProvider>
  )
}
