/**
 * React Query hooks for Micro-GenBI
 *
 * Provides:
 * - Query client with smart caching
 * - Typed hooks for all API endpoints
 * - Automatic retry and error handling
 */
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useMutation,
  useQueryClient,
} from '@tanstack/react-query'
import type {
  QueryResult,
  QueryHistoryItem,
  SchemaRegistryItem,
  DatabaseSource,
  SchemaSearchResult,
  TaskInfo,
  ChartRecommendation,
} from '../api'

// ── Query Client ───────────────────────────────────────────────────────────────

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30 * 1000,        // 30s 内认为新鲜
      gcTime: 5 * 60 * 1000,        // 5min 缓存
      retry: 2,
      refetchOnWindowFocus: false,
    },
    mutations: {
      retry: 1,
    },
  },
})

export { QueryClientProvider }

// ── Query Hooks ───────────────────────────────────────────────────────────────

export function useSchema() {
  return useQuery({
    queryKey: ['schema'],
    queryFn: () =>
      import('../api').then(m => m.queryApi.getSchema()),
    select: (data) => data.databases,
  })
}

export function useRegistry() {
  return useQuery({
    queryKey: ['registry'],
    queryFn: () => import('../api').then(m => m.queryApi.getRegistry()),
  })
}

export function useQueryHistory(opts?: { limit?: number; offset?: number; starredOnly?: boolean; search?: string }) {
  return useQuery({
    queryKey: ['history', opts],
    queryFn: () => import('../api').then(m => m.queryApi.getHistory(opts)),
    select: (data) => data.items,
  })
}

export function useSchemaSearch(query: string, enabled = true) {
  return useQuery({
    queryKey: ['schema-search', query],
    queryFn: () => import('../api').then(m => m.queryApi.searchSchema(query)),
    enabled: enabled && query.trim().length > 0,
    staleTime: 60 * 1000,
  })
}

export function useChartRecommend(columns: string[], data: Record<string, unknown>[], intent?: string) {
  return useQuery({
    queryKey: ['chart-recommend', columns, data, intent],
    queryFn: () => import('../api').then(m => m.chartApi.recommend(columns, data, intent)),
    enabled: columns.length > 0 && data.length > 0,
    staleTime: 5 * 60 * 1000,
  })
}

export function useQuerySuggestions(input: string) {
  return useQuery({
    queryKey: ['query-suggestions', input],
    queryFn: () => import('../api').then(m => m.suggestionApi.get(input)),
    enabled: input.trim().length >= 2,
    staleTime: 30 * 1000,
  })
}

// ── SQL Version Hooks ──────────────────────────────────────────────────────────

export function useSQLVersions(question: string, limit = 20) {
  return useQuery({
    queryKey: ['sql-versions', question, limit],
    queryFn: () => import('../api').then(m => m.versionApi.list(question, limit)),
    enabled: question.trim().length > 0,
    staleTime: 10 * 1000,
  })
}

export function useCompareVersions(versionId1: number, versionId2: number) {
  return useQuery({
    queryKey: ['sql-versions-compare', versionId1, versionId2],
    queryFn: () => import('../api').then(m => m.versionApi.compare(versionId1, versionId2)),
    enabled: versionId1 > 0 && versionId2 > 0 && versionId1 !== versionId2,
    staleTime: 30 * 1000,
  })
}

export function useRollbackVersion() {
  return useMutation({
    mutationFn: (versionId: number) =>
      import('../api').then(m => m.versionApi.rollback(versionId)),
  })
}

// ── Operation Trace Hooks ─────────────────────────────────────────────────────

export function useOperationTrace(taskId: string) {
  return useQuery({
    queryKey: ['operation-trace', taskId],
    queryFn: () => import('../api').then(m => m.traceApi.get(taskId)),
    enabled: taskId.trim().length > 0,
    staleTime: 0,
    refetchInterval: (query) => {
      const data = query.state.data
      if (data && data.status === 'running') return 1000
      return false
    },
  })
}

// ── Mutation Hooks ───────────────────────────────────────────────────────────

export function useSubmitQuery() {
  return useMutation({
    mutationFn: (params: { text: string; session_id?: string; generate_chart?: boolean }) =>
      import('../api').then(m => m.queryApi.submit(params.text, { session_id: params.session_id, generate_chart: params.generate_chart })),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history'] })
    },
  })
}

export function useToggleFavorite() {
  return useMutation({
    mutationFn: (params: { recordId: number; starred: boolean }) =>
      import('../api').then(m => m.queryApi.toggleFavorite(params.recordId, params.starred)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history'] })
    },
  })
}

export function useDeleteHistory() {
  return useMutation({
    mutationFn: (recordId: number) =>
      import('../api').then(m => m.queryApi.deleteHistory(recordId)),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['history'] })
    },
  })
}

// ── Prefetch helpers ──────────────────────────────────────────────────────────

export function usePrefetchSchema() {
  const client = useQueryClient()
  return () => {
    client.prefetchQuery({
      queryKey: ['schema'],
      queryFn: () => import('../api').then(m => m.queryApi.getSchema()),
    })
  }
}

export function usePrefetchHistory() {
  const client = useQueryClient()
  return (opts?: Parameters<typeof useQueryHistory>[0]) => {
    client.prefetchQuery({
      queryKey: ['history', opts],
      queryFn: () => import('../api').then(m => m.queryApi.getHistory(opts)),
    })
  }
}

// ── Anomaly Detection Hooks ────────────────────────────────────────────────────

export function useAnomalyDetection(
  data: Record<string, unknown>[],
  columns: string[],
  method: 'zscore' | 'iqr' = 'zscore',
  threshold = 3.0
) {
  return useQuery({
    queryKey: ['anomaly-detection', data, columns, method, threshold],
    queryFn: () => import('../api').then(m => m.anomalyApi.detect(data, columns, method, threshold)),
    enabled: data.length > 0 && columns.length > 0,
    staleTime: 0,
  })
}
