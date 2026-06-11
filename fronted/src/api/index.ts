/**
 * Micro-GenBI API Service Layer
 * 对接后端 /api/v1 REST 接口（使用原生 fetch）
 */

const BASE_URL = '/api/v1'

function getToken(): string {
  return localStorage.getItem('mgbi_token') || ''
}

function removeToken(): void {
  localStorage.removeItem('mgbi_token')
}

async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken()
  const defaultHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
  }
  if (token) {
    defaultHeaders['Authorization'] = `Bearer ${token}`
  }
  const mergedHeaders: Record<string, string> = {
    ...defaultHeaders,
    ...(options.headers as Record<string, string> | undefined),
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers: mergedHeaders,
  })
  if (!res.ok) {
    let msg = `请求失败 (${res.status})`
    try {
      const body = await res.json()
      msg = body.detail || body.message || msg
    } catch { /* ignore */ }
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

// ── Types ─────────────────────────────────────────────────────
export interface AuthUser {
  id: string
  username: string
  email: string
  role: 'admin' | 'user' | 'readonly'
  group: string
  subscriptionPlan: 'free' | 'pro' | 'enterprise'
  createdAt: string
}

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: AuthUser
}

export interface ColumnInfo {
  name: string
  type?: string
  data_type?: string
  description?: string
  nullable?: boolean
  primary_key?: boolean
  isPrimaryKey?: boolean
  primaryKey?: boolean
  display_name?: string
  foreign_key?: string
}

export interface QueryResult {
  sql: string
  data: Record<string, unknown>[]
  columns: ColumnInfo[]
  row_count?: number
  rowCount?: number
  execution_time_ms?: number
  executionTimeMs?: number
  steps_timing?: Record<string, number>
  steps?: Record<string, number>
  chart?: Record<string, unknown>
  summary?: string
  session_id?: string
  intent?: string
  confidence?: number
  status?: 'success' | 'failed' | 'blocked'
  error_message?: string
  errorMessage?: string
}

export interface QueryHistoryItem {
  id: string
  naturalQuery: string
  sql: string
  intent: string
  status: string
  executionTimeMs: number
  createdAt: string
  starred?: boolean
  execution_time_ms?: number
  row_count?: number
}

export interface SchemaColumn {
  name: string
  type: string
  description?: string
  nullable?: boolean
  primary_key?: boolean
  isPrimaryKey?: boolean
  primaryKey?: boolean
}

export interface SchemaTable {
  name: string
  display_name?: string
  description?: string
  columns: SchemaColumn[]
}

export interface DatabaseSource {
  id: string
  name: string
  display_name?: string
  type: string
  status: 'online' | 'offline' | 'active' | 'syncing'
  host?: string
  tableCount: number
  tenantName?: string
  tables: SchemaTable[]
}

export interface ManagedUser {
  id: string
  username: string
  email: string
  role: 'admin' | 'user' | 'readonly'
  group: string
  subscriptionPlan: 'free' | 'pro' | 'enterprise'
  status: 'active' | 'suspended'
  llmConfigured: boolean
  totalCalls: number
  lastCallTime: string
}

export interface AuditLogEntry {
  id: string
  timestamp: string
  user: string
  email: string
  eventType: string
  result: 'success' | 'failed' | 'blocked' | 'warning'
  details: string
  context?: Record<string, unknown>
}

export interface ApiKey {
  id: string
  name: string
  key_hint: string
  scope: 'read' | 'write' | 'admin'
  expires_in_days: number
  created_at: string
  last_used_at?: string
}

export interface LLMCostStats {
  totalTokens: string
  promptTokens: string
  completionTokens: string
  estimatedCost: string
  avgPerQuery: string
  callsCount: number
}

export interface CostByUser {
  user: string
  tokens: string
  calls: number
  cost: string
  percentage: string
}

export interface SlowQuery {
  id: string
  query: string
  user: string
  executionTimeMs: number
  status: string
  timestamp: string
}

export interface LLMMetric {
  model: string
  successRate: number
  avgLatencyMs: number
  totalCalls: number
}

export interface SecurityAlert {
  id: string
  severity: 'P0' | 'P1' | 'P2'
  type: string
  user: string
  ip: string
  description: string
  timestamp: string
  acknowledged: boolean
}

export interface SchemaRegistryItem {
  virtualSchema: string
  sourceNode: string
  sourceEntity: string
  type: string
}

function buildQuery(params?: Record<string, string | number | boolean | undefined>): string {
  if (!params) return ''
  const entries = Object.entries(params).filter(([, v]) => v !== undefined)
  if (entries.length === 0) return ''
  return '?' + new URLSearchParams(entries as [string, string][]).toString()
}

// ── Auth API ───────────────────────────────────────────────────
export const authApi = {
  login: (data: { username: string; password: string }): Promise<AuthResponse> =>
    apiFetch<AuthResponse>('/auth/login', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  register: (data: { username: string; password: string; email: string; role?: string; group?: string }): Promise<AuthResponse> =>
    apiFetch<AuthResponse>('/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  me: (): Promise<AuthUser> =>
    apiFetch<AuthUser>('/auth/me'),
}

// ── Query API ──────────────────────────────────────────────────
export interface TaskInfo {
  task_id: string
  status: string
}

export const queryApi = {
  submit: (text: string, opts?: { session_id?: string; generate_chart?: boolean; chart_type?: string }): Promise<QueryResult> =>
    apiFetch<QueryResult>('/query', {
      method: 'POST',
      body: JSON.stringify({ query: text, ...opts }),
    }),

  asyncSubmit: (text: string, opts?: { session_id?: string }): Promise<TaskInfo> =>
    apiFetch<TaskInfo>('/query/async', {
      method: 'POST',
      body: JSON.stringify({ query: text, ...opts }),
    }),

  getSchema: (connectionId?: string): Promise<{ databases: DatabaseSource[] }> =>
    apiFetch<{ databases: DatabaseSource[] }>(
      '/schema' + buildQuery(connectionId ? { connectionId } : undefined)
    ),

  getHistory: (opts?: { limit?: number; offset?: number }): Promise<{ items: QueryHistoryItem[]; total: number }> =>
    apiFetch<{ items: QueryHistoryItem[]; total: number }>('/history' + buildQuery(opts as Record<string, string | number | undefined>)),

  getRegistry: (): Promise<SchemaRegistryItem[]> =>
    apiFetch<SchemaRegistryItem[]>('/registry'),

  toggleFavorite: (recordId: number, starred: boolean): Promise<{ id: number; starred: boolean }> =>
    apiFetch<{ id: number; starred: boolean }>(`/history/${recordId}/favorite`, {
      method: 'POST',
      body: JSON.stringify({ starred }),
    }),

  deleteHistory: (recordId: number): Promise<void> =>
    apiFetch<void>(`/history/${recordId}`, { method: 'DELETE' }),

  searchSchema: (query: string): Promise<{ query: string; results: SchemaSearchResult[]; total: number }> => {
    return apiFetch<{ query: string; results: SchemaSearchResult[]; total: number }>('/schema/search', {
      method: 'POST',
      body: JSON.stringify({ query }),
    });
  },

  previewSQL: (query: string, connectionId?: string): Promise<{ sql: string }> =>
    apiFetch<{ sql: string }>('/query/preview-sql', {
      method: 'POST',
      body: JSON.stringify({ query, connection_id: connectionId }),
    }),

  multiSubmit: (text: string, opts?: { connection_id?: string; session_id?: string }): Promise<QueryResult> =>
    apiFetch<QueryResult>('/query/multi', {
      method: 'POST',
      body: JSON.stringify({ query: text, ...opts }),
    }),
}

// ── SQL Version API ────────────────────────────────────────────
export interface SQLVersion {
  id: number
  question: string
  sql: string
  created_at: string
  parent_version_id: number | null
  change_summary: string | null
  is_current?: boolean
}

export interface SQLVersionDiff {
  added_tables: string[]
  removed_tables: string[]
  modified_columns: string[]
  modified_where: boolean
  summary: string
}

export const versionApi = {
  list: (question: string, limit = 20): Promise<{ items: SQLVersion[]; total: number }> =>
    apiFetch<{ items: SQLVersion[]; total: number }>(
      `/history/versions?question=${encodeURIComponent(question)}&limit=${limit}`
    ),

  compare: (versionId1: number, versionId2: number): Promise<SQLVersionDiff> =>
    apiFetch<SQLVersionDiff>(
      `/history/versions/compare?version_id1=${versionId1}&version_id2=${versionId2}`
    ),

  rollback: (versionId: number): Promise<{ sql: string; message: string }> =>
    apiFetch<{ sql: string; message: string }>(`/history/versions/${versionId}/rollback`, {
      method: 'POST',
    }),
}

// ── Query Suggestions API ─────────────────────────────────────
export interface QuerySuggestion {
  text: string
  type: 'template' | 'history' | 'field' | 'time' | 'expansion'
  confidence: number
  metadata?: Record<string, unknown>
}

export const suggestionApi = {
  get: (input: string): Promise<{ suggestions: QuerySuggestion[] }> =>
    apiFetch<{ suggestions: QuerySuggestion[] }>(
      `/query/suggestions?q=${encodeURIComponent(input)}`
    ),
}

// ── Operation Trace API ────────────────────────────────────────
export interface TraceStep {
  id: string
  type: string
  input_summary: string
  output_summary: string
  duration_ms: number
  status: 'running' | 'success' | 'failed' | 'cancelled'
  metadata?: Record<string, unknown>
}

export interface OperationTraceResult {
  id: string
  operation_id: string
  operation_type: string
  steps: TraceStep[]
  total_duration_ms: number
  status: string
}

export const traceApi = {
  get: (taskId: string): Promise<OperationTraceResult> =>
    apiFetch<OperationTraceResult>(`/trace/${encodeURIComponent(taskId)}`),
}

// ── Subscription API ─────────────────────────────────────────────
export interface Subscription {
  id: string
  name: string
  query_description: string
  schedule: string
  schedule_label: string
  status: 'active' | 'paused'
  last_run_at: string | null
  next_run_at: string | null
}

export const subscriptionApi = {
  list: (): Promise<{ items: Subscription[] }> =>
    apiFetch<{ items: Subscription[] }>('/subscriptions'),

  create: (data: { name: string; query_description: string; schedule: string }): Promise<Subscription> =>
    apiFetch<Subscription>('/subscriptions', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: (id: string, data: { status?: string; schedule?: string }): Promise<Subscription> =>
    apiFetch<Subscription>(`/subscriptions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  remove: (id: string): Promise<void> =>
    apiFetch<void>(`/subscriptions/${id}`, { method: 'DELETE' }),
}

// ── Chart API ──────────────────────────────────────────────────
export interface ChartRecommendation {
  recommended: string
  confidence: number
  reason: string
  alternatives: string[]
  suggested_configs: Record<string, unknown>
  options?: Record<string, unknown>
}

export const chartApi = {
  recommend: (columns: string[], data: Record<string, unknown>[], intent?: string): Promise<ChartRecommendation> =>
    apiFetch<ChartRecommendation>('/chart/recommend', {
      method: 'POST',
      body: JSON.stringify({ columns, data, intent }),
    }),
}

export const schemaApi = {
  refresh: (): Promise<{ message: string }> =>
    apiFetch<{ message: string }>('/schema/refresh', { method: 'POST' }),

  testConnection: (connectionId: string): Promise<{ success: boolean; message?: string; latency_ms?: number }> =>
    apiFetch<{ success: boolean; message?: string; latency_ms?: number }>('/schema/test-connection', {
      method: 'POST',
      body: JSON.stringify({ id: connectionId }),
    }),
}

export interface AnomalyRecord {
  row_index: number
  column: string
  value: number
  expected_range: [number, number]
  score: number
  severity: 'critical' | 'high' | 'medium' | 'low'
}

export interface AnomalyResult {
  anomalies: AnomalyRecord[]
  summary: Record<string, unknown>
  severity_counts: Record<string, number>
}

export const anomalyApi = {
  detect: (
    data: Record<string, unknown>[],
    columns: string[],
    method = 'zscore',
    threshold = 3.0
  ): Promise<AnomalyResult> =>
    apiFetch<AnomalyResult>('/query/anomaly-detect', {
      method: 'POST',
      body: JSON.stringify({ data, columns, method, threshold }),
    }),
}

export interface SchemaSearchResult {
  table: string
  database?: string
  description: string
  column_count?: number
  columnCount?: number
  matching_columns?: string[]
  matchingColumns?: string[]
  score?: number
}

// ── Admin API ─────────────────────────────────────────────────
export const adminApi = {
  getUsers: (opts?: { group?: string; role?: string; status?: string }): Promise<{ items: ManagedUser[]; total: number }> =>
    apiFetch<{ items: ManagedUser[]; total: number }>('/admin/users' + buildQuery(opts as Record<string, string | undefined>)),

  createUser: (data: { username: string; email: string; password: string; role?: string }): Promise<ManagedUser> =>
    apiFetch<ManagedUser>('/admin/users?' + new URLSearchParams({ tenant_id: 'default' }).toString(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }).then(r => ({
      id: r.id,
      username: r.username,
      email: r.email,
      role: r.role as 'admin' | 'user' | 'readonly',
      group: r.group || 'default',
      subscriptionPlan: 'free' as const,
      status: r.status as 'active' | 'suspended' || 'active',
      llmConfigured: false,
      totalCalls: 0,
      lastCallTime: '',
    })),

  updateUser: (userId: string, data: Partial<ManagedUser>): Promise<ManagedUser> =>
    apiFetch<ManagedUser>(`/admin/users/${userId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),

  resetPassword: (userId: string): Promise<{ message: string; password: string }> =>
    apiFetch<{ message: string; password: string }>(`/admin/users/${userId}/reset-password`, { method: 'POST' }),

  deleteUser: (userId: string): Promise<void> =>
    apiFetch<void>(`/admin/users/${userId}`, { method: 'DELETE' }),

  getAuditLogs: (opts?: { eventType?: string; user?: string; limit?: number }): Promise<{ items: AuditLogEntry[]; total: number }> =>
    apiFetch<{ items: AuditLogEntry[]; total: number }>('/admin/audit/logs' + buildQuery(opts as Record<string, string | number | undefined>)),

  getAuditStats: (): Promise<{
    totalEvents: number
    failedLogins: number
    blockedQueries: number
    sqlInjections: number
    last24h: { logins: number; queries: number; failures: number }
  }> => apiFetch('/admin/audit/stats'),

  getCost: (period?: string): Promise<LLMCostStats> =>
    apiFetch<LLMCostStats>('/admin/cost' + buildQuery(period ? { period } : undefined)),

  getCostByUser: (): Promise<CostByUser[]> =>
    apiFetch<CostByUser[]>('/admin/cost/by-user'),

  getCostByModel: (): Promise<{ model: string; calls: string; tokens: string; cost: string }[]> =>
    apiFetch<{ model: string; calls: string; tokens: string; cost: string }[]>('/admin/cost/by-model'),

  getSlowQueries: (limit = 20): Promise<{ items: SlowQuery[]; total: number }> =>
    apiFetch<{ items: SlowQuery[]; total: number }>(`/admin/performance/slow-queries?limit=${limit}`),

  getLLMMetrics: (): Promise<LLMMetric[]> =>
    apiFetch<LLMMetric[]>('/admin/performance/llm-metrics'),

  getQueryTrend: (): Promise<{ label: string; value: number }[]> =>
    apiFetch<{ label: string; value: number }[]>('/admin/performance/query-trend'),

  getSecurityAlerts: (): Promise<{ items: SecurityAlert[]; total: number }> =>
    apiFetch<{ items: SecurityAlert[]; total: number }>('/admin/security/alerts'),

  ackAlert: (alertId: string): Promise<void> =>
    apiFetch<void>(`/admin/security/alerts/${alertId}/acknowledge`, { method: 'POST' }),

  getFailedLogins: (): Promise<{ user: string; ip: string; attempts: number; lastAttempt: string }[]> =>
    apiFetch<{ user: string; ip: string; attempts: number; lastAttempt: string }[]>('/admin/security/failed-logins'),

  getConnections: (): Promise<{ items: DatabaseSource[]; total: number }> =>
    apiFetch<{ items: DatabaseSource[]; total: number }>('/admin/connections'),

  createConnection: (data: Partial<DatabaseSource>): Promise<DatabaseSource> =>
    apiFetch<DatabaseSource>('/admin/connections', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteConnection: (connId: string): Promise<void> =>
    apiFetch<void>(`/admin/connections/${connId}`, { method: 'DELETE' }),

  getApiKeys: (): Promise<{ items: ApiKey[]; total: number }> =>
    apiFetch<{ items: ApiKey[]; total: number }>('/admin/api-keys'),

  createApiKey: (data: { name: string; scope: string; expires_in_days: number }): Promise<ApiKey & { key: string }> =>
    apiFetch<ApiKey & { key: string }>('/admin/api-keys', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  revokeApiKey: (id: string): Promise<void> =>
    apiFetch<void>(`/admin/api-keys/${id}`, { method: 'DELETE' }),

  saveSystemConfig: (config: Record<string, unknown>): Promise<{ message: string }> =>
    apiFetch<{ message: string }>('/admin/system-config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),
}

export { removeToken }
