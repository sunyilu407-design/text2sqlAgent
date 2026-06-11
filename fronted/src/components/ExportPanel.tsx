/**
 * ExportPanel — 数据导出面板
 * 对接 /api/v1/export 和 /api/v1/export/{export_id}
 */
import React, { useState, type ReactNode } from 'react'
import {
  Download,
  FileSpreadsheet,
  FileJson,
  FileText,
  Image,
  Loader2,
  CheckCircle,
  AlertCircle,
  X,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

type ExportFormat = 'csv' | 'excel' | 'json' | 'sql' | 'pdf'
type ExportStatus = 'idle' | 'pending' | 'processing' | 'completed' | 'failed'

interface ExportPanelProps {
  sql: string
  rowCount: number
  onClose?: () => void
}

const FORMAT_OPTIONS: {
  value: ExportFormat
  label: string
  icon: ReactNode
  desc: string
}[] = [
  { value: 'csv', label: 'CSV', icon: <FileSpreadsheet className="h-5 w-5" />, desc: '逗号分隔值，通用兼容' },
  { value: 'excel', label: 'Excel', icon: <FileSpreadsheet className="h-5 w-5" />, desc: 'xlsx 格式，支持多 Sheet' },
  { value: 'json', label: 'JSON', icon: <FileJson className="h-5 w-5" />, desc: '结构化 JSON 数组' },
  { value: 'sql', label: 'SQL', icon: <FileText className="h-5 w-5" />, desc: 'INSERT INTO 语句' },
  { value: 'pdf', label: 'PDF', icon: <Image className="h-5 w-5" />, desc: 'PDF 报告（需后端支持）' },
]

async function doExport(
  sql: string,
  format: ExportFormat,
  rowCount: number
): Promise<{ export_id: string; download_url: string }> {
  const token = localStorage.getItem('mgbi_token') || ''
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) headers['Authorization'] = `Bearer ${token}`

  // Step 1: 创建导出任务
  const createRes = await fetch('/api/v1/export', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      sql,
      format,
      max_rows: 10000,
      include_headers: true,
      mask_sensitive: true,
    }),
  })

  if (!createRes.ok) {
    const err = await createRes.json().catch(() => ({ detail: '导出失败' }))
    throw new Error(err.detail || `HTTP ${createRes.status}`)
  }

  const { export_id } = await createRes.json()

  // Step 2: 轮询导出状态
  for (let i = 0; i < 20; i++) {
    await new Promise(r => setTimeout(r, 500))
    const statusRes = await fetch(`/api/v1/export/${export_id}`, { headers })
    if (!statusRes.ok) continue
    const status = await statusRes.json()
    if (status.status === 'completed') {
      return {
        export_id,
        download_url: status.download_url || `/api/v1/export/${export_id}/download`,
      }
    }
    if (status.status === 'failed') {
      throw new Error(status.error || '导出失败')
    }
  }

  // 超时：直接返回下载链接（后端可能已完成但未更新状态）
  return {
    export_id,
    download_url: `/api/v1/export/${export_id}/download`,
  }
}

export default function ExportPanel({ sql, rowCount, onClose }: ExportPanelProps) {
  const [format, setFormat] = useState<ExportFormat>('csv')
  const [maskSensitive, setMaskSensitive] = useState(true)
  const [includeHeaders, setIncludeHeaders] = useState(true)
  const [maxRows, setMaxRows] = useState(10000)
  const [status, setStatus] = useState<ExportStatus>('idle')
  const [downloadUrl, setDownloadUrl] = useState('')
  const [error, setError] = useState('')
  const [exportId, setExportId] = useState('')

  const handleExport = async () => {
    if (!sql) {
      setError('没有可导出的数据，请先运行查询')
      return
    }
    setStatus('pending')
    setError('')
    setDownloadUrl('')

    try {
      const result = await doExport(sql, format, rowCount)
      setExportId(result.export_id)
      setDownloadUrl(result.download_url)
      setStatus('completed')
    } catch (err) {
      setError(err instanceof Error ? err.message : '导出失败')
      setStatus('failed')
    }
  }

  return (
    <div className="panel rounded-xl p-5 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
          <Download className="h-4 w-4" />
          导出数据
        </h3>
        {onClose && (
          <button onClick={onClose} className="p-1 hover:bg-slate-100 rounded transition-colors">
            <X className="h-4 w-4 text-slate-400" />
          </button>
        )}
      </div>

      {/* Format selector */}
      <div>
        <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">导出格式</p>
        <div className="grid grid-cols-5 gap-2">
          {FORMAT_OPTIONS.map(opt => (
            <button
              key={opt.value}
              onClick={() => setFormat(opt.value)}
              className={`flex flex-col items-center gap-1 p-3 rounded-xl border transition-all text-xs font-bold ${
                format === opt.value
                  ? 'border-indigo-500 bg-indigo-500 text-white shadow-sm'
                  : 'border-slate-200 bg-white/40 text-slate-700 hover:bg-indigo-50'
              }`}
            >
              {opt.icon}
              <span>{opt.label}</span>
            </button>
          ))}
        </div>
        <p className="text-[10px] text-slate-400 mt-1.5">
          {FORMAT_OPTIONS.find(o => o.value === format)?.desc}
        </p>
      </div>

      {/* Options */}
      <div className="space-y-2">
        <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">选项</p>

        <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 cursor-pointer">
          <input
            type="checkbox"
            checked={includeHeaders}
            onChange={e => setIncludeHeaders(e.target.checked)}
            className="rounded border-slate-300"
          />
          包含表头
        </label>

        <label className="flex items-center gap-2 text-xs font-semibold text-slate-700 cursor-pointer">
          <input
            type="checkbox"
            checked={maskSensitive}
            onChange={e => setMaskSensitive(e.target.checked)}
            className="rounded border-slate-300"
          />
          脱敏（隐藏敏感字段）
        </label>

        <div className="flex items-center gap-2 text-xs font-semibold text-slate-700">
          <label>最大行数:</label>
          <input
            type="number"
            value={maxRows}
            min={1}
            max={100000}
            onChange={e => setMaxRows(Number(e.target.value))}
            className="w-24 text-xs px-2 py-1 border border-slate-200 rounded-lg focus:outline-none focus:border-black"
          />
          <span className="text-slate-400">（当前结果 {rowCount} 行）</span>
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600 font-semibold">
          {error}
        </div>
      )}

      {/* Result */}
      {status === 'completed' && downloadUrl && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-lg space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-emerald-600">
            <CheckCircle className="h-4 w-4" />
            导出完成
          </div>
          <p className="text-[10px] text-slate-500 font-mono">ID: {exportId}</p>
          <a
            href={downloadUrl}
            download
            className="inline-flex items-center gap-1 px-3 py-1.5 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 transition-colors"
          >
            <Download className="h-3.5 w-3.5" />
            下载文件
          </a>
        </div>
      )}

      {/* Action */}
      <button
        onClick={handleExport}
        disabled={status === 'pending' || status === 'processing'}
        className="w-full bg-indigo-500 hover:bg-indigo-600 text-white py-2.5 rounded-xl text-xs font-bold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
      >
        {status === 'pending' || status === 'processing' ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" />
            正在导出...
          </>
        ) : (
          <>
            <Download className="h-4 w-4" />
            导出 {FORMAT_OPTIONS.find(o => o.value === format)?.label} 文件
          </>
        )}
      </button>
    </div>
  )
}
