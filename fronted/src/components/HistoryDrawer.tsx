/**
 * Query History Drawer — 侧边抽屉，展示历史查询记录
 * 对接 /api/v1/history
 */
import { useState, useEffect, type MouseEvent } from 'react'
import {
  Clock,
  Search,
  Star,
  Copy,
  Play,
  ChevronRight,
  Loader2,
  Database,
  X,
  Trash2,
  BarChart2,
  GitBranch,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { queryApi } from '../api'
import SQLVersionPanel from './SQLVersionPanel'

interface HistoryItem {
  id: string
  naturalQuery: string
  sql: string
  intent: string
  status: string
  executionTimeMs: number
  createdAt: string
}

interface HistoryDrawerProps {
  isOpen: boolean
  onClose: () => void
  onLoadQuery: (item: HistoryItem) => void
}

export default function HistoryDrawer({ isOpen, onClose, onLoadQuery }: HistoryDrawerProps) {
  const [items, setItems] = useState<HistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [searchText, setSearchText] = useState('')
  const [activeFilter, setActiveFilter] = useState<'all' | 'success' | 'blocked' | 'failed'>('all')
  const [showVersionPanel, setShowVersionPanel] = useState(false)
  const [versionQuestion, setVersionQuestion] = useState('')

  useEffect(() => {
    if (isOpen) {
      setLoading(true)
      queryApi.getHistory({ limit: 50 })
        .then(({ items: itms }) => setItems(itms))
        .catch(() => setItems([]))
        .finally(() => setLoading(false))
    }
  }, [isOpen])

  const filtered = items.filter(item => {
    const matchSearch = !searchText ||
      item.naturalQuery.toLowerCase().includes(searchText.toLowerCase()) ||
      item.sql.toLowerCase().includes(searchText.toLowerCase())
    const matchFilter = activeFilter === 'all' || item.status === activeFilter
    return matchSearch && matchFilter
  })

  const handleCopySQL = (e: MouseEvent, sql: string) => {
    e.stopPropagation()
    navigator.clipboard.writeText(sql)
  }

  const handleReRun = (e: MouseEvent, item: HistoryItem) => {
    e.stopPropagation()
    onLoadQuery(item)
  }

  const statusColor = (status: string) => {
    if (status === 'success') return 'bg-emerald-100 text-emerald-600'
    if (status === 'blocked') return 'bg-amber-100 text-amber-600'
    return 'bg-red-100 text-red-600'
  }

  const statusLabel = (status: string) => {
    if (status === 'success') return '成功'
    if (status === 'blocked') return '阻断'
    return '失败'
  }

  const formatTime = (iso: string) => {
    try {
      const d = new Date(iso)
      const now = new Date()
      const diff = now.getTime() - d.getTime()
      if (diff < 60000) return '刚刚'
      if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`
      return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
    } catch {
      return '—'
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/20 z-40"
            onClick={onClose}
          />

          {/* Drawer */}
          <motion.aside
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 w-96 bg-white/95 backdrop-blur-xl border-l border-slate-200 shadow-2xl z-50 flex flex-col"
          >
            {/* Header */}
            <div className="px-4 py-3 border-b border-slate-200 flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2">
                <Clock className="h-4 w-4 text-slate-700" />
                <h2 className="text-sm font-bold text-slate-900">查询历史</h2>
                <span className="text-[10px] text-slate-400 font-mono">{items.length} 条</span>
              </div>
              <button
                onClick={onClose}
                className="p-1 hover:bg-slate-100 rounded-md transition-colors"
              >
                <X className="h-4 w-4 text-slate-500" />
              </button>
            </div>

            {/* Search + Filter */}
            <div className="px-4 py-3 border-b border-slate-100 space-y-2 shrink-0">
              <div className="relative">
                <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                <input
                  value={searchText}
                  onChange={e => setSearchText(e.target.value)}
                  placeholder="搜索历史查询..."
                  className="w-full text-xs pl-8 pr-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-black placeholder-slate-400"
                />
              </div>
              <div className="flex gap-1 flex-wrap">
                {(['all', 'success', 'blocked', 'failed'] as const).map(f => (
                  <button
                    key={f}
                    onClick={() => setActiveFilter(f)}
                    className={`px-2 py-1 rounded-md text-[10px] font-bold transition-colors ${
                      activeFilter === f
                        ? 'bg-indigo-500 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-indigo-50 hover:text-indigo-600'
                    }`}
                  >
                    {f === 'all' ? '全部' : statusLabel(f)}
                  </button>
                ))}
                <div className="flex-1" />
                <button
                  onClick={() => setShowVersionPanel(v => !v)}
                  className={`px-2 py-1 rounded-md text-[10px] font-bold transition-colors flex items-center gap-1 ${
                    showVersionPanel
                      ? 'bg-indigo-500 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-indigo-50 hover:text-indigo-600'
                  }`}
                >
                  <GitBranch className="h-3 w-3" />
                  版本
                </button>
              </div>
            </div>

            <AnimatePresence>
              {showVersionPanel && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: 'auto', opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  className="overflow-hidden"
                >
                  <div className="px-4 py-3 border-b border-slate-100">
                    <input
                      value={versionQuestion}
                      onChange={e => setVersionQuestion(e.target.value)}
                      placeholder="输入查询问题以加载相关版本..."
                      className="w-full text-xs px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none focus:border-indigo-400 placeholder-slate-400"
                    />
                  </div>
                  {versionQuestion && (
                    <SQLVersionPanel
                      question={versionQuestion}
                      onRollback={(sql) => {
                        onLoadQuery({ id: 'rolled-back', naturalQuery: versionQuestion, sql, intent: '', status: 'success', executionTimeMs: 0, createdAt: '' })
                        setShowVersionPanel(false)
                      }}
                      onClose={() => setShowVersionPanel(false)}
                    />
                  )}
                </motion.div>
              )}
            </AnimatePresence>

            {/* List */}
            <div className="flex-1 overflow-y-auto">
              {loading ? (
                <div className="flex items-center justify-center h-32">
                  <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
                </div>
              ) : filtered.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-32 text-slate-400 text-xs text-center px-4">
                  <Clock className="h-8 w-8 mb-2 text-slate-300" />
                  <p>暂无查询历史</p>
                  <p className="text-[10px] mt-1">在查询工作台发起查询后会显示在这里</p>
                </div>
              ) : (
                <div className="divide-y divide-slate-100">
                  {filtered.map(item => (
                    <div
                      key={item.id}
                      onClick={() => onLoadQuery(item)}
                      className="px-4 py-3 hover:bg-slate-50 cursor-pointer group transition-colors"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold text-slate-800 line-clamp-2 leading-snug">
                            {item.naturalQuery}
                          </p>
                          <div className="flex items-center gap-2 mt-1.5">
                            <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${statusColor(item.status)}`}>
                              {statusLabel(item.status)}
                            </span>
                            <span className="text-[10px] text-slate-400 font-mono">
                              {item.executionTimeMs}ms
                            </span>
                            <span className="text-[10px] text-slate-400">
                              {formatTime(item.createdAt)}
                            </span>
                          </div>
                          {/* SQL preview */}
                          <div className="mt-1.5 text-[10px] font-mono text-slate-500 bg-slate-50 rounded px-2 py-1 line-clamp-2">
                            {item.sql || '—'}
                          </div>
                        </div>

                        {/* Action buttons */}
                        <div className="flex flex-col gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
                          <button
                            onClick={e => { e.stopPropagation(); onLoadQuery(item) }}
                            title="重新运行"
                            className="p-1 bg-indigo-500 text-white rounded hover:bg-indigo-600 transition-colors"
                          >
                            <Play className="h-3 w-3 fill-white" />
                          </button>
                          <button
                            onClick={e => handleCopySQL(e, item.sql)}
                            title="复制SQL"
                            className="p-1 bg-slate-100 rounded hover:bg-slate-200 transition-colors"
                          >
                            <Copy className="h-3 w-3 text-slate-600" />
                          </button>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  )
}
