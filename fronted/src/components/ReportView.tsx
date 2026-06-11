/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect, useCallback } from 'react';
import {
  FileText,
  AlertTriangle,
  Sparkles,
  CheckCircle2,
  TrendingDown,
  Clock,
  Volume2,
  RefreshCw,
  Loader2,
  Database,
  X,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { queryApi, type QueryResult } from '../api';

interface TodoItem {
  id: number;
  text: string;
  priority: '高' | '中' | '低';
  checked: boolean;
}

const TODOS_STORAGE_KEY = 'mgbi_report_todos';

function loadTodos(): TodoItem[] {
  try {
    const raw = localStorage.getItem(TODOS_STORAGE_KEY);
    if (raw) return JSON.parse(raw) as TodoItem[];
  } catch { /* ignore */ }
  return [
    { id: 1, text: '开启分流预案 (激活备用卡车车队以缓解港口阻塞)', priority: '高', checked: true },
    { id: 2, text: '启动海关报关延迟索赔索补 (针对滞港订单)', priority: '中', checked: false },
    { id: 3, text: '预拨多渠道航空备货渠道 (针对高单价奢侈品类)', priority: '高', checked: false },
    { id: 4, text: '向相关客户发送延期交货温馨声明', priority: '低', checked: true },
  ];
}

function saveTodos(todos: TodoItem[]): void {
  try {
    localStorage.setItem(TODOS_STORAGE_KEY, JSON.stringify(todos));
  } catch { /* ignore */ }
}

const REGENERATE_QUERY = '宁波地区营收下降原因分析';

export default function ReportView() {
  const [queryResult, setQueryResult] = useState<QueryResult | null>(null);
  const [reportLoading, setReportLoading] = useState(false);
  const [regenerateError, setRegenerateError] = useState<string | null>(null);
  const [audioPlaying, setAudioPlaying] = useState(false);
  const [todoList, setTodoList] = useState<TodoItem[]>(loadTodos);

  useEffect(() => {
    setReportLoading(true);
    queryApi.submit(REGENERATE_QUERY, { generate_chart: true })
      .then(result => {
        setQueryResult(result);
        setRegenerateError(null);
      })
      .catch(() => {
        setRegenerateError('数据加载失败，请稍后重试');
      })
      .finally(() => {
        setReportLoading(false);
      });
  }, []);

  const toggleTodo = useCallback((id: number) => {
    setTodoList(prev => {
      const updated = prev.map(todo =>
        todo.id === id ? { ...todo, checked: !todo.checked } : todo
      );
      saveTodos(updated);
      return updated;
    });
  }, []);

  const handleAudioClick = () => {
    if (!('speechSynthesis' in window)) {
      alert('当前浏览器不支持语音合成')
      return
    }
    const text = typeof queryResult?.summary === 'string' && queryResult.summary
      ? queryResult.summary
      : '暂无分析结果可朗读'
    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'zh-CN'
    utterance.rate = 0.9
    utterance.onstart = () => setAudioPlaying(true)
    utterance.onend = () => setAudioPlaying(false)
    utterance.onerror = () => setAudioPlaying(false)
    speechSynthesis.cancel()
    speechSynthesis.speak(utterance)
  }

  const handleRegenerate = useCallback(() => {
    setReportLoading(true);
    setRegenerateError(null);
    queryApi.submit(REGENERATE_QUERY, { generate_chart: true })
      .then(result => {
        setQueryResult(result);
        setRegenerateError(null);
      })
      .catch(() => {
        setRegenerateError('重新分析失败，请稍后重试');
      })
      .finally(() => {
        setReportLoading(false);
      });
  }, []);

  const completedCount = todoList.filter(t => t.checked).length;
  const progressPct = Math.round((completedCount / todoList.length) * 100);

  const aiSummary = queryResult?.summary ?? '正在分析中...';

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.98 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.98 }}
      transition={{ duration: 0.35 }}
      className="space-y-6 pb-20 select-none text-gray-800"
    >

      {/* Top action header info */}
      <header className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1 text-xs font-mono font-bold text-slate-600 bg-slate-100 w-fit px-2.5 py-0.5 rounded-full select-none border border-slate-200">
            <FileText className="h-3 w-3 text-black" />
            <span>ID: AI-REP-2026-05</span>
          </div>
          <h1 className="font-display text-4xl font-extrabold text-slate-900 tracking-tight leading-none animate-fade-in">
            宁波地区营收下降分析
          </h1>
          <p className="text-sm text-slate-500 mt-1 font-sans">
            AI-Generated Deep Cause Analysis Report.
          </p>
        </div>

        <div className="flex gap-2 shrink-0 select-none">
          <button
            onClick={handleAudioClick}
            className="p-2 bg-black/5 border border-slate-200 hover:bg-black/10 text-slate-700 rounded-lg transition-colors flex items-center justify-center cursor-pointer"
          >
            <Volume2 className={`h-4.5 w-4.5 ${audioPlaying ? 'text-black animate-bounce' : ''}`} />
          </button>

          <button
            disabled={reportLoading}
            onClick={handleRegenerate}
            className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-xs font-semibold text-white rounded-lg transition-colors flex items-center gap-1.5 cursor-pointer shadow-sm hover:shadow-md disabled:opacity-60"
          >
            {reportLoading ? (
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
            ) : (
              <Sparkles className="h-3.5 w-3.5 text-white" />
            )}
            <span>重新分析</span>
          </button>
        </div>
      </header>

      {/* Main Grid Content Area */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">

        {/* Left Side: Core Report and Analytical Graphics (cols 1-8) */}
        <div className="xl:col-span-8 flex flex-col gap-6">

          {/* AI core verdict summary banner panel */}
          <div className="relative rounded-2xl p-6 overflow-hidden bg-gradient-to-r from-red-500/15 to-orange-500/5 border border-red-500/20 shadow-sm flex flex-col md:flex-row gap-4 items-start">
            <div className="absolute top-0 right-0 w-32 h-32 bg-red-500/5 rounded-full blur-2xl pointer-events-none"></div>

            <div className="w-10 h-10 rounded-xl bg-red-500/20 flex items-center justify-center shrink-0 border border-red-500/20">
              <AlertTriangle className="h-5 w-5 text-red-400" />
            </div>

            <div className="space-y-2 flex-1">
              <h2 className="text-xs font-bold text-red-600 uppercase tracking-widest leading-none select-none">
                AI 核心诊断结论
              </h2>
              {reportLoading ? (
                <div className="flex items-center gap-2">
                  <Loader2 className="h-4 w-4 animate-spin text-slate-400" />
                  <p className="text-sm text-slate-500 italic">正在生成分析...</p>
                </div>
              ) : regenerateError ? (
                <p className="text-sm font-bold text-red-500 leading-relaxed">{regenerateError}</p>
              ) : (
                <p className="text-sm font-bold text-slate-800 leading-relaxed font-sans">
                  {aiSummary}
                </p>
              )}
            </div>
          </div>

          {/* Query result metrics summary */}
          {queryResult && (
            <div className="panel rounded-xl p-5 grid grid-cols-2 md:grid-cols-4 gap-4">
              <div className="text-center">
                <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">执行时间</p>
                <p className="text-lg font-bold text-slate-900 font-mono">{queryResult.executionTimeMs}ms</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">结果行数</p>
                <p className="text-lg font-bold text-slate-900 font-mono">{queryResult.rowCount}</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">查询意图</p>
                <p className="text-lg font-bold text-slate-900 font-mono">{queryResult.intent ?? '—'}</p>
              </div>
              <div className="text-center">
                <p className="text-[10px] text-slate-500 font-bold uppercase tracking-wider">置信度</p>
                <p className="text-lg font-bold text-slate-900 font-mono">
                  {queryResult.confidence != null ? `${Math.round(queryResult.confidence * 100)}%` : '—'}
                </p>
              </div>
            </div>
          )}

          {/* Dynamic customized SVG dual-line column comparison chart */}
          <section className="panel rounded-xl p-5">
            <div className="flex justify-between items-center mb-6">
              <div>
                <h3 className="text-sm font-bold text-slate-900">履约时效指标对比 (ECharts Styled SVG Map)</h3>
                <p className="text-[10px] text-slate-500 font-medium">对比正常基线期待值与本月异常表现</p>
              </div>

              {/* Legend pills */}
              <div className="flex gap-4 text-[10px] font-bold">
                <div className="flex items-center gap-1.5 text-slate-600">
                  <span className="w-3 h-3 rounded-full bg-indigo-500"></span>
                  <span>基线目标 (Expected Value)</span>
                </div>
                <div className="flex items-center gap-1.5 text-orange-600">
                  <span className="w-3 h-3 rounded-full bg-orange-500"></span>
                  <span>真实业绩 (Actual Metric)</span>
                </div>
              </div>
            </div>

            {/* Custom crafted SVG comparison chart mapping categories */}
            <div className="relative h-64 flex flex-col justify-end">
              <div className="absolute inset-x-0 top-0 h-[200px] flex flex-col justify-between pointer-events-none opacity-5">
                <div className="border-b border-black w-full"></div>
                <div className="border-b border-black w-full"></div>
                <div className="border-b border-black w-full"></div>
                <div className="border-b border-black w-full"></div>
              </div>

              {/* SVG pillars block */}
              <div className="h-[200px] w-full flex justify-around items-end relative z-10 px-8">

                {/* Metric 1: Fulfillment Rate: expected 98% vs actual 74% */}
                <div className="flex flex-col items-center gap-2 group w-24">
                  <div className="flex gap-1.5 items-end justify-center h-44">
                    {/* Normal Expected column bar */}
                    <div className="w-6 bg-indigo-400 rounded-t-sm h-[98%] shadow-sm hover:brightness-110 transition-all flex items-end justify-center">
                      <span className="text-[9px] text-white font-mono font-bold mb-1">98%</span>
                    </div>
                    {/* Actual alert columns bar */}
                    <div className="w-6 bg-orange-500/85 rounded-t-sm h-[74%] shadow-sm hover:brightness-110 transition-all flex items-end justify-center">
                      <span className="text-[9px] text-white font-mono font-bold mb-1">74%</span>
                    </div>
                  </div>
                  <span className="text-xs font-bold text-slate-600">履约完成率</span>
                </div>

                {/* Metric 2: Transit hours (Demurrage baseline 12h vs 28h actual) */}
                <div className="flex flex-col items-center gap-2 group w-24">
                  <div className="flex gap-1.5 items-end justify-center h-44">
                    <div className="w-6 bg-indigo-400 rounded-t-sm h-[32%] shadow-sm flex items-end justify-center">
                      <span className="text-[9px] text-white font-mono font-bold mb-1">12h</span>
                    </div>
                    <div className="w-6 bg-orange-500/85 rounded-t-sm h-[88%] shadow-sm flex items-end justify-center">
                      <span className="text-[9px] text-white font-mono font-bold mb-1">28h</span>
                    </div>
                  </div>
                  <span className="text-xs font-bold text-slate-600">平均过境时长</span>
                </div>

                {/* Metric 3: Exception Resolution rate (94% vs 42%) */}
                <div className="flex flex-col items-center gap-2 group w-24">
                  <div className="flex gap-1.5 items-end justify-center h-44">
                    <div className="w-6 bg-indigo-400 rounded-t-sm h-[94%] shadow-sm flex items-end justify-center">
                      <span className="text-[9px] text-white font-mono font-bold mb-1">94%</span>
                    </div>
                    <div className="w-6 bg-orange-500/85 rounded-t-sm h-[42%] shadow-sm flex items-end justify-center">
                      <span className="text-[9px] text-white font-mono font-bold mb-1">42%</span>
                    </div>
                  </div>
                  <span className="text-xs font-bold text-slate-600">异常瞬时解决率</span>
                </div>

              </div>
            </div>
          </section>

          {/* Structured Text Content Details: Deep AI analysis breakdown text cards */}
          <section className="panel rounded-xl p-5 space-y-4">
            <h3 className="text-sm font-bold text-slate-900">深度逻辑诊断分析</h3>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white/40 border border-slate-200/50 p-4 rounded-xl">
                <div className="flex items-center gap-2 mb-2 font-bold text-xs text-orange-600">
                  <Clock className="h-4.5 w-4.5" />
                  <span>阶段一：物流堆积，港口脱轨</span>
                </div>
                <p className="text-xs text-slate-600 font-medium leading-relaxed">
                  通过联邦多数据库模型排查发现，自五号起，宁波及北仑港区周边的集卡过境运输速度环比骤降54%，导致已经申报的出口货物无法如期集港封箱，形成了严重的供给侧瓶颈。
                </p>
              </div>

              <div className="bg-white/40 border border-slate-200/50 p-4 rounded-xl">
                <div className="flex items-center gap-2 mb-2 font-bold text-xs text-slate-900">
                  <TrendingDown className="h-4.5 w-4.5" />
                  <span>阶段二：信用证阻滞与应收未结</span>
                </div>
                <p className="text-xs text-slate-600 font-medium leading-relaxed">
                  大量的不可抗力延迟，阻碍了外贸业务常规的议付单证转交。结算部通过财务DW数据核实，部分大单由于结算条件未达（缺少装船批注），拖延了回笼结算，造成了表面的销售下降。
                </p>
              </div>
            </div>
          </section>

        </div>

        {/* Right Side Column Panels (cols 9-12) */}
        <div className="xl:col-span-4 flex flex-col gap-6">

          {/* Action List interactive Card view with local checklist progress tracking */}
          <section className="panel-elevated rounded-xl p-5 flex flex-col justify-between">
            <div>
              <div className="flex justify-between items-center mb-4 select-none">
                <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">
                  AI Action Plan
                </h3>
                <span className="bg-indigo-500 text-white px-2 py-0.5 rounded text-[10px] font-mono font-bold border border-indigo-300">
                  {progressPct}% 完成
                </span>
              </div>

              <div className="space-y-3">
                {todoList.map((todo) => (
                  <div
                    key={todo.id}
                    onClick={() => toggleTodo(todo.id)}
                    className={`p-3 rounded-lg border flex items-start gap-2.5 cursor-pointer selection:bg-transparent transition-all ${
                      todo.checked
                        ? 'bg-black/2 border-slate-200 opacity-50'
                        : 'bg-white/40 border-slate-200 hover:bg-black/5'
                    }`}
                  >
                    <div className="mt-0.5">
                      {todo.checked ? (
                        <CheckCircle2 className="h-4.5 w-4.5 text-black" />
                      ) : (
                        <div className="w-4.5 h-4.5 rounded-full border-2 border-slate-400/40"></div>
                      )}
                    </div>

                    <div className="flex-1">
                      <p className={`text-xs font-semibold leading-tight ${todo.checked ? 'line-through text-slate-400' : 'text-slate-900'}`}>
                        {todo.text}
                      </p>

                      <div className="flex gap-2 items-center mt-2.5">
                        <span className={`text-[9px] font-extrabold px-1.5 py-0.5 rounded ${
                          todo.priority === '高'
                            ? 'bg-red-500/10 text-red-600 border border-red-500/20'
                            : todo.priority === '中'
                              ? 'bg-amber-500/10 text-amber-600 border border-amber-500/20'
                              : 'bg-slate-500/10 text-slate-500 border border-slate-500/20'
                        }`}>
                          {todo.priority}优先级
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="w-full bg-slate-200 rounded-full h-1.5 mt-6 overflow-hidden">
              <div className="bg-indigo-500 h-1.5 rounded-full transition-all duration-500" style={{ width: `${progressPct}%` }}></div>
            </div>
          </section>

          {/* Secondary Stats panel: Key Impact level ranking (关联度排名 with custom progress bars) */}
          <section className="panel rounded-xl p-5 space-y-4 select-none">
            <h3 className="text-xs font-bold text-slate-500 uppercase tracking-widest">
              下压因子关联度排名
            </h3>

            <div className="space-y-4">
              {[
                { title: '供应链卡车滞港阻滞', ratio: '0.94', status: 'critical', bar: 'w-[94%] bg-status-p0' },
                { title: '仓储多库分仓滞压', ratio: '0.62', status: 'caution', bar: 'w-[62%] bg-status-p1' },
                { title: '区域消费者信心指数', ratio: '0.15', status: 'normal', bar: 'w-[15%] bg-status-p2' },
              ].map((fact) => (
                <div key={fact.title} className="space-y-1">
                  <div className="flex justify-between items-center text-xs font-bold text-slate-800">
                    <span>{fact.title}</span>
                    <span className="font-mono text-[11px] text-slate-400">Impact: +{fact.ratio}</span>
                  </div>

                  <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
                    <div className={`h-1.5 rounded-full ${fact.bar}`}></div>
                  </div>
                </div>
              ))}
            </div>

            <div className="bg-gradient-to-tr from-black/5 to-black/1 p-3 rounded-lg border border-slate-200 select-none">
              <span className="text-[10px] font-extrabold text-slate-800 uppercase tracking-wider block mb-1">
                AI 优化建议
              </span>
              <p className="text-[11px] text-slate-600 leading-normal">
                目前"卡车阻滞"因素权重已提升至0.94，极高。建议销售组立即将发货路线分流至上海、太仓、温州等副港口，降低出口压仓损失。
              </p>
            </div>
          </section>

        </div>

      </div>

    </motion.div>
  );
}
