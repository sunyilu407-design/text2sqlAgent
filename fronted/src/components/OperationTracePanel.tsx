/**
 * OperationTracePanel — 操作追踪面板
 * 展示查询执行的完整链路追踪（意图分类、Schema 检索、SQL 生成、验证、执行等步骤）
 */
import { motion } from 'motion/react'
import {
  Activity,
  Brain,
  Database,
  FileCode,
  ShieldCheck,
  Play,
  Eraser,
  MessageSquare,
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
} from 'lucide-react'
import { useOperationTrace } from '../hooks/useQueries'
import type { OperationTraceResult, TraceStep } from '../api'

const STEP_ICONS: Record<string, typeof Brain> = {
  intent_classification: Brain,
  schema_retrieval: Database,
  sql_generation: FileCode,
  sql_validation: ShieldCheck,
  sql_execution: Play,
  data_masking: Eraser,
  chart_generation: Activity,
  prompt_security_check: ShieldCheck,
  building_response: MessageSquare,
}

const STEP_LABELS: Record<string, string> = {
  intent_classification: '意图分类',
  schema_retrieval: 'Schema 检索',
  sql_generation: 'SQL 生成',
  sql_validation: 'SQL 验证',
  sql_execution: '执行查询',
  data_masking: '数据脱敏',
  chart_generation: '图表生成',
  prompt_security_check: '安全检查',
  building_response: '构建响应',
}

const STATUS_CONFIG = {
  success: { color: 'text-green-500', bg: 'bg-green-50', border: 'border-green-200' },
  failed: { color: 'text-red-500', bg: 'bg-red-50', border: 'border-red-200' },
  running: { color: 'text-blue-500', bg: 'bg-blue-50', border: 'border-blue-200' },
  cancelled: { color: 'text-gray-500', bg: 'bg-gray-50', border: 'border-gray-200' },
}

interface OperationTracePanelProps {
  taskId: string | null
  onClose: () => void
}

export default function OperationTracePanel({ taskId, onClose }: OperationTracePanelProps) {
  const { data, isLoading, isError } = useOperationTrace(taskId ?? '')

  if (!taskId) {
    return (
      <div className="panel rounded-xl bg-white/50 border border-white/20 p-4 flex items-center gap-2 text-xs text-gray-400">
        <Activity className="h-3.5 w-3.5" />
        输入任务 ID 以查看执行追踪
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="panel rounded-xl bg-white/50 border border-white/20 p-4 flex items-center gap-2 text-xs text-gray-400">
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
        加载追踪数据...
      </div>
    )
  }

  if (isError || !data) {
    return (
      <div className="panel rounded-xl bg-white/50 border border-white/20 p-4 flex items-center gap-2 text-xs text-red-400">
        <XCircle className="h-3.5 w-3.5" />
        追踪数据加载失败
      </div>
    )
  }

  const status = data.status ?? 'running'
  const cfg = STATUS_CONFIG[status] ?? STATUS_CONFIG.running
  const totalMs = data.total_duration_ms ?? 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      className="panel rounded-xl bg-white/50 border border-white/20 overflow-hidden"
    >
      {/* Header */}
      <div className={`px-3 py-2 border-b border-white/20 bg-white/30 flex items-center gap-2 ${cfg.bg}`}>
        <Activity className={`h-3.5 w-3.5 ${cfg.color}`} />
        <span className="text-[10px] font-bold text-gray-700 uppercase tracking-wide">执行追踪</span>
        <span className={`ml-auto text-[10px] font-bold ${cfg.color}`}>
          {status === 'success' ? '成功' : status === 'failed' ? '失败' : status === 'running' ? '进行中' : status}
        </span>
        {totalMs > 0 && (
          <span className="text-[10px] text-gray-400 font-mono flex items-center gap-0.5">
            <Clock className="h-3 w-3" />
            {totalMs}ms
          </span>
        )}
      </div>

      {/* Steps */}
      <div className="divide-y divide-gray-100/50">
        {data.steps?.map((step: TraceStep, idx: number) => {
          const Icon = STEP_ICONS[step.type] ?? Activity
          const label = STEP_LABELS[step.type] ?? step.type
          const sc = STATUS_CONFIG[step.status] ?? STATUS_CONFIG.running

          return (
            <div key={step.id ?? idx} className="px-3 py-2 hover:bg-white/20 transition-colors">
              <div className="flex items-start gap-2">
                <div className={`shrink-0 mt-0.5 ${sc.color}`}>
                  {step.status === 'running' ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  ) : step.status === 'success' ? (
                    <CheckCircle2 className="h-3.5 w-3.5" />
                  ) : (
                    <XCircle className="h-3.5 w-3.5" />
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <Icon className={`h-3 w-3 shrink-0 ${sc.color}`} />
                    <span className="text-[10px] font-bold text-gray-700">{label}</span>
                    {step.duration_ms > 0 && (
                      <span className="text-[10px] text-gray-400 font-mono ml-auto">
                        {step.duration_ms}ms
                      </span>
                    )}
                  </div>
                  {step.input_summary && (
                    <p className="text-[10px] text-gray-500 mt-0.5">
                      <span className="text-gray-400">输入: </span>{step.input_summary}
                    </p>
                  )}
                  {step.output_summary && (
                    <p className="text-[10px] text-gray-500 mt-0.5">
                      <span className="text-gray-400">输出: </span>{step.output_summary}
                    </p>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* No steps */}
      {(!data.steps || data.steps.length === 0) && (
        <div className="px-3 py-4 text-xs text-gray-400 text-center">
          暂无步骤数据
        </div>
      )}
    </motion.div>
  )
}
