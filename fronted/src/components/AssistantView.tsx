/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 * AI 智能分析助手 — 对接 /api/v1/query 接口
 */
import { useState, useRef, useEffect } from 'react'
import {
  Sparkles,
  Send,
  Bot,
  User,
  FileCheck2,
  BarChart2,
  AlertCircle,
  Clock,
  Mic,
  Smile,
  Paperclip,
  RefreshCw,
  Loader2,
  Compass,
} from 'lucide-react'
import { motion } from 'motion/react'
import { ChatMessage } from '../types'
import { queryApi } from '../api'
import SuggestionDropdown from './SuggestionDropdown'

const quickPrompts = [
  '分析本季度杭州市订单时效',
  '宁波营收异常下行原因',
  '温州联邦模式连接时效',
  '导出全省多源营收日志',
]

export default function AssistantView() {
  const [inputText, setInputText] = useState('')
  const [showSuggestions, setShowSuggestions] = useState(false)
  const inputContainerRef = useRef<HTMLDivElement>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: 'welcome',
      sender: 'assistant',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: '欢迎使用 Micro-GenBI 智能分析助手。请输入自然语言问题，我将自动生成最优 SQL 并返回分析结果。',
    },
  ])

  const [isLoading, setIsLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  const scrollBottom = () => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollBottom()
  }, [messages, isLoading])

  const [isRecording, setIsRecording] = useState(false)

  const handleMicClick = async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      alert('当前浏览器不支持语音输入')
      return
    }
    try {
      if (isRecording) {
        setIsRecording(false)
        return
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      const mediaRecorder = new MediaRecorder(stream)
      const chunks: Blob[] = []
      mediaRecorder.ondataavailable = (e) => { if (e.data.size) chunks.push(e.data) }
      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach(t => t.stop())
        if (chunks.length === 0) return
        const audioBlob = new Blob(chunks, { type: 'audio/webm' })
        const formData = new FormData()
        formData.append('audio', audioBlob, 'recording.webm')
        // TODO: POST to /api/v1/speech-to-text when backend supports it
        alert('语音识别功能待后端对接')
      }
      mediaRecorder.start()
      setIsRecording(true)
    } catch {
      alert('无法访问麦克风，请检查权限设置')
    }
  }

  const handleAttachClick = () => {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.csv,.xlsx,.json,.sql,.txt'
    input.onchange = () => {
      const file = input.files?.[0]
      if (file) alert(`已选择文件: ${file.name}，文件上传功能待后端对接`)
    }
    input.click()
  }

  const handleSendMessage = async (textToSend?: string) => {
    const rawText = textToSend || inputText.trim()
    if (!rawText) return

    const userMsg: ChatMessage = {
      id: 'usr_' + Date.now(),
      sender: 'user',
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      text: rawText,
    }

    setMessages(prev => [...prev, userMsg])
    if (!textToSend) setInputText('')
    setIsLoading(true)

    try {
      const result = await queryApi.submit(rawText)
      let chartData: { label: string; value: number; type: 'normal' | 'anomaly' }[] | undefined

      if (result.chart) {
        try {
          chartData = (result.chart as { data?: { label?: string; value?: number; type?: string }[] })?.data?.map(item => ({
            label: item.label || '',
            value: item.value || 0,
            type: item.type === 'anomaly' ? 'anomaly' as const : 'normal' as const,
          }))
        } catch { /* ignore */ }
      } else if (result.data && result.data.length > 0) {
        // 尝试从结果数据中提取图表信息
        const keys = Object.keys(result.data[0])
        if (keys.length >= 2) {
          const labelKey = keys.find(k => /name|label|region|city/i.test(k)) || keys[0]
          const valueKey = keys.find(k => /amount|value|total|sum|count/i.test(k)) || keys[1]
          chartData = result.data.slice(0, 6).map((row, i) => ({
            label: String(row[labelKey] ?? `Item ${i + 1}`),
            value: Number(row[valueKey]) || 0,
            type: 'normal' as const,
          }))
        }
      }

      const assistantMsg: ChatMessage = {
        id: 'ast_' + Date.now(),
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: result.summary || result.sql || '查询完成，已返回数据。',
        chartData,
      }

      setMessages(prev => [...prev, assistantMsg])
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: 'err_' + Date.now(),
        sender: 'assistant',
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        text: '抱歉，查询执行失败：' + (err instanceof Error ? err.message : '未知错误'),
      }
      setMessages(prev => [...prev, errorMsg])
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.35, ease: 'easeOut' }}
      className="flex p-1 gap-6 overflow-hidden h-[calc(100vh-140px)] select-none"
    >
      {/* Left: Chat */}
      <section className="flex-1 panel rounded-xl flex flex-col overflow-hidden relative">
        <div className="h-14 border-b border-slate-200 bg-white/50 flex justify-between items-center px-4 shrink-0 select-none">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-slate-100 flex items-center justify-center border border-slate-200 shadow-sm">
              <Bot className="h-4.5 w-4.5 text-slate-800" />
            </div>
            <div>
              <h2 className="text-xs font-black text-slate-800">AI 智能数据分析台</h2>
              <p className="text-[9px] text-slate-500 font-mono tracking-wider">Micro-GenBI · DeepSeek-V3</p>
            </div>
          </div>
          <div className="flex gap-2">
            <button className="text-[10px] bg-white/50 hover:bg-black/5 text-slate-700 font-bold px-2.5 py-1 rounded border border-slate-200 shadow-sm flex items-center gap-1 cursor-pointer transition-colors">
              <Compass className="h-3.5 w-3.5 text-slate-850" />
              <span>智能探索</span>
            </button>
          </div>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4 select-text">
          {messages.map((msg) => {
            const isAI = msg.sender === 'assistant'
            return (
              <div
                key={msg.id}
                className={`flex gap-3 max-w-[85%] ${isAI ? 'mr-auto items-start' : 'ml-auto flex-row-reverse text-right'}`}
              >
                <div className={`w-8 h-8 rounded-full shrink-0 flex items-center justify-center border ${
                  isAI ? 'bg-slate-100 text-slate-800 border-slate-200' : 'bg-indigo-500 text-white border-indigo-600 shadow'
                }`}>
                  {isAI ? <Bot className="h-4 w-4" /> : <User className="h-4 w-4" />}
                </div>

                <div className="space-y-1.5">
                  <div className="text-[10px] text-slate-500 font-mono flex items-center gap-1">
                    <span>{isAI ? 'Micro-GenBI Core' : 'Federated User'}</span>
                    <span>·</span>
                    <span>{msg.timestamp}</span>
                  </div>

                  <div className={`p-3.5 rounded-2xl text-xs font-medium leading-relaxed shadow-sm border ${
                    isAI ? 'bg-white/80 border-slate-200/50 text-slate-800 rounded-tl-sm' : 'bg-indigo-500 text-white border-indigo-600 rounded-tr-sm text-left'
                  }`}>
                    <p>{msg.text}</p>

                    {msg.chartData && msg.chartData.length > 0 && (
                      <div className="mt-4 border-t border-slate-200 pt-3 space-y-2.5 w-72 md:w-96 select-none">
                        <div className="text-[10px] tracking-wider font-extrabold text-slate-505 uppercase flex items-center gap-1">
                          <BarChart2 className="h-3 w-3 text-slate-800" />
                          <span>查询结果</span>
                        </div>
                        <div className="space-y-2.5">
                          {msg.chartData.map((node, i) => (
                            <div key={i} className="space-y-1">
                              <div className="flex justify-between text-[11px] font-bold">
                                <span className={node.type === 'anomaly' ? 'text-red-600' : 'text-slate-700'}>
                                  {node.label}
                                </span>
                                <span className="font-mono text-slate-500">
                                  {typeof node.value === 'number' && node.value > 10000
                                    ? '$' + (node.value / 1000000).toFixed(1) + 'M'
                                    : String(node.value)}
                                </span>
                              </div>
                              <div className="relative h-1.5 w-full bg-slate-100 rounded-full overflow-hidden">
                                <div
                                  className={`absolute top-0 left-0 h-1.5 rounded-full transition-all duration-500 ${
                                    node.type === 'anomaly' ? 'bg-red-500 animate-pulse' : 'bg-indigo-500'
                                  }`}
                                  style={{ width: `${Math.min((node.value / (Math.max(...msg.chartData!.map(d => d.value)))) * 100, 100)}%` }}
                                />
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )
          })}

          {isLoading && (
            <div className="flex gap-3 items-center text-xs text-slate-500 pl-11 select-none">
              <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-800" />
              <span className="font-semibold font-mono tracking-wide">GenBI 正在分析查询...</span>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="p-4 border-t border-slate-200 bg-white/30 shrink-0">
          <div className="flex gap-2 overflow-x-auto pb-3 select-none">
            {quickPrompts.map((p) => (
              <button
                key={p}
                onClick={() => handleSendMessage(p)}
                className="bg-white/50 border border-slate-200 hover:bg-black/5 hover:text-slate-900 text-[10px] font-bold text-slate-600 px-3 py-1.5 rounded-full shadow-sm cursor-pointer whitespace-nowrap tracking-wide select-none transition-all"
              >
                {p}
              </button>
            ))}
          </div>

          <div className="panel rounded-full px-4 py-2.5 flex items-center gap-3 border border-slate-200 shadow-md bg-white/60 text-slate-800 relative" ref={inputContainerRef}>
            <button className="p-1 text-slate-400 hover:text-slate-900 rounded" title="表情"><Smile className="h-4.5 w-4.5" /></button>
            <button className="p-1 text-slate-400 hover:text-slate-900 rounded" onClick={handleAttachClick} title="附件"><Paperclip className="h-4.5 w-4.5" /></button>
            <input
              value={inputText}
              onChange={(e) => { setInputText(e.target.value); setShowSuggestions(e.target.value.length >= 2) }}
              onKeyDown={(e) => { if (e.key === 'Enter') { handleSendMessage(); setShowSuggestions(false) } }}
              onFocus={() => inputText.length >= 2 && setShowSuggestions(true)}
              className="flex-1 text-xs border-none focus:outline-none placeholder-slate-400 font-semibold bg-transparent text-slate-800"
              placeholder="说说想要 analysis 的数据，例如：杭州本季度订单率..."
              type="text"
            />
            {showSuggestions && (
              <SuggestionDropdown
                input={inputText}
                onSelect={(text) => { setInputText(text); handleSendMessage(text); setShowSuggestions(false) }}
                onClose={() => setShowSuggestions(false)}
                containerRef={inputContainerRef}
              />
            )}
            <button className="p-1 text-slate-400 hover:text-slate-900 rounded" onClick={handleMicClick} title="语音输入"><Mic className={`h-4.5 w-4.5 ${isRecording ? 'text-red-500 animate-pulse' : ''}`} /></button>
            <button
              onClick={() => handleSendMessage()}
              disabled={isLoading}
              className="w-8 h-8 rounded-full bg-indigo-500 hover:bg-indigo-600 text-white flex items-center justify-center transition-all shadow-md cursor-pointer disabled:opacity-50"
            >
              <Send className="h-3.5 w-3.5" />
            </button>
          </div>
        </div>
      </section>

      {/* Right: Analysis Snapshot */}
      <section className="w-80 panel bg-white/40 rounded-xl p-4 flex flex-col justify-between overflow-hidden">
        <div className="space-y-4 select-none">
          <div className="flex gap-2 items-center pb-3 border-b border-slate-200">
            <Sparkles className="h-5 w-5 text-slate-900" />
            <h3 className="text-xs font-black uppercase text-slate-800 tracking-wider">智能分析快照</h3>
          </div>

          <div className="p-3 bg-emerald-50 rounded-xl border border-emerald-200">
            <div className="flex items-center gap-1.5 text-xs font-bold text-emerald-700 mb-1">
              <FileCheck2 className="h-4 w-4" />
              <span>系统就绪</span>
            </div>
            <p className="text-[11px] text-slate-600 font-medium leading-relaxed">
              输入自然语言问题，AI 将自动生成 SQL 并返回分析结果。
            </p>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between items-center text-[11px] font-bold">
              <span className="text-slate-500">查询模式</span>
              <span className="text-slate-800">自然语言 → SQL</span>
            </div>
            <div className="flex justify-between items-center text-[11px] font-bold">
              <span className="text-slate-500">支持的数据库</span>
              <span className="text-slate-800">PostgreSQL / MySQL</span>
            </div>
          </div>
        </div>

        <div className="bg-slate-50 p-3 rounded-lg border border-slate-200 select-none">
          <span className="text-[9px] font-extrabold text-slate-800 uppercase tracking-widest block mb-0.5">AI 隐私协议保护</span>
          <p className="text-[10px] text-slate-500">
            联邦查询对话不进行外部模型训练，数据在省中心隔离节点加密执行。
          </p>
        </div>
      </section>
    </motion.div>
  )
}
