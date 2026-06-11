/**
 * StreamingQueryPanel — SSE 异步查询流式进度面板
 * 对接 /api/v1/query/async/{taskId}/stream
 */
import { useState, useEffect, useCallback, useRef, type ReactNode } from 'react'
import {
  Loader2,
  CheckCircle2,
  Circle,
  AlertCircle,
  X,
  Clock,
  ChevronRight,
  Brain,
  Database,
  FileCode,
  ShieldCheck,
  Play,
  Eraser,
  MessageSquare,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

// ── Step definitions ──────────────────────────────────────────────
type StepKey =
  | 'intent_classification'
  | 'schema_retrieval'
  | 'sql_generation'
  | 'sql_validation'
  | 'sql_execution'
  | 'data_masking'
  | 'building_response'

interface StepDef {
  key: StepKey
  label: string
  icon: ReactNode
}

const STEPS: StepDef[] = [
  { key: 'intent_classification', label: '意图分类', icon: <Brain className="h-4 w-4" /> },
  { key: 'schema_retrieval', label: 'Schema 检索', icon: <Database className="h-4 w-4" /> },
  { key: 'sql_generation', label: 'SQL 生成', icon: <FileCode className="h-4 w-4" /> },
  { key: 'sql_validation', label: 'SQL 验证', icon: <ShieldCheck className="h-4 w-4" /> },
  { key: 'sql_execution', label: '执行查询', icon: <Play className="h-4 w-4" /> },
  { key: 'data_masking', label: '数据脱敏', icon: <Eraser className="h-4 w-4" /> },
  { key: 'building_response', label: '构建响应', icon: <MessageSquare className="h-4 w-4" /> },
]

// ── SSE Event types ───────────────────────────────────────────────
type SSEEventType = 'start' | 'progress' | 'complete' | 'error'

interface SSEMessage {
  type: SSEEventType
  step?: StepKey
  progress?: number
  message?: string
  result?: unknown
  error?: string
}

// ── Props ─────────────────────────────────────────────────────────
interface StreamingQueryPanelProps {
  taskId: string
  onComplete: (result: unknown) => void
  onError: (error: string) => void
  onCancel: () => void
}

// ── Component ─────────────────────────────────────────────────────
export default function StreamingQueryPanel({
  taskId,
  onComplete,
  onError,
  onCancel,
}: StreamingQueryPanelProps) {
  const [started, setStarted] = useState(false)
  const [currentStep, setCurrentStep] = useState<StepKey | null>(null)
  const [completedSteps, setCompletedSteps] = useState<Set<StepKey>>(new Set())
  const [progress, setProgress] = useState(0)
  const [stepMessage, setStepMessage] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const [elapsedSec, setElapsedSec] = useState(0)

  const esRef = useRef<EventSource | null>(null)
  const startTimeRef = useRef<number>(Date.now())
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Elapsed time counter
  useEffect(() => {
    if (!started || done) return
    timerRef.current = setInterval(() => {
      setElapsedSec(Math.floor((Date.now() - startTimeRef.current) / 1000))
    }, 1000)
    return () => {
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [started, done])

  // SSE connection
  useEffect(() => {
    const url = `/api/v1/query/async/${encodeURIComponent(taskId)}/stream`
    const es = new EventSource(url)
    esRef.current = es

    es.onopen = () => {
      startTimeRef.current = Date.now()
      setStarted(true)
    }

    es.onmessage = (e: MessageEvent<string>) => {
      let data: SSEMessage
      try {
        data = JSON.parse(e.data) as SSEMessage
      } catch {
        return
      }

      switch (data.type) {
        case 'start':
          setStepMessage('开始处理查询...')
          break

        case 'progress':
          if (data.step) {
            setCurrentStep(data.step)
            setProgress(data.progress ?? 0)
            if (data.message) setStepMessage(data.message)
            setCompletedSteps(prev => {
              const next = new Set(prev)
              // Auto-complete previous steps
              const idx = STEPS.findIndex(s => s.key === data.step)
              if (idx > 0) {
                const prevKey = STEPS[idx - 1]?.key
                if (prevKey && !next.has(prevKey)) next.add(prevKey)
              }
              return next
            })
          }
          break

        case 'complete':
          setCompletedSteps(prev => {
            const next = new Set(prev)
            if (currentStep) next.add(currentStep)
            STEPS.forEach(s => next.add(s.key))
            return next
          })
          setDone(true)
          setProgress(100)
          setStepMessage('查询完成')
          es.close()
          if (data.result !== undefined) {
            onComplete(data.result)
          }
          break

        case 'error':
          setError(data.error ?? '未知错误')
          onError(data.error ?? '未知错误')
          es.close()
          break
      }
    }

    es.onerror = () => {
      const msg = 'SSE 连接异常，请检查网络或任务是否已过期'
      setError(msg)
      onError(msg)
      es.close()
    }

    return () => {
      es.close()
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [taskId, currentStep, onComplete, onError])

  const handleCancel = useCallback(async () => {
    if (esRef.current) esRef.current.close()
    if (timerRef.current) clearInterval(timerRef.current)
    try {
      const token = localStorage.getItem('mgbi_token') ?? ''
      await fetch(`/api/v1/query/async/${encodeURIComponent(taskId)}`, {
        method: 'DELETE',
        headers: {
          Authorization: token ? `Bearer ${token}` : '',
        },
      })
    } catch {
      // ignore cancellation errors
    }
    onCancel()
  }, [taskId, onCancel])

  const fmtTime = (sec: number) => {
    if (sec < 60) return `${sec}s`
    return `${Math.floor(sec / 60)}m ${sec % 60}s`
  }

  const getStepStatus = (stepKey: StepKey): 'done' | 'active' | 'pending' => {
    if (completedSteps.has(stepKey)) return 'done'
    if (currentStep === stepKey) return 'active'
    return 'pending'
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.25 }}
      className="panel rounded-2xl overflow-hidden"
    >
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/30 bg-white/30 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2">
            <Brain className="h-5 w-5 text-slate-700" />
            <h3 className="text-sm font-bold text-slate-800">异步查询进度</h3>
          </div>
          {!done && !error && started && (
            <span className="text-[10px] font-mono font-bold text-slate-400 bg-white/50 px-2 py-0.5 rounded-full">
              {fmtTime(elapsedSec)}
            </span>
          )}
          {done && !error && (
            <span className="flex items-center gap-1 text-[10px] font-bold text-emerald-600 bg-emerald-50 px-2 py-0.5 rounded-full">
              <CheckCircle2 className="h-3 w-3" />
              完成 · {fmtTime(elapsedSec)}
            </span>
          )}
        </div>
        {!done && (
          <button
            onClick={handleCancel}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-600 hover:bg-red-50 hover:text-red-500 border border-white/40 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
            取消
          </button>
        )}
      </div>

      {/* Overall progress bar */}
      {started && !done && (
        <div className="px-5 py-3 border-b border-white/20 bg-white/10">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[11px] font-bold text-slate-600 flex items-center gap-1.5">
              <Clock className="h-3.5 w-3.5 text-slate-400" />
              整体进度
            </span>
            <span className="text-[11px] font-mono font-bold text-slate-500">{progress}%</span>
          </div>
          <div className="h-2 bg-white/40 rounded-full overflow-hidden">
            <motion.div
              className="h-full bg-gradient-to-r from-digital-blue to-primary rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${progress}%` }}
              transition={{ duration: 0.4, ease: 'easeOut' }}
            />
          </div>
          {stepMessage && (
            <p className="mt-1.5 text-[11px] text-slate-500">{stepMessage}</p>
          )}
        </div>
      )}

      {/* Step list */}
      <div className="px-5 py-4 space-y-1">
        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider mb-3">
          处理步骤
        </p>
        <div className="space-y-2">
          {STEPS.map((step, idx) => {
            const status = getStepStatus(step.key)
            return (
              <div
                key={step.key}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all text-xs font-semibold ${
                  status === 'active'
                    ? 'bg-digital-blue/10 border border-digital-blue/20'
                    : status === 'done'
                    ? 'bg-emerald-50/60 border border-emerald-200/40'
                    : 'bg-white/20 border border-transparent'
                }`}
              >
                {/* Icon / indicator */}
                <div className="shrink-0">
                  {status === 'done' ? (
                    <div className="w-7 h-7 rounded-full bg-emerald-100 flex items-center justify-center">
                      <CheckCircle2 className="h-4 w-4 text-emerald-600" />
                    </div>
                  ) : status === 'active' ? (
                    <div className="w-7 h-7 rounded-full bg-digital-blue/20 flex items-center justify-center">
                      <Loader2 className="h-4 w-4 text-digital-blue animate-spin" />
                    </div>
                  ) : (
                    <div className="w-7 h-7 rounded-full bg-white/50 flex items-center justify-center">
                      <Circle className="h-3.5 w-3.5 text-slate-300" />
                    </div>
                  )}
                </div>

                {/* Step name */}
                <span
                  className={`flex-1 ${
                    status === 'active'
                      ? 'text-digital-blue'
                      : status === 'done'
                      ? 'text-emerald-600'
                      : 'text-slate-400'
                  }`}
                >
                  {step.label}
                </span>

                {/* Step message (only for active) */}
                <AnimatePresence>
                  {status === 'active' && stepMessage && (
                    <motion.span
                      initial={{ opacity: 0, x: 4 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: 4 }}
                      className="text-[10px] text-slate-400 italic"
                    >
                      {stepMessage}
                    </motion.span>
                  )}
                </AnimatePresence>

                {/* Arrow connector */}
                {idx < STEPS.length - 1 && (
                  <ChevronRight className="h-3.5 w-3.5 text-slate-300 shrink-0" />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Error state */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mx-5 mb-4 p-3 bg-red-50 border border-red-200 rounded-xl flex items-start gap-2"
          >
            <AlertCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />
            <div>
              <p className="text-xs font-bold text-red-600">执行失败</p>
              <p className="text-[11px] text-red-400 mt-0.5">{error}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  )
}
