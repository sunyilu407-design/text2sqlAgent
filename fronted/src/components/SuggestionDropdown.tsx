/**
 * SuggestionDropdown — 查询建议下拉组件
 * 根据用户输入实时显示查询建议（模板、历史、字段、时间等类型）
 */
import { useEffect, useRef, type RefObject } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { Sparkles, History, Database, Calendar, ArrowRight, Search } from 'lucide-react'
import { useQuerySuggestions } from '../hooks/useQueries'
import type { QuerySuggestion } from '../api'

const TYPE_CONFIG: Record<string, { icon: typeof Sparkles; label: string; color: string }> = {
  template: { icon: Sparkles, label: '查询模板', color: 'text-purple-500' },
  history: { icon: History, label: '历史查询', color: 'text-blue-500' },
  field: { icon: Database, label: '字段联想', color: 'text-green-500' },
  time: { icon: Calendar, label: '时间扩展', color: 'text-orange-500' },
  expansion: { icon: ArrowRight, label: '查询扩展', color: 'text-teal-500' },
}

interface SuggestionDropdownProps {
  input: string
  onSelect: (text: string) => void
  onClose: () => void
  containerRef?: RefObject<HTMLElement>
}

export default function SuggestionDropdown({ input, onSelect, onClose, containerRef }: SuggestionDropdownProps) {
  const { data, isLoading } = useQuerySuggestions(input)
  const dropdownRef = useRef<HTMLDivElement>(null)

  const suggestions: QuerySuggestion[] = data?.suggestions ?? []

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node) &&
        containerRef?.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [onClose, containerRef])

  if (!input.trim() || input.length < 2) return null

  return (
    <motion.div
      ref={dropdownRef}
      initial={{ opacity: 0, y: -4 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -4 }}
      transition={{ duration: 0.15 }}
      className="absolute bottom-full left-0 right-0 mb-1 z-50"
    >
      <div className="panel rounded-xl shadow-xl border border-white/20 overflow-hidden">
        {isLoading ? (
          <div className="px-3 py-2.5 text-xs text-gray-400 flex items-center gap-2">
            <Search className="h-3.5 w-3.5 animate-pulse" />
            正在获取建议...
          </div>
        ) : suggestions.length === 0 ? (
          <div className="px-3 py-2.5 text-xs text-gray-400 flex items-center gap-2">
            <Sparkles className="h-3.5 w-3.5" />
            暂无相关建议，试试更通用的关键词
          </div>
        ) : (
          <ul className="divide-y divide-white/10">
            {suggestions.map((s, idx) => {
              const cfg = TYPE_CONFIG[s.type] ?? TYPE_CONFIG.expansion
              const Icon = cfg.icon
              return (
                <li key={idx}>
                  <button
                    onClick={() => { onSelect(s.text); onClose() }}
                    className="w-full px-3 py-2 flex items-center gap-2.5 hover:bg-white/20 transition-colors text-left"
                  >
                    <Icon className={`h-3.5 w-3.5 shrink-0 ${cfg.color}`} />
                    <span className="text-xs font-medium text-slate-700 flex-1 truncate">
                      {s.text}
                    </span>
                    <span className={`text-[10px] font-semibold shrink-0 ${cfg.color}`}>
                      {cfg.label}
                    </span>
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>
    </motion.div>
  )
}
