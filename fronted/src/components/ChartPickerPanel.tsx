/**
 * ChartPickerPanel — 图表类型选择面板
 * 支持自动推荐 + 6种图表类型预览
 */
import { useState, useMemo, type ReactNode } from 'react'
import {
  BarChart2,
  TrendingUp,
  PieChart,
  Layers,
  Circle,
  Grid3X3,
  X,
  Sparkles,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import type { ColumnInfo } from '../api'

type ChartType = 'bar' | 'line' | 'pie' | 'area' | 'scatter' | 'table'

interface ChartPickerPanelProps {
  columns: (string | ColumnInfo)[]
  data: Record<string, unknown>[]
  onSelect: (chartType: string) => void
  onClose: () => void
}

interface ChartOption {
  type: ChartType
  label: string
  icon: ReactNode
  preview: ReactNode
  description: string
}

// Tiny SVG chart previews
function BarPreview() {
  return (
    <svg viewBox="0 0 48 32" className="w-full h-full">
      <rect x="4" y="14" width="8" height="14" rx="1.5" fill="currentColor" opacity="0.7" />
      <rect x="16" y="8" width="8" height="20" rx="1.5" fill="currentColor" opacity="0.85" />
      <rect x="28" y="18" width="8" height="10" rx="1.5" fill="currentColor" opacity="0.6" />
      <rect x="40" y="5" width="8" height="23" rx="1.5" fill="currentColor" opacity="0.9" />
    </svg>
  )
}

function LinePreview() {
  return (
    <svg viewBox="0 0 48 32" className="w-full h-full">
      <polyline
        points="4,24 14,16 24,12 34,8 44,4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.8"
      />
      <circle cx="4" cy="24" r="2.5" fill="currentColor" opacity="0.9" />
      <circle cx="14" cy="16" r="2.5" fill="currentColor" opacity="0.9" />
      <circle cx="24" cy="12" r="2.5" fill="currentColor" opacity="0.9" />
      <circle cx="34" cy="8" r="2.5" fill="currentColor" opacity="0.9" />
      <circle cx="44" cy="4" r="2.5" fill="currentColor" opacity="0.9" />
    </svg>
  )
}

function PiePreview() {
  return (
    <svg viewBox="0 0 48 32" className="w-full h-full">
      <path d="M24 16 L24 2 A14 14 0 0 1 38 16 Z" fill="currentColor" opacity="0.9" />
      <path d="M24 16 L38 16 A14 14 0 0 1 14 30 L24 16 Z" fill="currentColor" opacity="0.65" />
      <path d="M24 16 L14 30 A14 14 0 0 1 10 2 L24 16 Z" fill="currentColor" opacity="0.4" />
      <circle cx="24" cy="16" r="5" fill="white" opacity="0.8" />
    </svg>
  )
}

function AreaPreview() {
  return (
    <svg viewBox="0 0 48 32" className="w-full h-full">
      <path
        d="M4,24 L14,16 L24,12 L34,8 L44,4 L44,28 L4,28 Z"
        fill="currentColor"
        opacity="0.3"
      />
      <polyline
        points="4,24 14,16 24,12 34,8 44,4"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.85"
      />
    </svg>
  )
}

function ScatterPreview() {
  return (
    <svg viewBox="0 0 48 32" className="w-full h-full">
      <circle cx="8" cy="22" r="2.5" fill="currentColor" opacity="0.7" />
      <circle cx="14" cy="18" r="2" fill="currentColor" opacity="0.6" />
      <circle cx="20" cy="14" r="3" fill="currentColor" opacity="0.9" />
      <circle cx="28" cy="10" r="2" fill="currentColor" opacity="0.8" />
      <circle cx="34" cy="8" r="2.5" fill="currentColor" opacity="0.85" />
      <circle cx="40" cy="6" r="2" fill="currentColor" opacity="0.7" />
      <circle cx="12" cy="26" r="1.5" fill="currentColor" opacity="0.5" />
      <circle cx="36" cy="16" r="2" fill="currentColor" opacity="0.75" />
    </svg>
  )
}

function TablePreview() {
  return (
    <svg viewBox="0 0 48 32" className="w-full h-full">
      <rect x="4" y="4" width="40" height="5" rx="1" fill="currentColor" opacity="0.5" />
      <rect x="4" y="12" width="40" height="4" rx="1" fill="currentColor" opacity="0.25" />
      <rect x="4" y="18" width="40" height="4" rx="1" fill="currentColor" opacity="0.25" />
      <rect x="4" y="24" width="40" height="4" rx="1" fill="currentColor" opacity="0.25" />
    </svg>
  )
}

const CHART_OPTIONS: ChartOption[] = [
  {
    type: 'bar',
    label: '柱状图',
    icon: <BarChart2 className="h-5 w-5" />,
    preview: <BarPreview />,
    description: '适合比较分类数据的数量差异',
  },
  {
    type: 'line',
    label: '折线图',
    icon: <TrendingUp className="h-5 w-5" />,
    preview: <LinePreview />,
    description: '适合展示数据随时间变化的趋势',
  },
  {
    type: 'pie',
    label: '饼图',
    icon: <PieChart className="h-5 w-5" />,
    preview: <PiePreview />,
    description: '适合展示各部分占总体的比例',
  },
  {
    type: 'area',
    label: '面积图',
    icon: <Layers className="h-5 w-5" />,
    preview: <AreaPreview />,
    description: '适合展示累积数据的变化趋势',
  },
  {
    type: 'scatter',
    label: '散点图',
    icon: <Circle className="h-5 w-5" />,
    preview: <ScatterPreview />,
    description: '适合发现两个变量之间的相关性',
  },
  {
    type: 'table',
    label: '数据表',
    icon: <Grid3X3 className="h-5 w-5" />,
    preview: <TablePreview />,
    description: '适合精确查看每一条数据',
  },
]

function detectBestChartType(columns: (string | ColumnInfo)[], data: Record<string, unknown>[]): ChartType {
  const colLower = columns.map(c => (typeof c === 'string' ? c : (c as ColumnInfo).name).toLowerCase())

  // Check for percentage/ratio columns → pie
  if (
    colLower.some(c => c.includes('percent') || c.includes('ratio') || c.includes('占比') || c.includes('比例') || c.includes('%')) ||
    (data.length > 0 && Object.keys(data[0]).some(k => {
      const v = data[0][k]
      return typeof v === 'number' && v >= 0 && v <= 1
    }))
  ) {
    return 'pie'
  }

  // Check for time/date columns → line
  if (
    colLower.some(c => c.includes('date') || c.includes('time') || c.includes('month') || c.includes('year') || c.includes('日') || c.includes('月') || c.includes('年') || c.includes('时')) ||
    (data.length > 0 && Object.values(data[0]).some(v => v instanceof Date || (typeof v === 'string' && /^\d{4}-\d{2}/.test(v))))
  ) {
    return 'line'
  }

  // Default → bar
  return 'bar'
}

export default function ChartPickerPanel({
  columns,
  data,
  onSelect,
  onClose,
}: ChartPickerPanelProps) {
  const [hovered, setHovered] = useState<ChartType | null>(null)

  const bestType = useMemo(() => detectBestChartType(columns, data), [columns, data])

  const activeChart = hovered ?? bestType
  const activeOption = CHART_OPTIONS.find(o => o.type === activeChart)!

  return (
    <motion.div
      initial={{ opacity: 0, y: -8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={{ opacity: 0, y: -8, scale: 0.97 }}
      transition={{ duration: 0.18, ease: 'easeOut' }}
      className="panel-elevated rounded-2xl p-5 space-y-4 w-[560px]"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-bold text-slate-900">选择图表类型</h3>
          {activeOption && (
            <span className="text-[10px] text-slate-500 font-medium">
              — {activeOption.description}
            </span>
          )}
        </div>
        <button
          onClick={onClose}
          className="p-1.5 hover:bg-slate-100 rounded-lg transition-colors"
        >
          <X className="h-4 w-4 text-slate-400" />
        </button>
      </div>

      <div className="flex gap-4">
        {/* Chart type grid */}
        <div className="flex-1 grid grid-cols-3 gap-2">
          {CHART_OPTIONS.map(opt => {
            const isRecommended = opt.type === bestType
            const isSelected = opt.type === activeChart
            return (
              <motion.button
                key={opt.type}
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                onClick={() => onSelect(opt.type)}
                onMouseEnter={() => setHovered(opt.type)}
                onMouseLeave={() => setHovered(null)}
                className={`relative flex flex-col items-center gap-1.5 p-3 rounded-xl border transition-all text-xs font-bold ${
                  isSelected
                    ? 'border-indigo-500 bg-indigo-500 text-white shadow-sm'
                    : 'border-slate-200 bg-white/40 text-slate-700 hover:bg-indigo-50'
                }`}
              >
                {isRecommended && (
                  <span className="absolute -top-2 -right-2 flex items-center gap-0.5 px-1.5 py-0.5 bg-amber-400 text-white text-[9px] font-bold rounded-full shadow-sm">
                    <Sparkles className="h-2.5 w-2.5" />
                    推荐
                  </span>
                )}
                <div className={`h-8 w-10 ${isSelected ? 'text-white' : 'text-slate-600'}`}>
                  {opt.preview}
                </div>
                <span>{opt.label}</span>
              </motion.button>
            )
          })}
        </div>

        {/* Preview area */}
        <div className="w-36 flex flex-col items-center gap-2">
          <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">
            预览
          </p>
          <div
            className={`w-full h-28 rounded-xl border flex items-center justify-center p-2 transition-all ${
              activeChart === 'table'
                ? 'border-slate-200 bg-white/60'
                : 'border-slate-200 bg-white/60'
            }`}
          >
            <div className="w-full h-full text-slate-500">
              <AnimatePresence mode="wait">
                <motion.div
                  key={activeChart}
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  transition={{ duration: 0.15 }}
                  className="w-full h-full"
                >
                  {activeOption?.preview}
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
          <p className="text-[10px] text-slate-400 font-medium">
            {activeOption?.label}
          </p>
        </div>
      </div>

      {/* Footer hint */}
      <p className="text-[10px] text-slate-400 text-center">
        根据数据结构自动推荐最合适的图表类型
      </p>
    </motion.div>
  )
}
