/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, FormEvent, useEffect } from 'react';
import { motion } from 'motion/react';
import {
  Save,
  HelpCircle,
  HardDrive,
  Cpu,
  Sliders,
  ShieldCheck,
  KeyRound,
  Globe,
  CheckCircle2,
  Sun,
  Moon,
  Monitor,
  Copy,
  ChevronDown,
  Terminal,
  Palette,
} from 'lucide-react';
import { adminApi } from '../api';
import { LLMConfig } from '../types';
import { useAuth } from '../context/AuthContext';
import ApiKeyPanel from './ApiKeyPanel';

interface SettingsViewProps {
  config: LLMConfig;
  onSaveConfig: (updated: LLMConfig) => void;
}

export default function SettingsView({
  config,
  onSaveConfig,
}: SettingsViewProps) {
  const { user } = useAuth()
  const [endpoint, setEndpoint] = useState(config.endpoint);
  const [apiKey, setApiKey] = useState(config.apiKey);
  const [modelName, setModelName] = useState(config.modelName);
  const [temperature, setTemperature] = useState(config.temperature);
  const [maxTokens, setMaxTokens] = useState(config.maxTokens);

  const [isSaved, setIsSaved] = useState(false);

  // Appearance state — supports light, dark, and system themes
  const [theme, setTheme] = useState<'light' | 'dark' | 'system'>(() => {
    const saved = localStorage.getItem('mgbi_theme') as 'light' | 'dark' | 'system' | null;
    return saved || 'light';
  });
  const [language, setLanguage] = useState(() => {
    return localStorage.getItem('mgbi_language') || 'zh';
  });

  // Sample code state
  const [showSampleCode, setShowSampleCode] = useState(false);
  const [copied, setCopied] = useState(false);

  // API Key Management state
  // Apply theme on mount and when theme changes
  useEffect(() => {
    const root = document.documentElement;
    localStorage.setItem('mgbi_theme', theme);

    if (theme === 'dark') {
      root.classList.add('dark');
    } else if (theme === 'light') {
      root.classList.remove('dark');
    } else {
      // system preference
      const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.classList.toggle('dark', prefersDark);
    }
  }, [theme]);

  const handleThemeChange = (newTheme: 'light' | 'dark' | 'system') => {
    setTheme(newTheme);
  };

  const handleLanguageChange = (lang: string) => {
    setLanguage(lang);
    localStorage.setItem('mgbi_language', lang);
  };

  const copyToClipboard = async (text: string) => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const languageLabels: Record<string, string> = {
    zh: '简体中文',
    en: 'English',
    ja: '日本語',
  };

  const themeIcons = {
    light: Sun,
    dark: Moon,
    system: Monitor,
  };

  const sampleCurlCode = `curl -X POST https://your-api.com/api/v1/query \\
  -H "Authorization: Bearer YOUR_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"text": "查询本月销售额"}'`;

  const handleSave = (e: FormEvent) => {
    e.preventDefault();
    onSaveConfig({
      endpoint,
      apiKey,
      modelName,
      temperature,
      maxTokens,
    });
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2000);
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6" id="settings-container">
      {/* Upper header section */}
      <div className="flex justify-between items-end">
        <div>
          <h1 className="font-display text-4xl font-extrabold text-slate-900 tracking-tight">
            运行属性设置
          </h1>
          <p className="text-sm text-slate-500 mt-1 font-sans">
            管理当前节点的 LLM 大模型调用网关、API 凭证、安全策略和订阅控制配额。
          </p>
        </div>
        
        {user && (
          <div className="flex items-center gap-2 px-3 py-1.5 bg-white/40 border border-slate-200 rounded-xl max-w-xs">
            <ShieldCheck className="h-4.5 w-4.5 text-slate-700" />
            <div className="text-left font-sans text-xs">
              <p className="font-bold text-slate-800 truncate">{user.username}</p>
              <p className="text-[10px] text-slate-400 capitalize">{user.role === 'admin' ? '👑 系统运维管理员' : '👤 联邦普通用户'}</p>
            </div>
          </div>
        )}
      </div>

      {isSaved && (
        <motion.div 
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-xs text-emerald-700 font-bold flex items-center gap-2"
        >
          <CheckCircle2 className="h-4.5 w-4.5" />
          <span>大语言模型代理设置与节点 API 参数已在本地成功持久化。</span>
        </motion.div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        
        {/* Profile Card & Version Controller */}
        <div className="md:col-span-1 space-y-6">
          <section className="panel p-5 rounded-2xl bg-white/40 border border-slate-200">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider mb-4">当前账号环境</h2>
            <div className="space-y-4">
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500 font-semibold">角色级别:</span>
                <span className="font-bold text-slate-900 bg-slate-100 rounded-md px-2 py-0.5">
                  {user?.role === 'admin' ? '系统管理员' : '普通分析员'}
                </span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500 font-semibold">业务归组:</span>
                <span className="font-bold text-slate-800">{user?.group || '未分组'}</span>
              </div>
              <div className="flex justify-between items-center text-xs">
                <span className="text-slate-500 font-semibold">接入序列号:</span>
                <span className="font-mono text-slate-400 text-[10px]">#MB-{Math.floor(user?.createdAt ? new Date(user.createdAt).getTime() / 1000000 : 4329048).toString(16)}</span>
              </div>
            </div>
          </section>

          <section className="panel p-5 rounded-2xl bg-white/40 border border-slate-200 space-y-4">
            <h2 className="text-xs font-bold text-slate-400 uppercase tracking-wider">订阅与调用控制</h2>
            <div className="p-3.5 rounded-xl border border-dashed border-slate-200 bg-white/20 select-none">
              <span className="text-[10px] font-extrabold text-slate-500 uppercase tracking-widest block mb-1">
                当前限流额度
              </span>
              <p className="text-xs font-black text-slate-800 uppercase tracking-tight">
                {user?.subscriptionPlan === 'free' ? '免费级 (20 QPM / Min)' : user?.subscriptionPlan === 'enterprise' ? '企业集群级 (不设限)' : '专业级 (1,200 QPM / Min)'}
              </p>
            </div>

              <div className="space-y-2">
              <p className="text-[11px] text-slate-500 font-semibold">订阅版本：</p>
              <div className="grid grid-cols-1 gap-2">
                {(['free', 'pro', 'enterprise'] as const).map((tier) => (
                  <div
                    key={tier}
                    className={`py-1.5 px-3 rounded-lg text-xs font-bold border flex justify-between items-center ${
                      user?.subscriptionPlan === tier
                        ? 'border-indigo-500 bg-indigo-500 text-white shadow-xs'
                        : 'border-slate-200 bg-white/40 text-slate-700 hover:bg-indigo-50'
                    }`}
                  >
                    <span className="capitalize">{tier === 'free' ? '免费版 (Free)' : tier === 'pro' ? '专业商业版 (Pro)' : '尊享企业版 (Enterprise)'}</span>
                    {user?.subscriptionPlan === tier && <span className="text-[9px] px-1 bg-white text-black font-semibold rounded">Active</span>}
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* Appearance & Theme Section */}
          <section className="panel p-5 rounded-2xl bg-white/40 border border-slate-200 space-y-4">
            <div className="flex items-center gap-2 mb-4">
              <Palette className="h-4 w-4 text-slate-700" />
              <h2 className="text-xs font-bold text-slate-900">外观与主题</h2>
            </div>

            {/* Theme — always light */}
            <div>
              <p className="text-[11px] text-slate-500 font-semibold mb-2">主题</p>
              <div className="flex gap-2">
                <button
                  onClick={() => handleThemeChange('light')}
                  className={`flex-1 py-2 px-3 rounded-xl text-xs font-bold border flex flex-col items-center gap-1 transition-all ${
                    theme === 'light'
                      ? 'border-indigo-500 bg-indigo-500 text-white'
                      : 'border-slate-200 bg-white/40 text-slate-500 hover:border-indigo-300 hover:text-indigo-600'
                  }`}
                >
                  <Sun className="h-4 w-4" />
                  <span>浅色</span>
                </button>
                <button
                  onClick={() => handleThemeChange('dark')}
                  className={`flex-1 py-2 px-3 rounded-xl text-xs font-bold border flex flex-col items-center gap-1 transition-all ${
                    theme === 'dark'
                      ? 'border-indigo-500 bg-indigo-500 text-white'
                      : 'border-slate-200 bg-white/40 text-slate-500 hover:border-indigo-300 hover:text-indigo-600'
                  }`}
                >
                  <Moon className="h-4 w-4" />
                  <span>深色</span>
                </button>
                <button
                  onClick={() => handleThemeChange('system')}
                  className={`flex-1 py-2 px-3 rounded-xl text-xs font-bold border flex flex-col items-center gap-1 transition-all ${
                    theme === 'system'
                      ? 'border-indigo-500 bg-indigo-500 text-white'
                      : 'border-slate-200 bg-white/40 text-slate-500 hover:border-indigo-300 hover:text-indigo-600'
                  }`}
                >
                  <Monitor className="h-4 w-4" />
                  <span>跟随系统</span>
                </button>
              </div>
            </div>

            {/* Language Switcher */}
            <div>
              <p className="text-[11px] text-slate-500 font-semibold mb-2">语言切换</p>
              <select
                value={language}
                onChange={(e) => handleLanguageChange(e.target.value)}
                className="w-full text-xs font-semibold px-3 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 appearance-none"
              >
                <option value="zh">简体中文</option>
                <option value="en">English</option>
                <option value="ja">日本語</option>
              </select>
              <span className="text-[10px] text-slate-400 mt-1 block">
                当前显示：{languageLabels[language] || language}
              </span>
            </div>
          </section>

          {/* Sample Code Section */}
          <section className="panel p-5 rounded-2xl bg-white/40 border border-slate-200 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Terminal className="h-4 w-4 text-slate-700" />
                <h2 className="text-xs font-bold text-slate-900">示例代码</h2>
              </div>
              <button
                onClick={() => setShowSampleCode(!showSampleCode)}
                className="text-[11px] text-slate-500 font-semibold hover:text-slate-800 flex items-center gap-1"
              >
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showSampleCode ? 'rotate-180' : ''}`} />
                <span>{showSampleCode ? '收起' : '展开'}</span>
              </button>
            </div>

            {showSampleCode && (
              <motion.div
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: 'auto' }}
                className="relative"
              >
                <div className="absolute top-2 right-2 z-10">
                  <button
                    onClick={() => copyToClipboard(sampleCurlCode)}
                    className="flex items-center gap-1 px-2 py-1 bg-slate-700 hover:bg-slate-600 text-white text-[10px] font-bold rounded-lg transition-colors"
                  >
                    <Copy className="h-3 w-3" />
                    <span>{copied ? '已复制' : '复制'}</span>
                  </button>
                </div>
                <pre className="bg-slate-100 text-slate-800 p-4 rounded-xl text-[11px] font-mono overflow-x-auto">
                  <code>{sampleCurlCode}</code>
                </pre>
              </motion.div>
            )}
          </section>

          {/* API Key Management Section */}
          <section className="panel p-5 rounded-2xl bg-white/40 border border-slate-200 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-slate-700" />
                <h2 className="text-xs font-bold text-slate-900">API Key 管理</h2>
              </div>
            </div>
            <ApiKeyPanel />
          </section>
        </div>

        {/* LLM Configuration Controls */}
        <div className="md:col-span-2">
          <section className="panel p-6 rounded-2xl bg-white/40 border border-slate-200">
            <div className="flex items-center gap-2 mb-6">
              <Cpu className="h-5 w-5 text-slate-800" />
              <h2 className="text-sm font-bold text-slate-900">边缘 LLM 大语言模型代理配置</h2>
            </div>

            <form onSubmit={handleSave} className="space-y-5">
              
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <Globe className="h-3.5 w-3.5 text-slate-500" />
                    <span>大语言模型 API 终结点 (Endpoint)</span>
                  </label>
                  <input
                    value={endpoint}
                    onChange={(e) => setEndpoint(e.target.value)}
                    className="w-full text-xs font-semibold px-3 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 placeholder-slate-400"
                    placeholder="https://api.vertex-genbi.internal/v1"
                    type="text"
                  />
                  <span className="text-[10px] text-slate-400 mt-1 block">
                    指向省数据中心或本地私有部署的 API 代理层。
                  </span>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <KeyRound className="h-3.5 w-3.5 text-slate-500" />
                    <span>API 调用密钥 (API Key)</span>
                  </label>
                  <input
                    value={apiKey}
                    onChange={(e) => setApiKey(e.target.value)}
                    className="w-full text-xs font-semibold px-3 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 placeholder-slate-400 font-mono"
                    placeholder="sk-••••••••••••••••••••••••"
                    type="password"
                  />
                  <span className="text-[10px] text-slate-400 mt-1 block">
                    安全沙箱存储，仅在进行边缘联邦分析服务代理时进行透传。
                  </span>
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <HardDrive className="h-3.5 w-3.5 text-slate-500" />
                    <span>映射大模型名称 (Target Model)</span>
                  </label>
                  <select
                    value={modelName}
                    onChange={(e) => setModelName(e.target.value)}
                    className="w-full text-xs font-semibold px-3 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 appearance-none"
                  >
                    <option value="gemini-3.5-flash">Vertex API: gemini-3.5-flash (默认极速型)</option>
                    <option value="gemini-3.5-pro">Vertex API: gemini-3.5-pro (超长上下文深度诊断型)</option>
                    <option value="local-deepseek-r1">Secure Edge: DeepSeek-R1 (局域网边缘计算节点)</option>
                    <option value="qwen-max">Federated Gateway: Qwen-Max (备用中继大模型)</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5 flex items-center gap-1">
                    <Sliders className="h-3.5 w-3.5 text-slate-500" />
                    <span>最大生成 Token 长度</span>
                  </label>
                  <input
                    type="number"
                    value={maxTokens}
                    onChange={(e) => setMaxTokens(Number(e.target.value))}
                    className="w-full text-xs font-semibold px-3 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800"
                    min={256}
                    max={16384}
                  />
                </div>
              </div>

              <div>
                <div className="flex justify-between items-center mb-1.5">
                  <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider">
                    温度参数 (Temperature): <span className="font-mono text-slate-800">{temperature}</span>
                  </label>
                  <span className="text-[10px] text-slate-500 font-semibold">
                    {temperature === 0 ? '确定性规则检索 (精确模式)' : temperature > 0.7 ? '多元创意性推演 (探索模式)' : '平衡采样'}
                  </span>
                </div>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={temperature}
                  onChange={(e) => setTemperature(parseFloat(e.target.value))}
                  className="w-full h-1.5 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-black"
                />
              </div>

              <div className="pt-4 border-t border-slate-200/50 flex justify-between items-center">
                <div className="flex items-center gap-1.5 text-[11px] text-slate-500 font-semibold hover:underline cursor-pointer">
                  <HelpCircle className="h-4 w-4 text-slate-400" />
                  <span>如何获取我的 API 密钥？</span>
                </div>

                <button
                  type="submit"
                  className="bg-indigo-500 hover:bg-indigo-600 text-white font-bold text-xs py-2 px-5 rounded-xl transition-all cursor-pointer flex items-center gap-1.5 shadow"
                >
                  <Save className="h-3.5 w-3.5" />
                  <span>保存大语言模型配置</span>
                </button>
              </div>

            </form>
          </section>
        </div>

      </div>
    </div>
  );
}
