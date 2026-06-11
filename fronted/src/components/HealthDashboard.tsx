/**
 * HealthDashboard — 系统健康状态面板
 * 对接 /api/v1/health（无需认证）
 */
import { useState, useEffect } from 'react'
import {
  Activity,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Database,
  Cpu,
  HardDrive,
  Wifi,
  RefreshCw,
  Loader2,
  Clock,
  TrendingUp,
} from 'lucide-react'

interface HealthCheck {
  status: string
  latency_ms?: number
  message?: string
}

interface SystemHealth {
  status: string
  version: string
  checks: Record<string, HealthCheck>
}

function statusIcon(s: string) {
  if (s === 'healthy') return <CheckCircle className="h-4 w-4 text-emerald-500" />
  if (s === 'unhealthy') return <XCircle className="h-4 w-4 text-red-500" />
  return <AlertTriangle className="h-4 w-4 text-amber-500" />
}

function statusColor(s: string) {
  if (s === 'healthy') return 'bg-emerald-50 border-emerald-200 text-emerald-700'
  if (s === 'unhealthy') return 'bg-red-50 border-red-200 text-red-700'
  return 'bg-amber-50 border-amber-200 text-amber-700'
}

function statusBadge(s: string) {
  if (s === 'healthy') return 'bg-emerald-100 text-emerald-700'
  if (s === 'unhealthy') return 'bg-red-100 text-red-700'
  return 'bg-amber-100 text-amber-700'
}

export default function HealthDashboard() {
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [error, setError] = useState('')

  const fetchHealth = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await fetch('/api/v1/health')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data: SystemHealth = await res.json()
      setHealth(data)
      setLastUpdated(new Date())
    } catch (err) {
      setError(err instanceof Error ? err.message : '获取失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchHealth()
    // Auto-refresh every 30s
    const interval = setInterval(fetchHealth, 30000)
    return () => clearInterval(interval)
  }, [])

  const components: { name: string; status: string; latency_ms?: number; message?: string }[] =
    health?.checks
      ? Object.entries(health.checks as Record<string, HealthCheck>).map(([name, check]) => ({
          name,
          status: check.status,
          latency_ms: check.latency_ms,
          message: check.message,
        }))
      : []

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-4xl font-bold text-slate-900">系统健康状态</h1>
          <p className="text-sm text-slate-500 mt-1">
            实时监控系统各组件运行状态
          </p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-[11px] text-slate-400 font-mono">
              <Clock className="inline h-3 w-3 mr-1" />
              {lastUpdated.toLocaleTimeString('zh-CN')}
            </span>
          )}
          <button
            onClick={fetchHealth}
            disabled={loading}
            className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl text-xs font-bold transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} />
            刷新
          </button>
        </div>
      </div>

      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600 font-semibold">
          {error} — <button onClick={fetchHealth} className="underline">重试</button>
        </div>
      )}

      {/* Overall status banner */}
      <div className={`rounded-2xl p-6 border flex items-center gap-4 ${
        health?.status === 'healthy' ? 'bg-emerald-50 border-emerald-200' :
        health?.status === 'unhealthy' ? 'bg-red-50 border-red-200' :
        'bg-amber-50 border-amber-200'
      }`}>
        <div className={`w-14 h-14 rounded-2xl flex items-center justify-center ${
          health?.status === 'healthy' ? 'bg-emerald-100' :
          health?.status === 'unhealthy' ? 'bg-red-100' : 'bg-amber-100'
        }`}>
          {health ? statusIcon(health.status) : <Loader2 className="h-6 w-6 animate-spin text-slate-400" />}
        </div>
        <div>
          <h2 className="text-xl font-bold text-slate-900">
            {health ? (
              health.status === 'healthy' ? '所有系统运行正常' :
              health.status === 'unhealthy' ? '系统存在故障' : '系统性能降级'
            ) : '正在检测...'}
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            Micro-GenBI v{health?.version || '—'} · 每 30 秒自动刷新
          </p>
        </div>
        {health && (
          <div className="ml-auto flex gap-2">
            {components.map(c => (
              <span key={c.name} className={`text-[10px] font-bold px-2 py-1 rounded-full ${statusBadge(c.status)}`}>
                {c.name} {c.status === 'healthy' ? '✓' : '!'}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Component grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {loading && !health ? (
          Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="panel rounded-xl p-5 h-32 animate-pulse bg-slate-100" />
          ))
        ) : components.length === 0 ? (
          <div className="col-span-2 text-center py-12 text-slate-400 text-sm">
            暂无组件数据
          </div>
        ) : components.map(comp => (
          <div key={comp.name} className={`panel rounded-xl p-5 border ${statusColor(comp.status)}`}>
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                {comp.name === 'database' && <Database className="h-5 w-5" />}
                {comp.name === 'llm' && <Cpu className="h-5 w-5" />}
                {comp.name === 'disk' && <HardDrive className="h-5 w-5" />}
                {comp.name === 'network' && <Wifi className="h-5 w-5" />}
                {comp.name === 'memory' && <Activity className="h-5 w-5" />}
                {!['database', 'llm', 'disk', 'network', 'memory'].includes(comp.name) && (
                  <Activity className="h-5 w-5" />
                )}
                <span className="text-sm font-bold capitalize">{comp.name}</span>
              </div>
              {statusIcon(comp.status)}
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-slate-500">状态</span>
                <span className="font-bold capitalize">{comp.status}</span>
              </div>
              {comp.latency_ms !== undefined && (
                <div className="flex justify-between text-xs">
                  <span className="text-slate-500">延迟</span>
                  <span className="font-mono font-bold">{comp.latency_ms}ms</span>
                </div>
              )}
              {comp.message && (
                <div className="text-[11px] text-slate-500 leading-relaxed mt-1">
                  {comp.message}
                </div>
              )}
            </div>

            {/* Latency bar */}
            {comp.latency_ms !== undefined && (
              <div className="mt-3">
                <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                  <div
                    className={`h-1.5 rounded-full transition-all ${
                      comp.latency_ms < 100 ? 'bg-emerald-500' :
                      comp.latency_ms < 500 ? 'bg-amber-500' : 'bg-red-500'
                    }`}
                    style={{ width: `${Math.min(comp.latency_ms / 5, 100)}%` }}
                  />
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Tips */}
      <div className="panel rounded-xl p-4 border border-slate-200">
        <div className="flex items-start gap-3">
          <TrendingUp className="h-4 w-4 text-slate-500 mt-0.5" />
          <div className="text-xs text-slate-500 leading-relaxed">
            <strong className="text-slate-700">状态说明：</strong>
            <ul className="mt-1 space-y-0.5">
              <li>· <span className="text-emerald-600 font-semibold">Healthy</span> — 组件正常运行，延迟在正常范围内</li>
              <li>· <span className="text-amber-600 font-semibold">Degraded</span> — 组件可用但性能下降，建议关注</li>
              <li>· <span className="text-red-600 font-semibold">Unhealthy</span> — 组件不可用，请立即处理</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}
