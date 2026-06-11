/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 * 查询工作台 — 对接 /api/v1/schema 和 /api/v1/query
 */
import { useState, useEffect } from 'react'
import {
  Plus,
  Search,
  Trash2,
  Play,
  TableProperties,
  Eye,
  Compass,
  Copy,
  Share2,
  Database,
  CheckSquare,
  Square,
  Sparkles,
  RefreshCw,
  AlertCircle,
  Loader2,
  ServerOff,
  ChevronDown,
  Clock,
  Download,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { queryApi } from '../api'
import type { DatabaseSource as ApiDatabaseSource, SchemaTable, QueryResult, ColumnInfo } from '../api'
import HistoryDrawer from './HistoryDrawer'
import { useToast } from '../context/ToastContext'
import ExportPanel from './ExportPanel'
import StreamingQueryPanel from './StreamingQueryPanel'
import SchemaSearchModal from './SchemaSearchModal'
import ChartPickerPanel from './ChartPickerPanel'
import ResultInsightPanel from './ResultInsightPanel'

// 兼容前端类型
interface LocalColumn {
  name: string
  type: string
  isPrimary?: boolean
  isChecked?: boolean
}
interface LocalTable {
  name: string
  type: string
  columns: LocalColumn[]
}
interface LocalDB {
  id: string
  name: string
  status: 'active' | 'syncing' | 'offline'
  tables: LocalTable[]
}

function normalizeColumn(col: { name: string; type: string; primary_key?: boolean; isPrimaryKey?: boolean; primaryKey?: boolean }): LocalColumn {
  return {
    name: col.name,
    type: col.type,
    isPrimary: !!(col.primary_key || col.isPrimaryKey || col.primaryKey),
  }
}

function normalizeDatabase(apiDb: ApiDatabaseSource): LocalDB {
  return {
    id: apiDb.id || apiDb.name,
    name: apiDb.name || apiDb.display_name || apiDb.id,
    status: (apiDb.status === 'online' || apiDb.status === 'active') ? 'active' : apiDb.status === 'syncing' ? 'syncing' : 'offline',
    tables: (apiDb.tables || []).map((t: SchemaTable) => ({
      name: t.name,
      type: t.description || t.display_name || '',
      columns: (t.columns || []).map(normalizeColumn),
    })),
  }
}

const FALLBACK_DB: LocalDB[] = [
  {
    id: 'db1',
    name: 'Orders_DB_Prod',
    status: 'active',
    tables: [
      { name: 'dim_customers', type: 'customers', columns: [{ name: 'customer_id', type: 'VARCHAR', isPrimary: true }, { name: 'customer_name', type: 'VARCHAR' }, { name: 'country', type: 'VARCHAR' }] },
      { name: 'fct_orders', type: 'orders', columns: [{ name: 'order_id', type: 'VARCHAR', isPrimary: true, isChecked: true }, { name: 'customer_id', type: 'VARCHAR', isChecked: true }, { name: 'order_date', type: 'TIMESTAMP', isChecked: false }, { name: 'total_amount', type: 'DECIMAL', isChecked: true }] },
      { name: 'fct_order_items', type: 'order_items', columns: [{ name: 'item_id', type: 'VARCHAR', isPrimary: true }, { name: 'order_id', type: 'VARCHAR' }, { name: 'qty', type: 'INTEGER' }] },
    ],
  },
  {
    id: 'db2',
    name: 'Financial_DW',
    status: 'active',
    tables: [
      { name: 'fct_payments', type: 'payments', columns: [{ name: 'payment_id', type: 'VARCHAR', isPrimary: true }, { name: 'order_id', type: 'VARCHAR', isChecked: true }, { name: 'payment_status', type: 'VARCHAR', isChecked: true }, { name: 'payment_method', type: 'VARCHAR', isChecked: true }] },
      { name: 'dim_currency', type: 'currency', columns: [{ name: 'currency_code', type: 'VARCHAR' }, { name: 'exchange_rate', type: 'DECIMAL' }] },
    ],
  },
  {
    id: 'db3',
    name: 'Logistics_API',
    status: 'syncing',
    tables: [],
  },
]

export default function QueryWorkbenchView() {
  const { error: toastError } = useToast()
  const [databases, setDatabases] = useState<LocalDB[]>(FALLBACK_DB)
  const [schemaLoading, setSchemaLoading] = useState(false)
  const [schemaError, setSchemaError] = useState('')

  const [activeTables, setActiveTables] = useState<string[]>(['fct_orders', 'fct_payments'])
  const [searchTableText, setSearchTableText] = useState('')
  const [isRunning, setIsRunning] = useState(false)
  const [copied, setCopied] = useState(false)

  const [checkedColumns, setCheckedColumns] = useState<Record<string, boolean>>({
    order_id: true, customer_id: true, total_amount: true,
    payment_status: true, payment_method: true,
  })

  const [previewSQL, setPreviewSQL] = useState('')

  const [queryResult, setQueryResult] = useState<QueryResult | null>(null)
  const [queryError, setQueryError] = useState('')
  const [isHistoryOpen, setIsHistoryOpen] = useState(false)
  const [isExportOpen, setIsExportOpen] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [activeTaskId, setActiveTaskId] = useState('')
  const [isSchemaSearchOpen, setIsSchemaSearchOpen] = useState(false)
  const [showChartPicker, setShowChartPicker] = useState(false)

  // 启动时拉取 Schema
  useEffect(() => {
    setSchemaLoading(true)
    queryApi.getSchema()
      .then(({ databases: dbs }) => {
        if (dbs && dbs.length > 0) {
          setDatabases(dbs.map(normalizeDatabase))
        }
      })
      .catch(() => {
        // 静默使用 fallback 数据，不阻断用户操作
      })
      .finally(() => setSchemaLoading(false))
  }, [])

  // 当切换活动表时，重置列选中状态
  useEffect(() => {
    const nextChecked: Record<string, boolean> = {}
    for (const db of databases) {
      for (const tbl of db.tables) {
        if (activeTables.includes(tbl.name)) {
          for (const col of tbl.columns) {
            nextChecked[col.name] = col.isChecked ?? false
          }
        }
      }
    }
    if (Object.keys(nextChecked).length > 0) {
      setCheckedColumns(prev => ({ ...nextChecked, ...prev }))
    }
  }, [activeTables])

  const toggleColumnSelection = (colName: string) => {
    setCheckedColumns(prev => ({ ...prev, [colName]: !prev[colName] }))
  }

  // Fetch preview SQL when checked columns change
  useEffect(() => {
    const selectedFields: string[] = Object.entries(checkedColumns)
      .filter(([, v]) => v)
      .map(([k]) => k)
    if (selectedFields.length === 0) { setPreviewSQL('-- 请先选择要查询的列'); return }
    const question = `SELECT ${selectedFields.join(', ')} FROM fct_orders o LEFT JOIN fct_payments p ON o.order_id = p.order_id`
    queryApi.previewSQL(question)
      .then(r => setPreviewSQL(r.sql || question + '\nLIMIT 100;'))
      .catch(() => setPreviewSQL(question + '\nLIMIT 100;'))
  }, [checkedColumns])

  const handleRunQuery = async () => {
    if (isRunning) return
    setIsRunning(true)
    setQueryError('')
    setQueryResult(null)

    // 收集用户选中的表和列，构造自然语言描述
    const selectedParts: string[] = []
    for (const db of databases) {
      for (const tbl of db.tables) {
        if (activeTables.includes(tbl.name)) {
          const selectedCols = tbl.columns.filter(c => checkedColumns[c.name])
          if (selectedCols.length > 0) {
            selectedParts.push(`${tbl.name}表的[${selectedCols.map(c => c.name).join(', ')}]列`)
          }
        }
      }
    }

    const naturalQuery = selectedParts.length > 0
      ? `查询${selectedParts.join('和')}，返回所有数据`
      : `查询选中的表数据`

    try {
      // 优先使用异步模式，体验更好
      const task = await queryApi.asyncSubmit(naturalQuery)
      setActiveTaskId(task.task_id)
      setIsStreaming(true)
    } catch {
      // 降级到同步模式
      const result = await queryApi.submit(naturalQuery)
      setQueryResult(result)
    } finally {
      setIsRunning(false)
    }
  }

  const handleCopySQL = () => {
    const sql = queryResult?.sql || previewSQL
    navigator.clipboard.writeText(sql)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleLoadFromHistory = (item: { id: string; naturalQuery: string; sql: string }) => {
    setIsHistoryOpen(false)
    setQueryResult({
      sql: item.sql,
      data: [],
      columns: [],
      rowCount: 0,
      executionTimeMs: 0,
      summary: `已加载历史查询: ${item.naturalQuery}`,
    })
  }

  // Helper: resolve column names from QueryResult.columns
  const resolveColumns = (result: QueryResult | null): string[] => {
    if (!result) return []
    if (!result.columns || result.columns.length === 0) return []
    // Handle both ColumnInfo[] and string[] (backward compat)
    return result.columns.map(col => (typeof col === 'string' ? col : (col as ColumnInfo).name))
  }

  const resultColumns = resolveColumns(queryResult)
  const resultRows = queryResult?.data || []
  const displaySQL = queryResult?.sql || previewSQL
  const sqlSummary = queryResult?.summary
  const rowCount = queryResult?.row_count ?? queryResult?.rowCount ?? 0
  const executionTimeMs = queryResult?.execution_time_ms ?? queryResult?.executionTimeMs ?? 0

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.3 }}
      className="flex p-2 gap-6 overflow-hidden h-[calc(100vh-140px)] select-none"
    >

      {/* Left Column: Schema Tree */}
      <section className="w-1/4 min-w-[280px] max-w-[320px] panel rounded-xl flex flex-col overflow-hidden">
        <div className="p-4 border-b border-white/20 flex justify-between items-center bg-white/40">
          <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2">
            <Database className="h-4.5 w-4.5 text-slate-800" />
            <span>数据源</span>
          </h2>
          <div className="flex gap-2 items-center">
            <button
              onClick={() => setIsSchemaSearchOpen(true)}
              className="text-[10px] px-2 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-600 rounded font-bold transition-colors"
              title="语义搜索 Schema"
            >
              语义搜索
            </button>
            {schemaLoading && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
            <span className="text-[10px] text-gray-400 font-mono">{databases.length} Connected</span>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-3 space-y-4">
          {schemaError && (
            <div className="text-xs text-red-500 p-2 bg-red-50 rounded">{schemaError}</div>
          )}
          {databases.map((db) => {
            const matchesSearch = db.name.toLowerCase().includes(searchTableText.toLowerCase()) ||
              db.tables.some(t => t.name.toLowerCase().includes(searchTableText.toLowerCase()))
            if (!matchesSearch && searchTableText !== '') return null

            return (
              <div key={db.id} className="space-y-1">
                <div className="flex items-center gap-2 p-2 hover:bg-white/30 rounded-lg">
                  <ChevronDown className="h-3 w-3 text-gray-400" />
                  <Database className={`h-3.5 w-3.5 ${db.status === 'active' ? 'text-status-p2' : 'text-status-p1'}`} />
                  <span className="text-xs font-bold text-gray-800">{db.name}</span>
                  {db.status === 'active' && (
                    <span className="ml-auto text-[9px] bg-status-p2/10 text-status-p2 px-1.5 py-0.5 rounded-full font-bold">活跃</span>
                  )}
                </div>
                <div className="pl-6 flex flex-col gap-1 border-l border-white/20 ml-3.5">
                  {db.tables.map((tbl) => {
                    const isVisibleInBuilder = activeTables.includes(tbl.name)
                    return (
                      <div
                        key={tbl.name}
                        onClick={() => {
                          setActiveTables(prev =>
                            prev.includes(tbl.name) ? prev.filter(t => t !== tbl.name) : [...prev, tbl.name]
                          )
                        }}
                        className={`flex items-center gap-2 p-1.5 rounded-md cursor-pointer transition-all text-xs font-medium border ${
                          isVisibleInBuilder
                            ? 'bg-black/5 text-slate-900 border-slate-300 font-bold'
                            : 'text-gray-500 hover:bg-white/10 hover:text-gray-800 border-transparent'
                        }`}
                      >
                        <TableProperties className="h-3.5 w-3.5" />
                        <span>{tbl.name}</span>
                        {isVisibleInBuilder && (
                          <span className="ml-auto w-1.5 h-1.5 rounded-full bg-digital-blue animate-pulse" />
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>

        <div className="p-3 border-t border-white/20 bg-white/10">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 h-3.5 w-3.5" />
            <input
              value={searchTableText}
              onChange={(e) => setSearchTableText(e.target.value)}
              className="w-full text-xs font-medium pl-9 pr-3 py-1.5 bg-white/20 hover:bg-white/40 focus:bg-white rounded-lg border border-white/40 focus:border-black focus:outline-none transition-all placeholder-gray-400"
              placeholder="搜索表名..."
              type="text"
            />
          </div>
        </div>
      </section>

      {/* Center Column: Visual Builder */}
      <section className="flex-1 flex flex-col rounded-xl border border-white/20 overflow-hidden bg-white/5 shadow-inner">
        <div className="h-14 border-b border-white/20 bg-white/50 flex justify-between items-center px-4 shrink-0">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-bold text-gray-800">可视化查询构建器</h3>
            <span className="h-4 w-px bg-white/40" />
            <span className="text-[10px] text-gray-500 font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-[#22C55E]" />
              {activeTables.length} 个表已选
            </span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsHistoryOpen(true)}
              className="px-3 py-1.5 rounded-lg border border-white/40 text-xs text-gray-600 font-semibold hover:bg-black/5 hover:text-gray-900 transition-colors flex items-center gap-1.5"
            >
              <Clock className="h-3.5 w-3.5" />
              历史
            </button>
            <button
              onClick={() => { setActiveTables([]); setQueryResult(null) }}
              className="px-3 py-1.5 rounded-lg border border-white/40 text-xs text-gray-600 font-semibold hover:bg-red-50 hover:text-red-600 hover:border-red-100 transition-colors"
            >
              清空画布
            </button>
            <button
              disabled={isRunning || activeTables.length === 0}
              onClick={handleRunQuery}
              className="bg-indigo-500 text-white px-4 py-1.5 rounded-lg text-xs font-semibold hover:bg-indigo-600 transition-all flex items-center gap-1.5 disabled:opacity-50 cursor-pointer shadow-md shadow-black/10 hover:shadow-lg"
            >
              {isRunning ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5 fill-white text-white" />
              )}
              <span>{isRunning ? '查询中...' : '运行查询'}</span>
            </button>
          </div>
        </div>

        <div className="flex-1 relative overflow-auto topology-grid p-6 bg-slate-50/50">
          <AnimatePresence>
            {activeTables.length >= 2 && (
              <svg className="absolute inset-0 w-full h-full pointer-events-none z-0">
                <path className="connector-line" d="M 280 130 C 350 130, 350 180, 420 180" fill="none" />
                <g transform="translate(350, 155)">
                  <circle cx="0" cy="0" r="14" fill="#f7f9fb" stroke="#000" strokeWidth="1.5" />
                  <text fill="#000" fontFamily="JetBrains Mono" fontSize="9" fontWeight="bold" x="-8" y="3">1:1</text>
                </g>
              </svg>
            )}
          </AnimatePresence>

          {activeTables.length === 0 && (
            <div className="absolute inset-0 flex flex-col items-center justify-center p-10 text-center text-gray-400 select-none pointer-events-none">
              <Database className="h-10 w-10 text-gray-300 animate-bounce mb-3" />
              <p className="text-sm font-semibold">画布为空</p>
              <p className="text-xs text-gray-400 mt-1">从左侧选择并单击数据表以建立联邦多库关联</p>
            </div>
          )}

          <div className="absolute bottom-4 right-4 panel p-1 rounded-lg flex shadow-sm z-30">
            <button className="p-1.5 hover:bg-white/30 rounded text-xs font-mono font-bold text-gray-500">100%</button>
            <button className="p-1.5 hover:bg-white/30 rounded text-xs text-gray-500 font-black">+</button>
            <button className="p-1.5 hover:bg-white/30 rounded text-xs text-gray-500 font-black">-</button>
          </div>
        </div>
      </section>

      {/* Right Column: Results & SQL */}
      <section className="w-[380px] flex flex-col gap-6 shrink-0">

        {/* Result Preview Table */}
        <div className="panel rounded-xl flex-1 flex flex-col overflow-hidden">
          <div className="px-4 py-3 border-b border-white/20 bg-white/40 flex justify-between items-center">
            <h2 className="text-xs font-bold text-gray-800 flex items-center gap-2 select-none">
              <Eye className="h-4.5 w-4.5 text-slate-800" />
              <span>结果预览</span>
            </h2>
            <div className="flex gap-2 items-center">
                  {queryResult && (
                <span className="text-[10px] font-bold bg-gray-100 text-gray-500 px-2 py-0.5 rounded">
                  {rowCount} 行
                </span>
              )}
              {resultRows.length > 0 && (
                <button
                  onClick={() => setIsExportOpen(v => !v)}
                  className="text-[10px] font-bold bg-indigo-500 text-white px-2 py-0.5 rounded hover:bg-indigo-600 transition-colors flex items-center gap-1"
                >
                  <Download className="h-3 w-3" />
                  导出
                </button>
              )}
              {resultRows.length > 0 && (
                <button
                  onClick={() => setShowChartPicker(true)}
                  className="text-[10px] font-bold bg-gradient-to-r from-amber-400 to-orange-500 text-white px-2 py-0.5 rounded hover:from-amber-500 hover:to-orange-600 transition-colors flex items-center gap-1 shadow-sm"
                >
                  <Sparkles className="h-3 w-3" />
                  图表
                </button>
              )}
              <span className="text-[10px] font-bold bg-gray-100 text-gray-500 px-2 py-0.5 rounded">上限100条</span>
            </div>
          </div>

          <div className="flex-1 overflow-auto p-2">
            {isRunning ? (
              <div className="space-y-2 p-4">
                {Array.from({ length: 4 }).map((_, i) => (
                  <div key={i} className="h-8 bg-gray-100 rounded animate-pulse" />
                ))}
              </div>
            ) : queryError ? (
              <div className="p-4 text-xs text-red-500 bg-red-50 rounded-lg">{queryError}</div>
            ) : resultRows.length > 0 ? (
              <table className="w-full text-left border-collapse select-text">
                <thead>
                  <tr className="border-b border-white/40 text-[10px] text-gray-400 uppercase font-mono font-bold">
                    {resultColumns.map((col, idx) => {
                    const colName = typeof col === 'string' ? col : (col as ColumnInfo).name
                    return (
                      <th key={idx} className="p-2 font-medium">{colName}</th>
                    )
                  })}
                  </tr>
                </thead>
                <tbody className="text-xs font-semibold">
                  {resultRows.map((row, i) => (
                    <tr key={i} className="border-b border-white/20 hover:bg-black/5 transition-all">
                      {resultColumns.map((col, cidx) => {
                        const colName = typeof col === 'string' ? col : (col as ColumnInfo).name
                        return (
                          <td key={cidx} className="p-2 font-mono text-slate-800 truncate max-w-[120px]">
                            {String(row[colName] ?? '—')}
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="flex flex-col items-center justify-center h-full text-gray-400 py-8 text-xs text-center">
                <ServerOff className="h-8 w-8 mb-2 text-gray-300" />
                <p>点击"运行查询"获取数据</p>
              </div>
            )}
          </div>
        </div>

        {/* AI SQL Panel */}
        <div className="panel rounded-xl h-[40%] flex flex-col relative overflow-hidden bg-gradient-to-br from-white/70 to-digital-blue/5">
          <div className="px-4 py-3 border-b border-white/20 flex justify-between items-center shrink-0">
            <h2 className="text-xs font-bold text-gray-800 flex items-center gap-1.5 select-none">
              <Compass className="h-4 w-4 text-slate-800 animate-pulse" />
              <span>AI 查询洞察</span>
              {queryResult && (
                <span className={`text-[9px] px-1.5 py-0.5 rounded-full font-bold ${
                  queryResult.status === 'success' ? 'bg-emerald-100 text-emerald-600' : 'bg-red-100 text-red-500'
                }`}>
                  {queryResult.status}
                </span>
              )}
            </h2>
            <div className="flex gap-2">
              <button
                onClick={handleCopySQL}
                className="text-gray-400 hover:text-black bg-white/30 p-1.5 rounded-md transition-all"
              >
                {copied ? <span className="text-[9px] font-bold text-status-p2">Copied!</span> : <Copy className="h-3.5 w-3.5" />}
              </button>
            </div>
          </div>

          <div className="p-4 flex-1 overflow-auto flex flex-col gap-3">
            {/* SQL Block */}
            <div className="text-[11px] leading-relaxed text-gray-700 bg-white/80 p-3 rounded-lg border border-white/40 font-mono select-text whitespace-pre-wrap">
              {displaySQL.split('\n').map((line, i) => {
                const upper = line.trim().toUpperCase()
                if (upper.startsWith('SELECT')) return <span key={i}><span className="text-amber-600 font-bold">SELECT</span>{line.slice(6)}\n</span>
                if (upper.startsWith('FROM')) return <span key={i}><span className="text-amber-600 font-bold">FROM</span>{line.slice(4)}\n</span>
                if (upper.startsWith('JOIN') || upper.startsWith('LEFT JOIN') || upper.startsWith('INNER JOIN')) {
                  const kw = upper.includes('LEFT') ? 'LEFT JOIN' : upper.includes('INNER') ? 'INNER JOIN' : 'JOIN'
                  return <span key={i}>{line}\n</span>
                }
                if (upper.startsWith('ON')) return <span key={i}><span className="text-amber-600 font-bold">ON</span>{line.slice(2)}\n</span>
                if (upper.startsWith('WHERE')) return <span key={i}><span className="text-amber-600 font-bold">WHERE</span>{line.slice(5)}\n</span>
                if (upper.startsWith('LIMIT')) return <span key={i}><span className="text-amber-600 font-bold">LIMIT</span>{line.slice(5)}\n</span>
                return <span key={i}>{line}\n</span>
              })}
            </div>

            {/* Summary / AI insight */}
            {sqlSummary && (
              <div className="flex gap-2 items-start">
                <div className="w-5.5 h-5.5 rounded-full bg-digital-blue/20 flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles className="h-3 w-3 text-digital-blue" />
                </div>
                <p className="text-xs text-gray-500 leading-normal">{sqlSummary}</p>
              </div>
            )}

            {queryResult && executionTimeMs > 0 && (
              <div className="text-[10px] text-gray-400 flex gap-3">
                <span>执行耗时: <strong className="text-gray-600">{executionTimeMs}ms</strong></span>
                {queryResult.intent && <span>意图: <strong className="text-gray-600">{queryResult.intent}</strong></span>}
                {queryResult.confidence && <span>置信度: <strong className="text-gray-600">{(queryResult.confidence * 100).toFixed(0)}%</strong></span>}
              </div>
            )}

            {!sqlSummary && !queryResult && (
              <div className="flex gap-2 items-start">
                <div className="w-5.5 h-5.5 rounded-full bg-digital-blue/20 flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles className="h-3 w-3 text-digital-blue" />
                </div>
                <p className="text-xs text-gray-500 leading-normal">
                  选中数据表和列后点击"运行查询"，AI 将自动生成最优 SQL 并返回结果。
                </p>
              </div>
            )}
          </div>
        </div>

      </section>

      {/* AI Result Insight Panel */}
      <section className="w-[380px] shrink-0">
        <ResultInsightPanel result={queryResult} isLoading={isRunning} />
      </section>

      {/* Export Panel — slides up when triggered */}
      <AnimatePresence>
        {isExportOpen && resultRows.length > 0 && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <ExportPanel
              sql={queryResult?.sql || ''}
              rowCount={rowCount}
              onClose={() => setIsExportOpen(false)}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <HistoryDrawer
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
        onLoadQuery={handleLoadFromHistory}
      />

      {/* SSE 异步查询流式进度 */}
      <AnimatePresence>
        {isStreaming && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center"
          >
            <StreamingQueryPanel
              taskId={activeTaskId}
              onComplete={(result) => {
                setIsStreaming(false)
                setQueryResult(result as QueryResult)
              }}
              onError={(error) => {
                setIsStreaming(false)
                setQueryError(error)
              }}
              onCancel={() => {
                setIsStreaming(false)
                setActiveTaskId('')
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* 语义 Schema 搜索模态框 */}
      <SchemaSearchModal
        isOpen={isSchemaSearchOpen}
        onClose={() => setIsSchemaSearchOpen(false)}
        onSelect={(table, selectedCols) => {
          setActiveTables(prev => prev.includes(table) ? prev : [...prev, table])
          if (selectedCols && selectedCols.length > 0) {
            setCheckedColumns(prev => {
              const updated = { ...prev }
              selectedCols.forEach(col => { updated[col] = true })
              return updated
            })
          }
          setIsSchemaSearchOpen(false)
        }}
      />

      {/* 图表类型选择模态框 */}
      <AnimatePresence>
        {showChartPicker && queryResult && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/40 backdrop-blur-sm z-50 flex items-center justify-center"
            onClick={() => setShowChartPicker(false)}
          >
            <div onClick={(e) => e.stopPropagation()}>
              <ChartPickerPanel
                columns={resultColumns}
                data={resultRows}
                onSelect={async (chartType) => {
                  setShowChartPicker(false)
                  const selectedParts: string[] = []
                  for (const db of databases) {
                    for (const tbl of db.tables) {
                      if (activeTables.includes(tbl.name)) {
                        const selectedCols = tbl.columns.filter(c => checkedColumns[c.name])
                        if (selectedCols.length > 0) {
                          selectedParts.push(`${tbl.name}表的[${selectedCols.map(c => c.name).join(', ')}]列`)
                        }
                      }
                    }
                  }
                  const naturalQuery = selectedParts.length > 0
                    ? `查询${selectedParts.join('和')}，返回所有数据`
                    : `查询选中的表数据`
                  try {
                    const result = await queryApi.submit(naturalQuery, { chart_type: chartType })
                    setQueryResult(result)
                  } catch (err) {
                    toastError(err instanceof Error ? err.message : '图表生成失败')
                  }
                }}
                onClose={() => setShowChartPicker(false)}
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
