/**
 * SQLVersionPanel — SQL 版本管理面板
 * 支持版本列表、版本对比、回滚功能
 */
import { useState } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import {
  X,
  GitBranch,
  Clock,
  ChevronDown,
  ChevronUp,
  ArrowLeft,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Loader2,
  Plus,
} from 'lucide-react'
import { useSQLVersions, useCompareVersions, useRollbackVersion } from '../hooks/useQueries'
import type { SQLVersion, SQLVersionDiff } from '../api'

interface SQLVersionPanelProps {
  question: string
  onRollback: (sql: string) => void
  onClose: () => void
}

export default function SQLVersionPanel({ question, onRollback, onClose }: SQLVersionPanelProps) {
  const { data, isLoading } = useSQLVersions(question)
  const rollback = useRollbackVersion()

  const [selectedVersions, setSelectedVersions] = useState<[number, number]>([0, 0])
  const [showDiff, setShowDiff] = useState(false)
  const [expandedVersion, setExpandedVersion] = useState<number | null>(null)

  const { data: diff, isLoading: isComparing } = useCompareVersions(
    selectedVersions[0] ?? 0,
    selectedVersions[1] ?? 0
  )

  const versions: SQLVersion[] = data?.items ?? []

  const handleSelect = (id: number) => {
    setSelectedVersions(prev => {
      if (prev[0] === 0) return [id, prev[1]]
      if (prev[1] === 0) return [id === prev[0] ? id : prev[0], id]
      return [id, 0]
    })
    setShowDiff(false)
  }

  const handleCompare = () => {
    if (selectedVersions[0] && selectedVersions[1]) {
      setShowDiff(true)
    }
  }

  const handleRollback = async (version: SQLVersion) => {
    const result = await rollback.mutateAsync(version.id)
    onRollback(result.sql)
  }

  const diffData = showDiff ? diff : null

  return (
    <div className="panel rounded-xl bg-white/80 backdrop-blur shadow-xl border border-white/20 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-white/20 flex items-center justify-between bg-white/40">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-indigo-500" />
          <h3 className="text-xs font-bold text-gray-800">SQL 版本管理</h3>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-black/5 rounded">
          <X className="h-4 w-4 text-gray-500" />
        </button>
      </div>

      <div className="divide-y divide-gray-100">
        {isLoading ? (
          <div className="flex items-center gap-2 px-4 py-6 text-xs text-gray-400 justify-center">
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
            加载版本历史...
          </div>
        ) : versions.length === 0 ? (
          <div className="flex items-center gap-2 px-4 py-6 text-xs text-gray-400 justify-center">
            <GitBranch className="h-3.5 w-3.5" />
            暂无版本记录
          </div>
        ) : (
          versions.map((v) => (
            <div key={v.id} className="px-4 py-3 hover:bg-white/40 transition-colors">
              {/* Version Row */}
              <div className="flex items-start gap-3">
                <button
                  onClick={() => handleSelect(v.id)}
                  className={`mt-0.5 shrink-0 w-4 h-4 rounded border-2 flex items-center justify-center transition-colors ${
                    selectedVersions.includes(v.id)
                      ? 'border-indigo-500 bg-indigo-500'
                      : 'border-gray-300 hover:border-indigo-300'
                  }`}
                >
                  {selectedVersions.includes(v.id) && (
                    <CheckCircle2 className="h-3 w-3 text-white" />
                  )}
                </button>

                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold bg-indigo-50 text-indigo-600 px-1.5 py-0.5 rounded">
                      v{v.id}
                    </span>
                    <span className="text-[10px] text-gray-400 font-medium flex items-center gap-0.5">
                      <Clock className="h-3 w-3" />
                      {v.created_at ? new Date(v.created_at).toLocaleString('zh-CN') : ''}
                    </span>
                  </div>

                  <p className="text-[10px] text-gray-500 mt-0.5 truncate">
                    {v.question}
                  </p>

                  {v.change_summary && (
                    <p className="text-[10px] text-gray-400 mt-0.5 italic">
                      {v.change_summary}
                    </p>
                  )}

                  <AnimatePresence>
                    {expandedVersion === v.id && (
                      <motion.pre
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="mt-2 text-[10px] font-mono bg-gray-50 rounded-lg p-2 text-gray-700 overflow-x-auto whitespace-pre-wrap break-all"
                      >
                        {v.sql}
                      </motion.pre>
                    )}
                  </AnimatePresence>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  <button
                    onClick={() => setExpandedVersion(expandedVersion === v.id ? null : v.id)}
                    className="p-1 hover:bg-black/5 rounded text-gray-400"
                    title="查看 SQL"
                  >
                    {expandedVersion === v.id ? (
                      <ChevronUp className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronDown className="h-3.5 w-3.5" />
                    )}
                  </button>
                  <button
                    onClick={() => handleRollback(v)}
                    disabled={rollback.isPending}
                    className="p-1 hover:bg-black/5 rounded text-gray-400 hover:text-indigo-500 disabled:opacity-40"
                    title="回滚到此版本"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Compare Actions */}
      {versions.length > 1 && (
        <div className="px-4 py-3 border-t border-white/20 bg-white/40 flex items-center gap-2">
          {selectedVersions[0] !== 0 && selectedVersions[1] !== 0 ? (
            <button
              onClick={handleCompare}
              disabled={isComparing}
              className="px-3 py-1.5 bg-indigo-500 text-white text-[10px] font-semibold rounded-lg hover:bg-indigo-600 transition-colors disabled:opacity-50 flex items-center gap-1.5"
            >
              {isComparing ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
              对比两个版本
            </button>
          ) : (
            <p className="text-[10px] text-gray-400">
              选择两个版本以对比
            </p>
          )}
        </div>
      )}

      {/* Diff View */}
      <AnimatePresence>
        {diffData && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="border-t border-white/20 overflow-hidden"
          >
            <DiffView diff={diffData} />
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function DiffView({ diff }: { diff: SQLVersionDiff }) {
  return (
    <div className="px-4 py-3 bg-gray-50 space-y-2">
      <h4 className="text-[10px] font-bold text-gray-700 uppercase tracking-wide">版本差异</h4>
      {diff.summary && (
        <p className="text-[10px] text-gray-600">{diff.summary}</p>
      )}
      <div className="grid grid-cols-2 gap-2">
        {diff.added_tables?.length > 0 && (
          <DiffBadge label="新增表" items={diff.added_tables} color="green" />
        )}
        {diff.removed_tables?.length > 0 && (
          <DiffBadge label="移除表" items={diff.removed_tables} color="red" />
        )}
        {diff.modified_columns?.length > 0 && (
          <DiffBadge label="修改列" items={diff.modified_columns} color="blue" />
        )}
        {diff.modified_where && (
          <span className="text-[10px] font-semibold bg-yellow-100 text-yellow-700 px-2 py-1 rounded">
            WHERE 子句有变化
          </span>
        )}
      </div>
    </div>
  )
}

function DiffBadge({ label, items, color }: { label: string; items: string[]; color: 'green' | 'red' | 'blue' }) {
  const colorMap = {
    green: 'bg-green-50 text-green-700 border-green-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
  }
  return (
    <div className={`text-[10px] font-semibold px-2 py-1 rounded border ${colorMap[color]}`}>
      <span className="uppercase">{label}: </span>
      {items.join(', ')}
    </div>
  )
}
