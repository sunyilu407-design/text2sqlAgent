/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 * 鉴权页面 — 对接 /api/v1/auth/login 和 /auth/register
 */
import { useState, FormEvent } from 'react'
import { motion } from 'motion/react'
import { Mail, Lock, User, Shield, Briefcase, Sparkles, CheckCircle, ArrowRight, Loader2 } from 'lucide-react'
import { useAuth } from '../context/AuthContext'

interface AuthViewProps {
  initialMode?: 'login' | 'register'
}

export default function AuthView({ initialMode = 'login' }: AuthViewProps) {
  const { login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>(initialMode)
  const [email, setEmail] = useState('')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<'user' | 'admin'>('user')
  const [group, setGroup] = useState('财务分析组')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    setError('')

    if (!username || !password || (mode === 'register' && !email)) {
      setError('请填写所有必填字段。')
      return
    }

    if (mode === 'register' && email && !email.includes('@')) {
      setError('请输入有效的电子邮件地址。')
      return
    }

    setLoading(true)
    try {
      if (mode === 'login') {
        await login(username, password)
      } else {
        await register({ username, password, email, role, group })
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : '操作失败，请重试。')
    } finally {
      setLoading(false)
    }
  }

  const handleFastFill = (type: 'user' | 'admin') => {
    if (type === 'admin') {
      setUsername('admin')
      setEmail('admin@microgenbi.cn')
      setPassword('admin123')
      setRole('admin')
      setGroup('系统运维处')
    } else {
      setUsername('analyst')
      setEmail('analyst@microgenbi.cn')
      setPassword('user123')
      setRole('user')
      setGroup('温州业务部')
    }
  }

  return (
    <div className="max-w-md mx-auto my-12" id="auth-container">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        className="panel-elevated rounded-2xl p-8 relative overflow-hidden"
      >
          <div className="absolute top-0 right-0 w-32 h-32 bg-indigo-500/5 rounded-bl-full blur-xl pointer-events-none" />

        <div className="text-center mb-8 select-none">
          <div className="inline-flex p-3 rounded-2xl bg-indigo-500 text-white mb-4 shadow-md">
            <Sparkles className="h-6 w-6" />
          </div>
          <h2 className="font-display text-2xl font-bold text-slate-900 tracking-tight">
            {mode === 'login' ? '欢迎回来' : '注册新账户'}
          </h2>
          <p className="text-xs text-slate-500 mt-1">
            {mode === 'login' ? '输入凭证以安全连接到联邦多库平台' : '设置多库微型分析引擎凭证与访问权限'}
          </p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200/65 rounded-lg text-xs text-red-600 font-semibold leading-relaxed">
            {error}
          </div>
        )}

        {loading ? (
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            className="text-center py-8 space-y-4"
          >
            <div className="inline-flex p-3 bg-emerald-100 text-emerald-600 rounded-full">
              <Loader2 className="h-8 w-8 animate-spin" />
            </div>
            <h3 className="text-sm font-bold text-slate-900">正在验证联邦身份...</h3>
            <p className="text-xs text-slate-500">连接后端鉴权服务节点</p>
          </motion.div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {mode === 'register' && (
              <div>
                <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                  用户昵称
                </label>
                <div className="relative">
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    className="w-full text-xs font-semibold pl-10 pr-4 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 placeholder-slate-400"
                    placeholder="如：杭州主数据官"
                    type="text"
                  />
                </div>
              </div>
            )}

            <div>
              <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                {mode === 'login' ? '用户名' : '电子邮箱'}
              </label>
              <div className="relative">
                {mode === 'login' ? (
                  <User className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                ) : (
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                )}
                <input
                  value={mode === 'login' ? username : email}
                  onChange={(e) => mode === 'login' ? setUsername(e.target.value) : setEmail(e.target.value)}
                  className="w-full text-xs font-semibold pl-10 pr-4 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 placeholder-slate-400"
                  placeholder={mode === 'login' ? 'username' : 'name@example.com'}
                  type="text"
                />
              </div>
            </div>

            <div>
              <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                登录密码
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                <input
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full text-xs font-semibold pl-10 pr-4 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 placeholder-slate-400"
                  placeholder="••••••••"
                  type="password"
                />
              </div>
            </div>

            {mode === 'register' && (
              <div className="grid grid-cols-2 gap-4 pt-1">
                <div>
                  <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                    安全角色
                  </label>
                  <div className="relative">
                    <Shield className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <select
                      value={role}
                      onChange={(e) => setRole(e.target.value as 'user' | 'admin')}
                      className="w-full text-xs font-semibold pl-9 pr-3 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 appearance-none"
                    >
                      <option value="user">普通用户</option>
                      <option value="admin">系统管理员</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                    所属数据分组
                  </label>
                  <div className="relative">
                    <Briefcase className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" />
                    <select
                      value={group}
                      onChange={(e) => setGroup(e.target.value)}
                      className="w-full text-xs font-semibold pl-9 pr-3 py-2.5 bg-white/50 border border-slate-200 focus:border-black focus:outline-none focus:bg-white rounded-xl transition-all text-slate-800 appearance-none"
                    >
                      <option value="财务分析组">财务分析组</option>
                      <option value="温州业务部">温州业务部</option>
                      <option value="宁波海关组">宁波海关组</option>
                      <option value="系统运维处">系统运维处</option>
                    </select>
                  </div>
                </div>
              </div>
            )}

            <button
              type="submit"
              className="w-full mt-6 bg-indigo-500 hover:bg-indigo-600 text-white py-2.5 px-4 rounded-xl text-xs font-bold shadow-md hover:shadow-lg hover:scale-[1.01] transition-all cursor-pointer flex items-center justify-center gap-1.5"
            >
              <span>{mode === 'login' ? '安全登录' : '创建新会话'}</span>
              <ArrowRight className="h-4 w-4" />
            </button>
          </form>
        )}

        {/* 测试快捷通道 — 开发环境下自动填充凭证 */}
        <div className="mt-6 pt-4 border-t border-slate-200/50 text-center space-y-2.5">
          <p className="text-[10px] text-slate-400 font-bold uppercase tracking-wider">
            测试快捷通道 (一键填充角色)
          </p>
          <div className="flex gap-2.5 justify-center">
            <button
              type="button"
              onClick={() => {
                setMode('login')
                handleFastFill('admin')
              }}
              className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full text-[10px] font-bold transition-colors border border-slate-200 shadow-xs"
            >
              👑 管理员模板
            </button>
            <button
              type="button"
              onClick={() => {
                setMode('login')
                handleFastFill('user')
              }}
              className="px-3 py-1 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-full text-[10px] font-bold transition-colors border border-slate-200 shadow-xs"
            >
              👤 普通用户模板
            </button>
          </div>
        </div>

        <div className="mt-5 text-center">
          <button
            type="button"
            onClick={() => setMode(mode === 'login' ? 'register' : 'login')}
            className="text-xs text-slate-600 hover:text-black font-semibold underline underline-offset-4"
          >
            {mode === 'login' ? '首次接入联邦？创建新节点' : '已有账户？点此进行登录'}
          </button>
        </div>
      </motion.div>
    </div>
  )
}
