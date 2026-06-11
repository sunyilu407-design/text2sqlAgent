/**
 * ResultInsightPanel — AI 结果解读面板
 * 基于查询结果数据自动生成解读，包括关键发现、数据洞察和行动建议
 */
import { useMemo } from 'react'
import { motion } from 'motion/react'
import {
  Lightbulb,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  CheckCircle2,
  BarChart2,
  RefreshCw,
  Loader2,
} from 'lucide-react'
import type { QueryResult } from '../api'

interface ResultInsightPanelProps {
  result: QueryResult | null
  isLoading?: boolean
}

interface Insight {
  icon: typeof Lightbulb
  color: string
  label: string
  content: string
}

export default function ResultInsightPanel({ result, isLoading }: ResultInsightPanelProps) {
  const insights = useMemo<Insight[]>(() => {
    if (!result || !result.data || result.data.length === 0) {
      return []
    }

    const insights: Insight[] = []
    const data = result.data
    const rowCount = result.row_count ?? result.rowCount ?? data.length
    const execTime = result.execution_time_ms ?? result.executionTimeMs ?? 0
    const columns = result.columns ?? []

    // 基础统计发现
    insights.push({
      icon: BarChart2,
      color: 'text-blue-500',
      label: '数据规模',
      content: `本次查询返回 ${rowCount} 行数据，涉及 ${columns.length} 个字段，执行耗时 ${execTime}ms`,
    })

    if (data.length > 0) {
      const firstRow = data[0]

      // 数值列分析
      const numericCols = Object.entries(firstRow).filter(([, v]) => typeof v === 'number')
      if (numericCols.length > 0) {
        const [colName, val] = numericCols[0]
        insights.push({
          icon: TrendingUp,
          color: 'text-green-500',
          label: '数值统计',
          content: `字段 "${colName}" 首行值为 ${typeof val === 'number' ? val.toLocaleString() : val}`,
        })

        // 计算数值范围
        const values = numericCols.map(([, v]) => v as number)
        const min = Math.min(...values)
        const max = Math.max(...values)
        const avg = values.reduce((a, b) => a + b, 0) / values.length
        if (min !== max) {
          insights.push({
            icon: TrendingUp,
            color: 'text-teal-500',
            label: '数值范围',
            content: `数值字段范围: 最小值 ${min.toLocaleString()}，最大值 ${max.toLocaleString()}，均值 ${avg.toLocaleString(undefined, { maximumFractionDigits: 2 })}`,
          })
        }
      }

      // 检测潜在异常（行数为0或极大值）
      if (rowCount === 0) {
        insights.push({
          icon: AlertTriangle,
          color: 'text-amber-500',
          label: '空结果',
          content: '查询返回 0 行数据，可能原因：筛选条件过于严格、对应时间段无数据、或表数据尚未同步',
        })
      } else if (rowCount > 10000) {
        insights.push({
          icon: AlertTriangle,
          color: 'text-amber-500',
          label: '大数据集',
          content: `返回行数较多 (${rowCount.toLocaleString()})，建议适当添加筛选条件以提升分析效率`,
        })
      }

      // 字符串列唯一值分析
      const stringCols = Object.entries(firstRow).filter(([, v]) => typeof v === 'string')
      if (stringCols.length > 0) {
        const uniqueCounts = new Map<string, number>()
        data.forEach(row => {
          stringCols.forEach(([k]) => {
            const v = row[k]
            if (typeof v === 'string' && v.trim()) {
              uniqueCounts.set(k, (uniqueCounts.get(k) ?? 0) + 1)
            }
          })
        })
        const topCol = [...uniqueCounts.entries()].sort((a, b) => b[1] - a[1])[0]
        if (topCol) {
          insights.push({
            icon: CheckCircle2,
            color: 'text-purple-500',
            label: '分类字段',
            content: `字段 "${topCol[0]}" 共出现 ${topCol[1]} 次（去重计数），适合作为分组维度`,
          })
        }
      }
    }

    // SQL 洞察
    if (result.sql) {
      const sqlLower = result.sql.toLowerCase()
      if (sqlLower.includes('join')) {
        insights.push({
          icon: RefreshCw,
          color: 'text-indigo-500',
          label: '多表关联',
          content: '当前查询使用了 JOIN 操作，涉及多表关联分析，请注意关联条件是否正确',
        })
      }
      if (sqlLower.includes('group by')) {
        insights.push({
          icon: BarChart2,
          color: 'text-orange-500',
          label: '聚合查询',
          content: '检测到 GROUP BY 聚合操作，分析维度已明确',
        })
      }
      if (sqlLower.includes('order by')) {
        insights.push({
          icon: TrendingDown,
          color: 'text-slate-500',
          label: '排序分析',
          content: '查询包含 ORDER BY，排序维度已确定',
        })
      }
    }

    return insights
  }, [result])

  if (isLoading) {
    return (
      <div className="panel rounded-xl bg-white/50 border border-white/20 p-4 flex items-center gap-2 text-xs text-gray-400">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        正在分析查询结果...
      </div>
    )
  }

  if (!result || insights.length === 0) {
    return (
      <div className="panel rounded-xl bg-white/50 border border-white/20 p-4 flex items-center gap-2 text-xs text-gray-400">
        <Lightbulb className="h-3.5 w-3.5" />
        执行查询后，这里将展示 AI 对结果的智能解读
      </div>
    )
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="panel rounded-xl bg-white/50 border border-white/20 overflow-hidden"
    >
      <div className="px-3 py-2 border-b border-white/20 bg-white/30 flex items-center gap-1.5">
        <Lightbulb className="h-3.5 w-3.5 text-amber-500" />
        <span className="text-[10px] font-bold text-gray-700 uppercase tracking-wide">智能洞察</span>
        <span className="ml-auto text-[10px] text-gray-400">{insights.length} 条发现</span>
      </div>
      <div className="divide-y divide-gray-100/50">
        {insights.map((insight, idx) => {
          const Icon = insight.icon
          return (
            <div key={idx} className="px-3 py-2 hover:bg-white/20 transition-colors">
              <div className="flex items-start gap-2">
                <Icon className={`h-3.5 w-3.5 shrink-0 mt-0.5 ${insight.color}`} />
                <div className="flex-1 min-w-0">
                  <span className="text-[10px] font-bold text-gray-600 uppercase tracking-wide">
                    {insight.label}
                  </span>
                  <p className="text-[10px] text-gray-600 mt-0.5 leading-snug">
                    {insight.content}
                  </p>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </motion.div>
  )
}
