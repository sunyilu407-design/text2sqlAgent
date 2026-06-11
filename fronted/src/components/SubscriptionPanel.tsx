/**
 * SubscriptionPanel — 定时任务 / 订阅管理面板
 * 对接 /api/v1/subscriptions (JWT 认证)
 */
import { useState, useEffect, useCallback, type FormEvent } from 'react'
import {
  X,
  Plus,
  Play,
  Pause,
  Trash2,
  Clock,
  Loader2,
  AlertCircle,
  CheckCircle2,
  RefreshCw,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

interface Subscription {
  id: string
  name: string
  query_description: string
  schedule: string
  last_run_at: string | null
  next_run_at: string | null
  status: 'active' | 'paused'
}

interface SubscriptionPanelProps {
  onClose?: () => void
}

interface SchedulePreset {
  label: string
  value: string
  cron: string
}

const SCHEDULE_PRESETS: SchedulePreset[] = [
  { label: '每天 09:00', value: 'daily', cron: '0 9 * * *' },
  { label: '每周一 09:00', value: 'weekly', cron: '0 9 * * 1' },
  { label: '每月1日 09:00', value: 'monthly', cron: '0 9 1 * *' },
  { label: '每6小时', value: 'every6h', cron: '0 */6 * * *' },
  { label: '自定义', value: 'custom', cron: '' },
]

function parseCron(cron: string): string {
  const parts = cron.trim().split(/\s+/)
  if (parts.length < 5) return cron

  const [minute, hour, dayOfMonth, month, dayOfWeek] = parts

  // daily
  if (minute !== '*' && hour !== '*' && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    return `每天 ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
  }
  // weekly
  if (minute !== '*' && hour !== '*' && dayOfMonth === '*' && month === '*' && dayOfWeek !== '*') {
    const dayNames = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
    const day = parseInt(dayOfWeek, 10)
    return `每周${dayNames[isNaN(day) ? 0 : day]} ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
  }
  // monthly
  if (minute !== '*' && hour !== '*' && dayOfMonth !== '*' && month === '*' && dayOfWeek === '*') {
    return `每月${dayOfMonth}日 ${hour.padStart(2, '0')}:${minute.padStart(2, '0')}`
  }
  // every N hours
  if (minute !== '*' && hour.startsWith('*/') && dayOfMonth === '*' && month === '*' && dayOfWeek === '*') {
    const interval = hour.replace('*/', '')
    return `每${interval}小时`
  }

  return cron
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

async function apiFetch<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = localStorage.getItem('mgbi_token') || ''
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  const res = await fetch(`/api/v1${path}`, { ...options, headers })
  if (res.status === 204) return undefined as unknown as T
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const body = await res.json()
      msg = body.detail || body.message || msg
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

export default function SubscriptionPanel({ onClose }: SubscriptionPanelProps) {
  const [subscriptions, setSubscriptions] = useState<Subscription[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [showForm, setShowForm] = useState(false)

  // Form state
  const [formName, setFormName] = useState('')
  const [formQuery, setFormQuery] = useState('')
  const [formSchedulePreset, setFormSchedulePreset] = useState('daily')
  const [formCustomCron, setFormCustomCron] = useState('')
  const [formSubmitting, setFormSubmitting] = useState(false)
  const [formError, setFormError] = useState('')

  // Action loading states
  const [actionLoading, setActionLoading] = useState<Record<string, boolean>>({})

  const fetchSubscriptions = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const data = await apiFetch<{ items: Subscription[] }>('/subscriptions')
      setSubscriptions(data.items ?? [])
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载订阅失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchSubscriptions()
  }, [fetchSubscriptions])

  const getCron = (): string => {
    if (formSchedulePreset === 'custom') {
      return formCustomCron.trim()
    }
    const preset = SCHEDULE_PRESETS.find(p => p.value === formSchedulePreset)
    return preset?.cron ?? ''
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setFormError('')

    const cron = getCron()
    if (!formName.trim()) {
      setFormError('请输入订阅名称')
      return
    }
    if (!formQuery.trim()) {
      setFormError('请输入查询描述')
      return
    }
    if (!cron) {
      setFormError('请选择或输入调度规则')
      return
    }

    setFormSubmitting(true)
    try {
      await apiFetch<{ id: string }>('/subscriptions', {
        method: 'POST',
        body: JSON.stringify({
          name: formName.trim(),
          query_description: formQuery.trim(),
          schedule: cron,
        }),
      })
      setFormName('')
      setFormQuery('')
      setFormSchedulePreset('daily')
      setFormCustomCron('')
      setShowForm(false)
      await fetchSubscriptions()
    } catch (err) {
      setFormError(err instanceof Error ? err.message : '创建失败')
    } finally {
      setFormSubmitting(false)
    }
  }

  const handleToggle = async (sub: Subscription) => {
    setActionLoading(prev => ({ ...prev, [sub.id]: true }))
    try {
      const newStatus = sub.status === 'active' ? 'paused' : 'active'
      const updated = await apiFetch<Subscription>(`/subscriptions/${sub.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus }),
      })
      setSubscriptions(prev =>
        prev.map(s => (s.id === sub.id ? { ...s, status: updated.status ?? newStatus } : s))
      )
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败')
    } finally {
      setActionLoading(prev => ({ ...prev, [sub.id]: false }))
    }
  }

  const handleDelete = async (sub: Subscription) => {
    if (!confirm(`确定删除订阅「${sub.name}」？`)) return
    setActionLoading(prev => ({ ...prev, [sub.id]: true }))
    try {
      await apiFetch<void>(`/subscriptions/${sub.id}`, { method: 'DELETE' })
      setSubscriptions(prev => prev.filter(s => s.id !== sub.id))
    } catch (err) {
      setError(err instanceof Error ? err.message : '删除失败')
    } finally {
      setActionLoading(prev => ({ ...prev, [sub.id]: false }))
    }
  }

  return (
    <div className="panel-elevated rounded-2xl p-6 space-y-5 w-[640px] max-h-[85vh] overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-slate-600" />
          <h2 className="text-base font-bold text-slate-900">定时订阅</h2>
          <span className="text-[11px] text-slate-400 font-medium px-2 py-0.5 bg-slate-100 rounded-full">
            {subscriptions.length} 个订阅
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={fetchSubscriptions}
            disabled={loading}
            className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-40"
            title="刷新"
          >
            <RefreshCw className={`h-4 w-4 text-slate-400 ${loading ? 'animate-spin' : ''}`} />
          </button>
          {onClose && (
            <button onClick={onClose} className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors">
              <X className="h-4 w-4 text-slate-400" />
            </button>
          )}
        </div>
      </div>

      {/* Error banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600 font-semibold"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
            <button onClick={() => setError('')} className="ml-auto p-0.5 hover:bg-red-100 rounded">
              <X className="h-3 w-3" />
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* New subscription form */}
      <AnimatePresence>
        {showForm && (
          <motion.form
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            onSubmit={handleSubmit}
            className="space-y-3 p-4 bg-slate-50/70 border border-slate-200 rounded-xl"
          >
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">
              新建订阅
            </p>

            {/* Name */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">订阅名称</label>
              <input
                type="text"
                value={formName}
                onChange={e => setFormName(e.target.value)}
                placeholder="例如：每日销售报表"
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg bg-white/60 focus:outline-none focus:border-black transition-colors"
              />
            </div>

            {/* Query description */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">查询描述</label>
              <textarea
                value={formQuery}
                onChange={e => setFormQuery(e.target.value)}
                placeholder="例如：本月各地区的销售额和订单数量"
                rows={2}
                className="w-full text-xs px-3 py-2 border border-slate-200 rounded-lg bg-white/60 focus:outline-none focus:border-black transition-colors resize-none"
              />
            </div>

            {/* Schedule */}
            <div>
              <label className="block text-xs font-semibold text-slate-700 mb-1">执行周期</label>
              <div className="flex gap-2 items-center">
                <select
                  value={formSchedulePreset}
                  onChange={e => setFormSchedulePreset(e.target.value)}
                  className="flex-1 text-xs px-3 py-2 border border-slate-200 rounded-lg bg-white/60 focus:outline-none focus:border-black transition-colors"
                >
                  {SCHEDULE_PRESETS.map(p => (
                    <option key={p.value} value={p.value}>
                      {p.label}
                    </option>
                  ))}
                </select>
                {formSchedulePreset === 'custom' && (
                  <input
                    type="text"
                    value={formCustomCron}
                    onChange={e => setFormCustomCron(e.target.value)}
                    placeholder="0 9 * * *"
                    className="flex-1 text-xs px-3 py-2 border border-slate-200 rounded-lg bg-white/60 focus:outline-none focus:border-black transition-colors font-mono"
                  />
                )}
              </div>
              {formSchedulePreset !== 'custom' && (
                <p className="mt-1 text-[10px] text-slate-400 font-mono">
                  cron: {getCron()}
                </p>
              )}
            </div>

            {/* Form error */}
            <AnimatePresence>
              {formError && (
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="text-[11px] text-red-500 font-semibold"
                >
                  {formError}
                </motion.p>
              )}
            </AnimatePresence>

            {/* Form actions */}
            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={formSubmitting}
                className="flex items-center gap-1.5 px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg text-xs font-bold transition-colors disabled:opacity-50"
              >
                {formSubmitting ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5" />
                )}
                创建订阅
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowForm(false)
                  setFormError('')
                }}
                className="px-4 py-2 border border-slate-200 rounded-lg text-xs font-semibold text-slate-600 hover:bg-slate-100 transition-colors"
              >
                取消
              </button>
            </div>
          </motion.form>
        )}
      </AnimatePresence>

      {/* New subscription button */}
      {!showForm && (
        <button
          onClick={() => setShowForm(true)}
          className="w-full flex items-center justify-center gap-2 py-2.5 border-2 border-dashed border-slate-300 rounded-xl text-xs font-bold text-slate-500 hover:border-black hover:text-black transition-all"
        >
          <Plus className="h-4 w-4" />
          新建订阅
        </button>
      )}

      {/* Subscription list */}
      {loading && subscriptions.length === 0 ? (
        <div className="flex items-center justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
        </div>
      ) : subscriptions.length === 0 ? (
        <div className="text-center py-10">
          <Clock className="h-8 w-8 text-slate-300 mx-auto mb-2" />
          <p className="text-xs text-slate-400 font-medium">暂无订阅</p>
          <p className="text-[10px] text-slate-400 mt-0.5">点击上方按钮创建第一个定时订阅</p>
        </div>
      ) : (
        <div className="space-y-2">
          {subscriptions.map(sub => (
            <div
              key={sub.id}
              className="flex items-start gap-3 p-3 bg-white/50 border border-slate-100 rounded-xl hover:bg-white/70 transition-colors"
            >
              {/* Status indicator */}
              <div className="mt-0.5">
                <div
                  className={`w-2 h-2 rounded-full ${
                    sub.status === 'active' ? 'bg-emerald-400' : 'bg-slate-300'
                  }`}
                />
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <p className="text-xs font-bold text-slate-900 truncate">{sub.name}</p>
                  <span
                    className={`shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      sub.status === 'active'
                        ? 'bg-emerald-50 text-emerald-600 border border-emerald-200'
                        : 'bg-slate-100 text-slate-500 border border-slate-200'
                    }`}
                  >
                    {sub.status === 'active' ? '活跃' : '已暂停'}
                  </span>
                </div>
                <p className="text-[11px] text-slate-500 font-medium mb-1.5 line-clamp-1">
                  {sub.query_description}
                </p>
                <div className="flex items-center gap-4 text-[10px] text-slate-400 font-mono">
                  <span title="Cron 规则">{sub.schedule}</span>
                  <span title="上次运行">
                    上次: <span className="font-medium">{formatDateTime(sub.last_run_at)}</span>
                  </span>
                  <span title="下次运行">
                    下次: <span className="font-medium">{formatDateTime(sub.next_run_at)}</span>
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => handleToggle(sub)}
                  disabled={actionLoading[sub.id]}
                  className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors disabled:opacity-40"
                  title={sub.status === 'active' ? '暂停' : '恢复'}
                >
                  {actionLoading[sub.id] ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />
                  ) : sub.status === 'active' ? (
                    <Pause className="h-3.5 w-3.5 text-slate-500" />
                  ) : (
                    <Play className="h-3.5 w-3.5 text-slate-500" />
                  )}
                </button>
                <button
                  onClick={() => handleDelete(sub)}
                  disabled={actionLoading[sub.id]}
                  className="p-1.5 hover:bg-red-50 rounded-lg transition-colors disabled:opacity-40"
                  title="删除"
                >
                  <Trash2 className="h-3.5 w-3.5 text-red-400" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Cron legend */}
      {subscriptions.length > 0 && (
        <div className="pt-2 border-t border-slate-100">
          <p className="text-[10px] text-slate-400 font-medium leading-relaxed">
            <span className="font-mono">cron 格式:</span>{' '}
            分 时 日 月 周 &nbsp;|&nbsp; 0 9 * * * = 每天09:00 &nbsp;|&nbsp; 0 */6 * * * = 每6小时
          </p>
        </div>
      )}
    </div>
  )
}
