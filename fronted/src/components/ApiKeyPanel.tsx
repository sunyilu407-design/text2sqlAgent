/**
 * ApiKeyPanel — API Key 管理面板
 * 对接 /api/v1/admin/api-keys
 */
import { useState, useEffect, useCallback, type ReactNode, type FormEvent } from 'react'
import {
  KeyRound,
  Plus,
  Copy,
  Check,
  Trash2,
  Loader2,
  AlertCircle,
  Shield,
  Eye,
  EyeOff,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'

// ── Types ─────────────────────────────────────────────────────────
interface ApiKeyItem {
  id: string
  name: string
  key_hint: string
  scope: 'read' | 'write' | 'admin'
  expires_in_days: number
  created_at: string
  last_used_at: string | null
}

interface CreateApiKeyResponse {
  id: string
  key: string // only shown once
  name: string
  scope: 'read' | 'write' | 'admin'
  expires_in_days: number
  created_at: string
}

// ── Helpers ──────────────────────────────────────────────────────
function maskKey(hint: string): string {
  // hint format: sk_****_xxxxx or similar
  return hint
}

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString('zh-CN', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    })
  } catch {
    return iso
  }
}

function daysUntilExpiry(createdAt: string, expiresInDays: number): string {
  const expiry = new Date(createdAt).getTime() + expiresInDays * 86400 * 1000
  const remaining = Math.ceil((expiry - Date.now()) / 86400000)
  if (remaining < 0) return '已过期'
  if (remaining === 0) return '今天到期'
  return `${remaining} 天后到期`
}

const SCOPE_COLORS: Record<string, string> = {
  read: 'bg-slate-100 text-slate-600 border-slate-200',
  write: 'bg-amber-50 text-amber-600 border-amber-200',
  admin: 'bg-red-50 text-red-500 border-red-200',
}

const SCOPE_LABELS: Record<string, string> = {
  read: '只读',
  write: '读写',
  admin: '管理',
}

// ── API helpers ───────────────────────────────────────────────────
async function fetchApiKeys(token: string): Promise<ApiKeyItem[]> {
  const res = await fetch('/api/v1/admin/api-keys', {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '获取密钥列表失败' }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  const data = await res.json()
  return (data.items ?? []) as ApiKeyItem[]
}

async function createApiKey(
  token: string,
  payload: { name: string; scope: 'read' | 'write' | 'admin'; expires_in_days: number }
): Promise<CreateApiKeyResponse> {
  const res = await fetch('/api/v1/admin/api-keys', {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: '创建密钥失败' }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<CreateApiKeyResponse>
}

async function revokeApiKey(token: string, keyId: string): Promise<void> {
  const res = await fetch(`/api/v1/admin/api-keys/${encodeURIComponent(keyId)}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok && res.status !== 204) {
    const err = await res.json().catch(() => ({ detail: '撤销密钥失败' }))
    throw new Error(err.detail ?? `HTTP ${res.status}`)
  }
}

// ── Props ─────────────────────────────────────────────────────────
interface ApiKeyPanelProps {
  onError?: (msg: string) => void
}

// ── Component ─────────────────────────────────────────────────────
export default function ApiKeyPanel({ onError }: ApiKeyPanelProps) {
  const [keys, setKeys] = useState<ApiKeyItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Create modal state
  const [showCreate, setShowCreate] = useState(false)
  const [createName, setCreateName] = useState('')
  const [createScope, setCreateScope] = useState<'read' | 'write' | 'admin'>('read')
  const [createExpiry, setCreateExpiry] = useState(30)
  const [creating, setCreating] = useState(false)
  const [newKey, setNewKey] = useState<CreateApiKeyResponse | null>(null)
  const [createErr, setCreateErr] = useState<string | null>(null)

  // Revoke confirmation state
  const [revokeTarget, setRevokeTarget] = useState<ApiKeyItem | null>(null)
  const [revoking, setRevoking] = useState(false)

  // Copy state
  const [copiedId, setCopiedId] = useState<string | null>(null)

  const token = localStorage.getItem('mgbi_token') ?? ''

  const loadKeys = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const items = await fetchApiKeys(token)
      setKeys(items)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载密钥列表失败'
      setError(msg)
      onError?.(msg)
    } finally {
      setLoading(false)
    }
  }, [token, onError])

  useEffect(() => {
    void loadKeys()
  }, [loadKeys])

  const handleCopy = useCallback(async (text: string, keyId: string) => {
    try {
      await navigator.clipboard.writeText(text)
      setCopiedId(keyId)
      setTimeout(() => setCopiedId(null), 2000)
    } catch {
      // fallback
    }
  }, [])

  const handleCreate = useCallback(async (e: FormEvent) => {
    e.preventDefault()
    if (!createName.trim()) return
    setCreating(true)
    setCreateErr(null)
    try {
      const created = await createApiKey(token, {
        name: createName.trim(),
        scope: createScope,
        expires_in_days: createExpiry,
      })
      setNewKey(created)
      await loadKeys()
    } catch (err) {
      setCreateErr(err instanceof Error ? err.message : '创建失败')
    } finally {
      setCreating(false)
    }
  }, [createName, createScope, createExpiry, token, loadKeys])

  const handleRevoke = useCallback(async () => {
    if (!revokeTarget) return
    setRevoking(true)
    try {
      await revokeApiKey(token, revokeTarget.id)
      setKeys(prev => prev.filter(k => k.id !== revokeTarget.id))
      setRevokeTarget(null)
    } catch (err) {
      const msg = err instanceof Error ? err.message : '撤销失败'
      setError(msg)
      onError?.(msg)
    } finally {
      setRevoking(false)
    }
  }, [revokeTarget, token, onError])

  return (
    <div className="panel rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="px-5 py-4 border-b border-white/30 bg-white/30 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <KeyRound className="h-5 w-5 text-slate-700" />
          <div>
            <h3 className="text-sm font-bold text-slate-800">API 密钥管理</h3>
            <p className="text-[10px] text-slate-400">管理用于后端集成的访问密钥</p>
          </div>
        </div>
        <button
          onClick={() => {
            setShowCreate(true)
            setNewKey(null)
            setCreateName('')
            setCreateScope('read')
            setCreateExpiry(30)
            setCreateErr(null)
          }}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg text-xs font-semibold transition-colors shadow-sm"
        >
          <Plus className="h-3.5 w-3.5" />
          创建新密钥
        </button>
      </div>

      {/* Error banner */}
      <AnimatePresence>
        {error && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            className="mx-5 mt-3 p-3 bg-red-50 border border-red-200 rounded-xl flex items-center gap-2 text-xs text-red-600 font-semibold"
          >
            <AlertCircle className="h-4 w-4 shrink-0" />
            {error}
            <button
              onClick={() => setError(null)}
              className="ml-auto text-red-400 hover:text-red-600 transition-colors"
            >
              ✕
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="h-6 w-6 animate-spin text-slate-400" />
        </div>
      )}

      {/* Empty state */}
      {!loading && keys.length === 0 && !error && (
        <div className="flex flex-col items-center justify-center py-12 text-slate-400">
          <KeyRound className="h-8 w-8 mb-2 text-slate-300" />
          <p className="text-xs font-semibold">暂无 API 密钥</p>
          <p className="text-[11px] mt-1">点击右上角"创建新密钥"生成</p>
        </div>
      )}

      {/* Key list */}
      {!loading && keys.length > 0 && (
        <div className="divide-y divide-white/20">
          {keys.map(key => (
            <div
              key={key.id}
              className="px-5 py-4 flex items-center gap-4 hover:bg-white/10 transition-colors"
            >
              {/* Icon */}
              <div className="w-9 h-9 rounded-xl bg-white/50 flex items-center justify-center shrink-0">
                <Shield className="h-4.5 w-4.5 text-slate-500" />
              </div>

              {/* Info */}
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-800 truncate">{key.name}</span>
                  <span
                    className={`text-[10px] font-bold px-1.5 py-0.5 rounded border shrink-0 ${SCOPE_COLORS[key.scope] ?? SCOPE_COLORS.read}`}
                  >
                    {SCOPE_LABELS[key.scope] ?? key.scope}
                  </span>
                </div>
                <div className="flex items-center gap-3 mt-1">
                  <span className="text-[11px] font-mono text-slate-400">
                    {maskKey(key.key_hint)}
                  </span>
                  <span className="text-[10px] text-slate-300">·</span>
                  <span className="text-[11px] text-slate-400">
                    有效期: {daysUntilExpiry(key.created_at, key.expires_in_days)}
                  </span>
                  <span className="text-[10px] text-slate-300">·</span>
                  <span className="text-[11px] text-slate-400">
                    创建于 {formatDate(key.created_at)}
                  </span>
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => handleCopy(key.key_hint, key.id)}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-white/40 text-[11px] font-semibold text-slate-500 hover:bg-white/30 transition-colors"
                  title="复制密钥提示"
                >
                  {copiedId === key.id ? (
                    <Check className="h-3.5 w-3.5 text-emerald-500" />
                  ) : (
                    <Copy className="h-3.5 w-3.5" />
                  )}
                  <span>{copiedId === key.id ? '已复制' : '复制'}</span>
                </button>
                <button
                  onClick={() => setRevokeTarget(key)}
                  className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-red-100 text-[11px] font-semibold text-red-500 hover:bg-red-50 transition-colors"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                  <span>撤销</span>
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create Modal */}
      <AnimatePresence>
        {showCreate && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm"
            onClick={(e) => {
              if (e.target === e.currentTarget) setShowCreate(false)
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-md panel-elevated rounded-2xl overflow-hidden"
            >
              {/* Modal header */}
              <div className="px-6 py-4 border-b border-white/30 bg-white/50 flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <KeyRound className="h-4.5 w-4.5 text-slate-700" />
                  <h3 className="text-sm font-bold text-slate-800">创建 API 密钥</h3>
                </div>
                <button
                  onClick={() => setShowCreate(false)}
                  className="text-slate-400 hover:text-slate-600 transition-colors text-lg leading-none"
                >
                  ✕
                </button>
              </div>

              {/* New key result */}
              <AnimatePresence>
                {newKey && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="mx-6 mt-4 p-4 bg-emerald-50 border border-emerald-200 rounded-xl"
                  >
                    <div className="flex items-center gap-2 mb-3">
                      <Check className="h-4 w-4 text-emerald-600" />
                      <p className="text-xs font-bold text-emerald-700">密钥已生成，请立即复制保存！此密钥仅显示一次。</p>
                    </div>
                    <div className="flex items-center gap-2 bg-white/80 rounded-lg p-3 border border-emerald-200">
                      <code className="flex-1 text-xs font-mono text-slate-700 break-all select-all">
                        {newKey.key}
                      </code>
                      <button
                        onClick={() => {
                          void handleCopy(newKey.key, newKey.id)
                        }}
                        className="shrink-0 p-1.5 rounded-lg hover:bg-emerald-100 transition-colors text-emerald-600"
                        title="复制密钥"
                      >
                        {copiedId === newKey.id ? (
                          <Check className="h-4 w-4" />
                        ) : (
                          <Copy className="h-4 w-4" />
                        )}
                      </button>
                    </div>
                    <button
                      onClick={() => {
                        setShowCreate(false)
                        setNewKey(null)
                      }}
                      className="w-full mt-3 py-2 bg-emerald-600 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 transition-colors"
                    >
                      完成
                    </button>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Create form */}
              {!newKey && (
                <form onSubmit={handleCreate} className="p-6 space-y-4">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                      密钥名称
                    </label>
                    <input
                      value={createName}
                      onChange={e => setCreateName(e.target.value)}
                      className="w-full text-xs font-semibold px-3 py-2.5 bg-white/60 border border-slate-200 focus:border-black focus:outline-none rounded-xl text-slate-800 placeholder-slate-400"
                      placeholder="例如: 生产环境集成密钥"
                      type="text"
                      required
                    />
                  </div>

                  <div>
                    <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                      权限范围
                    </label>
                    <div className="grid grid-cols-3 gap-2">
                      {(['read', 'write', 'admin'] as const).map(scope => (
                        <button
                          key={scope}
                          type="button"
                          onClick={() => setCreateScope(scope)}
                          className={`py-2 rounded-xl text-xs font-bold border transition-all ${
                            createScope === scope
                              ? 'border-indigo-500 bg-indigo-500 text-white shadow-sm'
                              : `${SCOPE_COLORS[scope]} border`
                          }`}
                        >
                          {SCOPE_LABELS[scope]} {scope === 'read' ? '(只读)' : scope === 'write' ? '(读写)' : '(管理)'}
                        </button>
                      ))}
                    </div>
                    <p className="text-[10px] text-slate-400 mt-1.5">
                      {createScope === 'read' && '仅允许读取数据，无法执行查询'}
                      {createScope === 'write' && '允许读取和写入数据，可执行查询'}
                      {createScope === 'admin' && '完整管理权限，包括密钥管理和用户管理'}
                    </p>
                  </div>

                  <div>
                    <label className="block text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1.5">
                      有效期 (天)
                    </label>
                    <input
                      type="number"
                      value={createExpiry}
                      onChange={e => setCreateExpiry(Number(e.target.value))}
                      className="w-full text-xs font-semibold px-3 py-2.5 bg-white/60 border border-slate-200 focus:border-black focus:outline-none rounded-xl text-slate-800"
                      min={1}
                      max={365}
                      required
                    />
                    <p className="text-[10px] text-slate-400 mt-1.5">
                      密钥将在 {createExpiry} 天后自动过期，建议定期轮换
                    </p>
                  </div>

                  {createErr && (
                    <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600 font-semibold flex items-center gap-2">
                      <AlertCircle className="h-4 w-4 shrink-0" />
                      {createErr}
                    </div>
                  )}

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowCreate(false)}
                      className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 border border-white/60 hover:bg-white/40 transition-colors"
                    >
                      取消
                    </button>
                    <button
                      type="submit"
                      disabled={creating || !createName.trim()}
                      className="flex items-center gap-2 px-5 py-2 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl text-xs font-bold transition-colors disabled:opacity-50 cursor-pointer"
                    >
                      {creating && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                      {creating ? '创建中...' : '创建密钥'}
                    </button>
                  </div>
                </form>
              )}
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Revoke confirmation modal */}
      <AnimatePresence>
        {revokeTarget && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/30 backdrop-blur-sm"
            onClick={e => {
              if (e.target === e.currentTarget) setRevokeTarget(null)
            }}
          >
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: 8 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: 8 }}
              transition={{ duration: 0.2 }}
              className="w-full max-w-sm panel-elevated rounded-2xl overflow-hidden"
            >
              <div className="p-6 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-red-50 flex items-center justify-center shrink-0">
                    <AlertCircle className="h-5 w-5 text-red-500" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-slate-800">确认撤销密钥</h3>
                    <p className="text-[11px] text-slate-500 mt-0.5">
                      撤销后，使用此密钥的所有请求将立即失效。
                    </p>
                  </div>
                </div>
                <div className="p-3 bg-slate-50 rounded-xl">
                  <p className="text-xs font-bold text-slate-700">{revokeTarget.name}</p>
                  <p className="text-[11px] text-slate-400 font-mono mt-0.5">{maskKey(revokeTarget.key_hint)}</p>
                </div>
                <div className="flex justify-end gap-2">
                  <button
                    onClick={() => setRevokeTarget(null)}
                    className="px-4 py-2 rounded-xl text-xs font-semibold text-slate-600 border border-white/60 hover:bg-white/40 transition-colors"
                  >
                    取消
                  </button>
                  <button
                    onClick={() => {
                      void handleRevoke()
                    }}
                    disabled={revoking}
                    className="flex items-center gap-2 px-5 py-2 bg-red-500 text-white rounded-xl text-xs font-bold hover:bg-red-600 transition-colors disabled:opacity-50 cursor-pointer"
                  >
                    {revoking && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                    {revoking ? '撤销中...' : '确认撤销'}
                  </button>
                </div>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
