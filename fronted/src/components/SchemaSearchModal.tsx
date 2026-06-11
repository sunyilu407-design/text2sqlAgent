/**
 * SchemaSearchModal — Semantic schema search with natural language
 * Searches /api/v1/schema/search with fallback to client-side filtering
 */
import { useState, useEffect, useRef, useCallback, type ChangeEvent, type KeyboardEvent } from 'react';
import { Search, X, Loader2, Database, Columns, MessageSquare } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { queryApi, type SchemaSearchResult, type DatabaseSource } from '../api';

export interface SchemaSearchModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSelect: (table: string, columns: string[]) => void;
}

interface LocalSearchResult {
  table: string;
  description: string;
  columnCount: number;
  matchingColumns: string[];
}

function clientSideSearch(
  query: string,
  databases: DatabaseSource[]
): LocalSearchResult[] {
  const q = query.toLowerCase().trim();
  if (!q) return [];

  const results: LocalSearchResult[] = [];

  for (const db of databases) {
    for (const table of db.tables ?? []) {
      const tableName = table.name.toLowerCase();
      const displayName = (table.display_name ?? table.name).toLowerCase();
      const description = (table.description ?? '').toLowerCase();

      const matchingCols: string[] = [];
      for (const col of table.columns ?? []) {
        const colName = col.name.toLowerCase();
        const colDesc = (col.description ?? '').toLowerCase();
        if (
          colName.includes(q) ||
          colDesc.includes(q) ||
          q.split(/\s+/).every(token => colName.includes(token) || colDesc.includes(token))
        ) {
          matchingCols.push(col.name);
        }
      }

      const tableMatches =
        tableName.includes(q) ||
        displayName.includes(q) ||
        description.includes(q) ||
        q.split(/\s+/).every(token =>
          tableName.includes(token) || displayName.includes(token) || description.includes(token)
        );

      if (tableMatches || matchingCols.length > 0) {
        results.push({
          table: table.name,
          description: table.description ?? '',
          columnCount: table.columns?.length ?? 0,
          matchingColumns: matchingCols.length > 0 ? matchingCols : table.columns?.map(c => c.name) ?? [],
        });
      }
    }
  }

  return results;
}

export default function SchemaSearchModal({ isOpen, onClose, onSelect }: SchemaSearchModalProps) {
  const [searchText, setSearchText] = useState('');
  const [results, setResults] = useState<SchemaSearchResult[] | LocalSearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [databases, setDatabases] = useState<DatabaseSource[]>([]);

  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-focus input when modal opens
  useEffect(() => {
    if (isOpen) {
      setSearchText('');
      setResults([]);
      setError(false);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [isOpen]);

  // Load schema data once when modal opens for client-side fallback
  useEffect(() => {
    if (!isOpen) return;
    queryApi.getSchema()
      .then(({ databases: dbs }) => setDatabases(dbs))
      .catch(() => setDatabases([]));
  }, [isOpen]);

  const doSearch = useCallback(async (query: string) => {
    if (!query.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    setError(false);

    try {
      const serverResults = await queryApi.searchSchema(query);
      setResults(serverResults);
    } catch (err) {
      // Fallback to client-side search if endpoint 404s
      const is404 = err instanceof Error && (err.message.includes('404') || err.message.includes('Not Found'));
      if (is404) {
        const local = clientSideSearch(query, databases);
        setResults(local);
      } else {
        // Try local search on any error (network, etc.)
        const local = clientSideSearch(query, databases);
        setResults(local);
        if (local.length === 0) {
          setError(true);
        }
      }
    } finally {
      setLoading(false);
    }
  }, [databases]);

  const handleInputChange = useCallback((e: ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setSearchText(val);

    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    if (!val.trim()) {
      setResults([]);
      setLoading(false);
      return;
    }

    setLoading(true);
    debounceRef.current = setTimeout(() => {
      doSearch(val);
    }, 400);
  }, [doSearch]);

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      onClose();
    }
  }, [onClose]);

  const handleSelect = useCallback((table: string, columns: string[]) => {
    onSelect(table, columns);
    onClose();
  }, [onSelect, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/30 backdrop-blur-sm z-50"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: -20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: -20 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="fixed inset-x-4 top-[10vh] mx-auto max-w-2xl w-full z-50"
          >
            <div className="panel-elevated rounded-2xl overflow-hidden shadow-2xl border border-white/60">
              {/* Header */}
              <div className="flex items-center gap-3 px-5 py-4 border-b border-slate-200/60">
                <div className="w-8 h-8 rounded-lg bg-black/5 flex items-center justify-center shrink-0">
                  <Database className="h-4 w-4 text-slate-700" />
                </div>
                <input
                  ref={inputRef}
                  type="text"
                  value={searchText}
                  onChange={handleInputChange}
                  onKeyDown={handleKeyDown}
                  placeholder="搜索数据表和字段，如「用户订单」或「revenue」..."
                  className="flex-1 bg-transparent text-sm text-slate-900 placeholder-slate-400 outline-none"
                />
                {loading ? (
                  <Loader2 className="h-4 w-4 animate-spin text-slate-400 shrink-0" />
                ) : (
                  searchText && (
                    <button
                      onClick={() => { setSearchText(''); setResults([]); inputRef.current?.focus(); }}
                      className="p-1 hover:bg-slate-100 rounded transition-colors shrink-0"
                    >
                      <X className="h-4 w-4 text-slate-400" />
                    </button>
                  )
                )}
              </div>

              {/* Results */}
              <div className="max-h-96 overflow-y-auto">
                {loading && results.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                    <Loader2 className="h-6 w-6 animate-spin mb-3 text-slate-300" />
                    <p className="text-xs">搜索中...</p>
                  </div>
                ) : error ? (
                  <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                    <MessageSquare className="h-8 w-8 mb-3 text-slate-300" />
                    <p className="text-xs text-center px-8 leading-relaxed">
                      搜索遇到问题，尝试换一个关键词
                    </p>
                  </div>
                ) : results.length === 0 && searchText ? (
                  <div className="flex flex-col items-center justify-center py-16 text-slate-400">
                    <Search className="h-8 w-8 mb-3 text-slate-300" />
                    <p className="text-xs text-center px-8 leading-relaxed">
                      未找到相关表或字段
                    </p>
                  </div>
                ) : results.length === 0 ? (
                  <div className="flex flex-col items-center justify-center py-12 text-slate-400">
                    <Search className="h-8 w-8 mb-3 text-slate-300" />
                    <p className="text-xs text-center px-8">
                      输入关键词搜索数据表或字段
                    </p>
                  </div>
                ) : (
                  <div className="divide-y divide-slate-100/60">
                    {results.map((result) => (
                      <div
                        key={result.table}
                        onClick={() => handleSelect(result.table, result.matchingColumns)}
                        className="px-5 py-4 hover:bg-slate-50/80 cursor-pointer transition-colors group"
                      >
                        <div className="flex items-start gap-3">
                          <div className="w-7 h-7 rounded-md bg-black/5 flex items-center justify-center shrink-0 mt-0.5 group-hover:bg-black/10 transition-colors">
                            <Database className="h-3.5 w-3.5 text-slate-600" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className="text-xs font-bold text-slate-900 font-mono">
                                {result.table}
                              </span>
                              <span className="flex items-center gap-1 text-[10px] text-slate-400">
                                <Columns className="h-3 w-3" />
                                {result.columnCount} 列
                              </span>
                            </div>
                            {result.description && (
                              <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-1">
                                {result.description}
                              </p>
                            )}
                            {result.matchingColumns.length > 0 && (
                              <div className="flex flex-wrap gap-1 mt-2">
                                {result.matchingColumns.map(col => (
                                  <span
                                    key={col}
                                    className="inline-flex items-center px-1.5 py-0.5 rounded bg-slate-100 text-[10px] font-mono text-slate-600"
                                  >
                                    {col}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer hint */}
              <div className="px-5 py-3 border-t border-slate-200/60 bg-slate-50/40">
                <p className="text-[11px] text-slate-400 flex items-center gap-1.5">
                  <MessageSquare className="h-3 w-3" />
                  找不到？尝试换一个关键词，或使用自然语言描述，如「用户订单相关」
                </p>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
