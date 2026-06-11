/**
 * AnomalyPanel — 异常检测可视化面板
 * 对接 /api/v1/query/anomaly-detect
 * 支持 Z-Score 和 IQR 两种检测方法，可视化展示异常数据点
 */
import { useState } from 'react'
import { motion } from 'motion/react'
import {
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Activity,
  Loader2,
  X,
  ChevronDown,
  ChevronUp,
  ShieldAlert,
} from 'lucide-react'
import { anomalyApi } from '../api'
import type { AnomalyRecord, AnomalyResult } from '../api'

type DetectionMethod = 'zscore' | 'iqr'

const SEVERITY_CONFIG = {
  critical: { color: 'text-red-600', bg: 'bg-red-50', border: 'border-red-300', label: '严重', icon: ShieldAlert },
  high:     { color: 'text-orange-600', bg: 'bg-orange-50', border: 'border-orange-300', label: '高', icon: AlertTriangle },
  medium:   { color: 'text-yellow-600', bg: 'bg-yellow-50', border: 'border-yellow-300', label: '中', icon: Activity },
  low:      { color: 'text-blue-600', bg: 'bg-blue-50', border: 'border-blue-300', label: '低', icon: TrendingUp },
}

interface AnomalyPanelProps {
  data: Record<string, unknown>[]
  columns: string[]
  onClose: () => void
}

export default function AnomalyPanel({ data, columns, onClose }: AnomalyPanelProps) {
  const [method, setMethod] = useState<DetectionMethod>('zscore')
  const [threshold, setThreshold] = useState(3.0)
  const [result, setResult] = useState<AnomalyResult | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [expanded, setExpanded] = useState<number | null>(null)

  const numericColumns = columns.filter(col => {
    if (data.length === 0) return false
    const val = data[0][col]
    return typeof val === 'number'
  })

  const handleDetect = async () => {
    if (numericColumns.length === 0) return
    setIsLoading(true)
    try {
      const res = await anomalyApi.detect(data, numericColumns, method, threshold)
      setResult(res)
    } catch {
      setResult({ anomalies: [], summary: {}, severity_counts: {} })
    } finally {
      setIsLoading(false)
    }
  }

  const severities = (result?.severity_counts ?? {}) as Record<string, number>
  const total = Object.values(severities).reduce((a, b) => a + b, 0)

  return (
    <div className="panel rounded-xl bg-white/80 backdrop-blur shadow-xl border border-white/20 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/20 bg-white/40 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <AlertTriangle className="h-4 w-4 text-amber-500" />
          <h3 className="text-xs font-bold text-gray-800">异常检测</h3>
          {result && (
            <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
              total === 0 ? 'bg-emerald-50 text-emerald-600' : 'bg-red-50 text-red-600'
            }`}>
              {total === 0 ? '无异常' : `${total} 个异常`}
            </span>
          )}
        </div>
        <button onClick={onClose} className="p-1 hover:bg-black/5 rounded">
          <X className="h-4 w-4 text-gray-500" />
        </button>
      </div>

      {/* Controls */}
      <div className="px-4 py-3 border-b border-white/20 bg-white/20 flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">方法</label>
          <select
            value={method}
            onChange={e => setMethod(e.target.value as DetectionMethod)}
            className="text-xs px-2 py-1 rounded border border-gray-200 bg-white focus:outline-none focus:border-indigo-400"
          >
            <option value="zscore">Z-Score</option>
            <option value="iqr">IQR</option>
          </select>
        </div>

        {method === 'zscore' && (
          <div className="flex items-center gap-1.5">
            <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">阈值</label>
            <input
              type="number"
              min={1}
              max={5}
              step={0.5}
              value={threshold}
              onChange={e => setThreshold(parseFloat(e.target.value) || 3.0)}
              className="w-16 text-xs px-2 py-1 rounded border border-gray-200 bg-white focus:outline-none focus:border-indigo-400"
            />
            <span className="text-[10px] text-gray-400">σ</span>
          </div>
        )}

        <div className="flex items-center gap-1.5">
          <label className="text-[10px] font-semibold text-gray-500 uppercase tracking-wide">检测列</label>
          <span className="text-[10px] text-indigo-600 font-mono font-bold">
            {numericColumns.length > 0 ? numericColumns.join(', ') : '无可数值列'}
          </span>
        </div>

        <button
          onClick={handleDetect}
          disabled={isLoading || numericColumns.length === 0}
          className="ml-auto px-3 py-1.5 bg-amber-500 text-white text-[10px] font-bold rounded-lg hover:bg-amber-600 transition-colors disabled:opacity-50 flex items-center gap-1.5"
        >
          {isLoading ? <Loader2 className="h-3 w-3 animate-spin" /> : <Activity className="h-3 w-3" />}
          检测
        </button>
      </div>

      {/* Severity Summary */}
      {result && (
        <div className="px-4 py-2 border-b border-white/20 bg-white/10 flex items-center gap-3">
          {Object.entries(severities).map(([sev, count]) => {
            if (count === 0) return null
            const cfg = SEVERITY_CONFIG[sev as keyof typeof SEVERITY_CONFIG]
            const Icon = cfg.icon
            return (
              <div key={sev} className={`flex items-center gap-1 ${cfg.bg} border ${cfg.border} rounded-full px-2 py-0.5`}>
                <Icon className={`h-3 w-3 ${cfg.color}`} />
                <span className={`text-[10px] font-bold ${cfg.color}`}>{cfg.label} ×{count}</span>
              </div>
            )
          })}
        </div>
      )}

      {/* Anomaly List */}
      <div className="divide-y divide-gray-100/50 max-h-64 overflow-y-auto">
        {!result ? (
          <div className="flex flex-col items-center justify-center py-8 text-xs text-gray-400">
            <Activity className="h-8 w-8 mb-2 opacity-30" />
            <p>点击"检测"按钮开始异常分析</p>
            <p className="text-[10px] mt-1">Z-Score: 超过阈值 σ 即标记 | IQR: 超出四分位范围即标记</p>
          </div>
        ) : result.anomalies.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-8 text-xs text-emerald-500">
            <ShieldAlert className="h-8 w-8 mb-2" />
            <p className="font-bold">数据表现正常，未检测到异常</p>
          </div>
        ) : (
          result.anomalies.map((a, idx) => {
            const cfg = SEVERITY_CONFIG[a.severity as keyof typeof SEVERITY_CONFIG] ?? SEVERITY_CONFIG.low
            const Icon = cfg.icon
            const isOpen = expanded === idx

            return (
              <div key={idx} className={`px-4 py-2.5 hover:bg-white/30 transition-colors ${cfg.bg}`}>
                <div className="flex items-start gap-2">
                  <Icon className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${cfg.color}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className={`text-[10px] font-bold uppercase ${cfg.color}`}>{cfg.label}</span>
                      <span className="text-[10px] font-mono text-gray-600">
                        行 #{a.row_index + 1}
                      </span>
                      <span className="text-[10px] font-mono font-bold text-gray-800 bg-white/60 px-1.5 py-0.5 rounded border border-gray-200">
                        {a.column}
                      </span>
                      <span className="text-[10px] font-mono text-gray-500">
                        值: <span className="font-bold text-gray-800">{typeof a.value === 'number' ? a.value.toLocaleString() : a.value}</span>
                      </span>
                      <span className="text-[10px] text-gray-400">
                        期望: [{a.expected_range[0].toLocaleString()}, {a.expected_range[1].toLocaleString()}]
                      </span>
                      <span className="text-[10px] text-gray-400 font-mono ml-auto">
                        score: {a.score}
                      </span>
                    </div>

                    {/* Inline context */}
                    {data[a.row_index] && (
                      <div className="mt-1 text-[10px] text-gray-400 font-mono">
                        行数据: {Object.entries(data[a.row_index]).slice(0, 4).map(([k, v]) => `${k}=${v}`).join(' | ')}
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
