/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect } from 'react';
import { useToast } from '../context/ToastContext';
import {
  Network,
  Cpu,
  Zap,
  Search,
  Download,
  Edit3,
  Settings2,
  Info,
  Server,
  Grid,
  TrendingUp,
  Activity,
  ArrowRight,
  Database,
  Layers,
  Sparkles,
  RefreshCw,
  Clock,
  Plus,
  Loader2,
} from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { SchemaRegistryItem, NodeStatus } from '../types';
import { queryApi, adminApi, schemaApi } from '../api';

export default function RegistryView() {
  const { error: toastError } = useToast()
  const [engineMode, setEngineMode] = useState<'single' | 'aggregate' | 'federated'>('federated');
  const [searchSchema, setSearchSchema] = useState('');
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);

  const [activeNodes, setActiveNodes] = useState<NodeStatus[]>([]);
  const [schemas, setSchemas] = useState<SchemaRegistryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [editingNode, setEditingNode] = useState<NodeStatus | null>(null);
  const [settingsNode, setSettingsNode] = useState<NodeStatus | null>(null);
  const [showAddNodeModal, setShowAddNodeModal] = useState(false);
  const [topologyZoom, setTopologyZoom] = useState(1);

  useEffect(() => {
    const load = async () => {
      setLoading(true)
      try {
        const [connResp, regResp] = await Promise.allSettled([
          adminApi.getConnections(),
          queryApi.getRegistry(),
        ])
        if (connResp.status === 'fulfilled') {
          const nodes: NodeStatus[] = connResp.value.items.map((db, i) => ({
            id: db.id || String(i),
            name: db.name || db.display_name || db.id,
            status: (db.status === 'online' || db.status === 'active') ? 'online' as const : (db.status === 'syncing' ? 'syncing' as const : 'offline' as const),
            metadata: `${db.tableCount || db.tables?.length || 0} Tables`,
            logo: db.type || 'database',
          }))
          setActiveNodes(nodes)
        }
        if (regResp.status === 'fulfilled') {
          setSchemas(regResp.value)
        }
      } catch (err) {
        toastError(err instanceof Error ? err.message : '加载注册表数据失败')
      }
      setLoading(false)
    }
    load()
  }, [])

  const handleSaveEngineMode = () => {
    // TODO: POST to backend when engine mode save API is available
    toastError(`引擎模式已切换至: ${engineMode}（保存功能待后端对接）`)
  }

  const handleRefreshSchema = async () => {
    setIsRefreshing(true)
    try {
      await schemaApi.refresh()
      toastError('Schema 缓存已刷新')
    } catch {
      toastError('刷新失败，请稍后重试')
    } finally {
      setIsRefreshing(false)
    }
  }

  const handleEditNode = (node: NodeStatus) => {
    setEditingNode(node)
  }

  const handleNodeSettings = (node: NodeStatus) => {
    setSettingsNode(node)
  }

  const handleAddNode = () => {
    setShowAddNodeModal(true)
  }

  const handleViewLogs = () => {
    alert('节点运行日志功能开发中，可前往 Dashboard 查看实时指标')
  }

  const handleExportSchemas = () => {
    const headers = ['Virtual Schema', 'Source Node', 'Source Entity', 'Type']
    const rows = schemas.map(s => [s.virtualSchema, s.sourceNode, s.sourceEntity, s.type])
    const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n')
    const blob = new Blob([csv], { type: 'text/csv' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'schema-registry.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <motion.div 
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -15 }}
      transition={{ duration: 0.35 }}
      className="space-y-6 pb-20 select-none"
    >
      
      {/* Header Info */}
      <header>
        <h1 className="font-display text-4xl font-black text-gray-900 leading-tight">架构配置中心</h1>
        <p className="text-sm text-gray-500 mt-1 font-sans">
          管理全球数据库拓扑、连接状态和统一模式映射。
        </p>
      </header>

      {/* Grid Layout: Topography Engine Map and Registered Nodes list list */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        
        {/* Left Big Space: Topology Canvas and Engines layout configuration */}
        <div className="xl:col-span-8 flex flex-col gap-6">
          
          {/* Engine Modes Select Card Hub */}
          <section className="panel rounded-xl p-5">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-sm font-bold text-gray-800 flex items-center gap-2">
                <Network className="h-4.5 w-4.5 text-slate-850" />
                <span>引擎模式</span>
              </h2>
              <span className="bg-status-p2/10 text-status-p2 border border-status-p2/20 px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider select-none animate-pulse">
                Active
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* Mode: Single */}
              <div 
                onClick={() => setEngineMode('single')}
                className={`panel rounded-lg p-4 cursor-pointer hover:bg-white/40 transition-all border ${
                  engineMode === 'single'
                    ? 'border-slate-800 ring-1 ring-slate-800 bg-white/60 shadow-lg shadow-slate-900/10'
                    : 'border-white/40'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <Server className="h-5 w-5 text-gray-500" />
                  <div className={`w-4.5 h-4.5 rounded-full border flex items-center justify-center ${
                    engineMode === 'single' ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300'
                  }`}>
                    {engineMode === 'single' && <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>}
                  </div>
                </div>
                <h3 className="text-xs font-bold text-gray-800">单节点</h3>
                <p className="text-[11px] text-gray-500 font-medium leading-normal mt-1">
                  直接连接到单个本地或云端主数据存储。
                </p>
              </div>

              {/* Mode: Aggregate Data Warehouse */}
              <div 
                onClick={() => setEngineMode('aggregate')}
                className={`panel rounded-lg p-4 cursor-pointer hover:bg-white/40 transition-all border ${
                  engineMode === 'aggregate'
                    ? 'border-slate-800 ring-1 ring-slate-800 bg-white/60 shadow-lg shadow-slate-900/10'
                    : 'border-white/40'
                }`}
              >
                <div className="flex items-center justify-between mb-2">
                  <Grid className="h-5 w-5 text-gray-500" />
                  <div className={`w-4.5 h-4.5 rounded-full border flex items-center justify-center ${
                    engineMode === 'aggregate' ? 'border-indigo-500 bg-indigo-50' : 'border-gray-300'
                  }`}>
                    {engineMode === 'aggregate' && <div className="w-2 h-2 bg-indigo-500 rounded-full"></div>}
                  </div>
                </div>
                <h3 className="text-xs font-bold text-gray-800">数据湖仓</h3>
                <p className="text-[11px] text-gray-500 font-medium leading-normal mt-1">
                  跨大规模数据湖的同步、批量聚合。
                </p>
              </div>

              {/* Mode: Federated (Current Active) */}
              <div 
                onClick={() => setEngineMode('federated')}
                className={`relative rounded-lg p-4 cursor-pointer transition-all border-2 overflow-hidden ${
                  engineMode === 'federated'
                    ? 'border-indigo-500 bg-indigo-50 shadow-md shadow-indigo-200/40'
                    : 'panel border-white/40 hover:bg-white/40'
                }`}
              >
                {/* Visual gradient orb */}
                <div className="absolute top-0 right-0 w-16 h-16 bg-indigo-500/5 rounded-bl-full blur-xl animate-pulse"></div>
                <div className="flex items-center justify-between mb-2 relative z-10">
                  <Zap className="h-5 w-5 text-indigo-500" />
                  <div className="w-4.5 h-4.5 rounded-full border-2 border-indigo-500 bg-indigo-50 flex items-center justify-center animate-pulse">
                    <div className="w-2.5 h-2.5 bg-indigo-500 rounded-full"></div>
                  </div>
                </div>
                <h3 className="text-xs font-bold text-gray-800 relative z-10">联邦多库</h3>
                <p className="text-[11px] text-slate-800 font-semibold leading-normal mt-1 relative z-10">
                  无需移动数据即可跨异构多集群统一秒级查询。
                </p>
              </div>
            </div>
            <div className="mt-4 flex justify-end">
              <button
                onClick={handleSaveEngineMode}
                className="px-4 py-2 bg-indigo-500 text-white rounded-lg text-xs font-bold hover:bg-indigo-600 transition-colors"
              >
                保存模式切换
              </button>
            </div>
          </section>

          {/* Topology Network Route Visual Map */}
          <section className="panel rounded-xl overflow-hidden relative" style={{ height: '400px' }}>
            {/* Dotted Coordinate Background Map lines */}
            <div className="absolute inset-0 topology-grid opacity-70"></div>
            <div className="absolute inset-0 bg-gradient-to-b from-transparent to-[#f7f9fb]/40 pointer-events-none"></div>
            
            <div className="absolute top-4 left-4 z-10 bg-white/70 backdrop-blur-md p-2 rounded-lg border border-white/20 select-none">
              <h2 className="text-xs font-bold text-gray-800">拓扑图</h2>
              <div className="text-[10px] text-gray-500 font-mono tracking-wide mt-0.5">实时路由可视化</div>
            </div>

            {/* Custom Scale indicators top right */}
            <div className="absolute top-4 right-4 z-10 flex gap-1.5 select-none">
              <button onClick={() => setTopologyZoom(z => Math.min(z + 0.2, 2))} className="w-7 h-7 rounded-full panel flex items-center justify-center text-gray-500 hover:text-black border border-white/40">+</button>
              <button onClick={() => setTopologyZoom(z => Math.max(z - 0.2, 0.5))} className="w-7 h-7 rounded-full panel flex items-center justify-center text-gray-500 hover:text-black border border-white/40">-</button>
              <button onClick={handleRefreshSchema} className="w-7 h-7 rounded-full panel flex items-center justify-center text-gray-500 hover:text-black border border-white/40">⟳</button>
            </div>

            {/* Faux Graph Node Items with SVG Link connections */}
            <div className="absolute inset-0 flex items-center justify-center">
              <div className="relative w-full max-w-lg h-64 select-none" style={{ transform: `scale(${topologyZoom})`, transition: 'transform 0.2s' }}>
                
                {/* Center Core: AI GenBI Engine Node pill board */}
                <div className="absolute top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 w-16 h-16 rounded-2xl panel-elevated flex items-center justify-center z-20 shadow-lg border-slate-900/30 bg-gradient-to-tr from-white to-slate-900/5">
                  <div className="absolute inset-0 rounded-2xl border border-slate-900/20 animate-ping" style={{ animationDuration: '3s' }}></div>
                  <Cpu className="h-8 w-8 text-black animate-pulse" />
                </div>

                {/* SVG Visual linking vectors pointers */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none drop-shadow-sm z-10">
                  {/* Link Line to PG Node */}
                  <line x1="256" y1="128" x2="150" y2="60" stroke="rgba(15, 23, 42, 0.2)" strokeWidth="1.5" strokeDasharray="3 3" />
                  {/* Link Line to Mongo Node */}
                  <line x1="256" y1="128" x2="380" y2="70" stroke="rgba(15, 23, 42, 0.25)" strokeWidth="2" />
                  {/* Link Line to Snowflake Node */}
                  <line x1="256" y1="128" x2="160" y2="210" stroke="rgba(15, 23, 42, 0.25)" strokeWidth="1.8" />
                  {/* Link Line to Redis Node */}
                  <line x1="256" y1="128" x2="360" y2="190" stroke="rgba(15, 23, 42, 0.2)" strokeWidth="1.5" strokeDasharray="3 3" />
                </svg>

                {/* Satellite Node: Postgres */}
                <div 
                  onMouseEnter={() => setHoveredNode('postgres')}
                  onMouseLeave={() => setHoveredNode(null)}
                  className="absolute top-[32px] left-[68px] panel-elevated hover:scale-105 transition-all text-xs font-bold text-gray-800 px-3.5 py-1.5 rounded-lg flex items-center gap-2 cursor-help z-20"
                >
                  <div className="w-2 h-2 rounded-full bg-status-p2 shadow-[0_0_8px_#22c55e]"></div>
                  <span>PostgreSQL_Prod</span>
                </div>

                {/* Satellite Node: MongoDB */}
                <div 
                  onMouseEnter={() => setHoveredNode('mongodb')}
                  onMouseLeave={() => setHoveredNode(null)}
                  className="absolute top-[42px] right-[40px] panel-elevated hover:scale-105 transition-all text-xs font-bold text-gray-800 px-3.5 py-1.5 rounded-lg flex items-center gap-2 cursor-help z-20"
                >
                  <div className="w-2 h-2 rounded-full bg-status-p2 shadow-[0_0_8px_#22c55e]"></div>
                  <span>Mongo_Events</span>
                </div>

                {/* Satellite Node: Snowflake */}
                <div 
                  onMouseEnter={() => setHoveredNode('snowflake')}
                  onMouseLeave={() => setHoveredNode(null)}
                  className="absolute bottom-[20px] left-[70px] panel-elevated hover:scale-105 transition-all text-xs font-bold text-gray-800 px-3.5 py-1.5 rounded-lg flex items-center gap-2 cursor-help z-20"
                >
                  <div className="w-2 h-2 rounded-full bg-status-p2 shadow-[0_0_8px_#22c55e]"></div>
                  <span>Snowflake_DW</span>
                </div>

                {/* Satellite Node: Redis Cache node */}
                <div 
                  onMouseEnter={() => setHoveredNode('redis')}
                  onMouseLeave={() => setHoveredNode(null)}
                  className="absolute bottom-[40px] right-[64px] panel-elevated hover:scale-105 transition-all text-xs font-bold text-gray-800 px-3.5 py-1.5 rounded-lg flex items-center gap-2 cursor-help z-20"
                >
                  <div className="w-2.5 h-2.5 rounded-full bg-[#FFB800] shadow-[0_0_8px_#FFB800] animate-pulse"></div>
                  <span>Redis_Cache</span>
                </div>

                {/* Popover Node details card */}
                <AnimatePresence>
                  {hoveredNode && (
                    <motion.div 
                      initial={{ scale: 0.95, opacity: 0 }}
                      animate={{ scale: 1, opacity: 1 }}
                      exit={{ scale: 0.95, opacity: 0 }}
                      className="absolute left-1/2 top-[5%] transform -translate-x-1/2 bg-white/95 border border-white shadow-xl backdrop-blur rounded px-3 py-1 text-[11px] font-bold text-gray-700 flex items-center gap-2"
                    >
                      <Sparkles className="h-3.5 w-3.5 text-slate-800 fill-slate-800" />
                      <span>
                        {hoveredNode === 'postgres' 
                          ? 'pg_core: 稳定联机状态 (42 Tables · 稳定路由)' 
                          : hoveredNode === 'mongodb' 
                          ? 'mongo_events: 高吞吐集群联机 (24 Collections)' 
                          : hoveredNode === 'snowflake' 
                          ? 'Snowflake_DW: 历史归档就绪' 
                          : 'redis_cache: 自底同步连接已激活'}
                      </span>
                    </motion.div>
                  )}
                </AnimatePresence>

              </div>
            </div>

            {/* Bottom mini KPI strip */}
            <div className="absolute bottom-0 left-0 w-full bg-white/90 backdrop-blur-xl border-t border-white/20 p-3.5 flex justify-between items-center z-10 select-none">
              <div className="flex gap-6">
                <div>
                  <div className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">总查询 (1h)</div>
                  <div className="text-xs font-bold text-gray-800 font-mono mt-0.5">142.5k</div>
                </div>
                <div>
                  <div className="text-[10px] text-gray-400 font-semibold uppercase tracking-wider">平均延迟</div>
                  <div className="text-xs font-bold text-slate-800 font-mono mt-0.5">42ms</div>
                </div>
              </div>

              <button onClick={handleViewLogs} className="text-xs font-bold text-black hover:underline flex items-center gap-0.5 cursor-pointer">
                <span>查看日志</span>
                <ArrowRight className="h-3.5 w-3.5" />
              </button>
            </div>
          </section>

        </div>

        {/* Right Side: Nodes Connected list (xl:col-span-4) */}
        <section className="xl:col-span-4 flex flex-col panel rounded-xl h-full overflow-hidden min-h-[480px]">
          <div className="p-4 border-b border-white/20 flex justify-between items-center bg-white/40">
            <h2 className="text-sm font-bold text-gray-800">已注册节点</h2>
            <button onClick={handleAddNode} className="p-1 text-gray-400 hover:text-black border border-white/40 rounded-md hover:bg-white/40 transition-colors">
              <Plus className="h-4 w-4" />
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-3 space-y-3">
            {activeNodes.map((node) => (
              <div 
                key={node.id} 
                className={`p-3 rounded-xl border border-white/20 hover:border-black hover:bg-white/40 transition-all duration-300 relative group cursor-pointer ${
                  node.status === 'syncing' ? 'bg-[#FFB800]/5 border-amber-100' : 'bg-white/20'
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <div className="flex items-center gap-2">
                    <Database className={`h-4.5 w-4.5 ${
                      node.status === 'online' ? 'text-slate-800' : 'text-[#FFB800]'
                    }`} />
                    <span className="text-xs font-bold text-gray-800">{node.name}</span>
                  </div>

                  <span className={`text-[10px] font-bold inline-flex items-center gap-1 px-2 py-0.5 rounded-full ${
                    node.status === 'online' 
                      ? 'bg-status-p2/15 text-status-p2' 
                      : 'bg-yellow-50 text-[#FFB800]'
                  }`}>
                    {node.status === 'online' ? (
                      <>
                        <span className="w-1.5 h-1.5 rounded-full bg-status-p2"></span> In check
                      </>
                    ) : (
                      <>
                        <RefreshCw className="h-3 w-3 animate-spin" /> Syncing
                      </>
                    )}
                  </span>
                </div>

                <div className="flex justify-between text-[11px] text-gray-500 font-medium pl-6">
                  <span>{node.metadata}</span>
                  <button onClick={() => handleEditNode(node)} className="opacity-0 group-hover:opacity-100 transition-opacity text-xs font-semibold text-black hover:underline flex items-center gap-0.5">
                    <Edit3 className="h-3 w-3" /> 编辑
                  </button>
                </div>
              </div>
            ))}
          </div>
        </section>

      </div>

      {/* Bottom Global Schemas Mapping Database Table Section */}
      <section className="panel rounded-xl p-5">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-light/10 pb-4 mb-4 select-none">
          <div>
            <h2 className="text-base font-bold text-gray-800">全局模式注册表</h2>
            <p className="text-xs text-gray-500 font-medium mt-0.5">
              统一命名空间映射用于联邦多集群关联查询。
            </p>
          </div>

          <div className="flex gap-2">
            <div className="relative">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400 h-3.5 w-3.5" />
              <input
                value={searchSchema}
                onChange={(e) => setSearchSchema(e.target.value)}
                className="w-48 text-xs font-medium pl-8 pr-3 py-1.5 bg-white/20 hover:bg-white/40 focus:bg-white rounded-lg border border-white/40 focus:border-black focus:outline-none transition-all placeholder-gray-400"
                placeholder="搜索模式..."
                type="text"
              />
            </div>
            <button className="px-3 py-1.5 rounded-lg border border-white/40 hover:bg-white/40 text-xs font-semibold text-gray-600 flex items-center gap-1 cursor-pointer transition-all">
              <Download className="h-3.5 w-3.5" />
              <span>导出</span>
            </button>
          </div>
        </div>

        {/* Registry schema datagrid list list */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs select-none">
            <thead>
              <tr className="border-b border-white/40 text-gray-400 font-semibold uppercase tracking-wider">
                <th className="p-3 font-medium">Virtual Schema</th>
                <th className="p-3 font-medium">Source Node</th>
                <th className="p-3 font-medium">Source Entity</th>
                <th className="p-3 font-medium">Type</th>
                <th className="p-3 font-medium text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="font-semibold text-gray-700">
              {schemas
                .filter(item => 
                  item.virtualSchema.toLowerCase().includes(searchSchema.toLowerCase()) ||
                  item.sourceNode.toLowerCase().includes(searchSchema.toLowerCase())
                )
                .map((row) => (
                  <tr key={row.virtualSchema} className="border-b border-white/10 hover:bg-white/20 transition-all duration-200">
                    <td className="p-3 text-slate-900 font-mono leading-none">{row.virtualSchema}</td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        row.sourceNode === 'Federated View' 
                          ? 'bg-black/5 text-slate-950' 
                          : 'bg-gray-100 text-gray-500'
                      }`}>
                        {row.sourceNode}
                      </span>
                    </td>
                    <td className="p-3 font-mono text-[10px] text-gray-400">{row.sourceEntity}</td>
                    <td className="p-3">
                      <span className={`px-2 py-0.5 rounded border text-[10px] ${
                        row.type === '虚拟视图'
                          ? 'border-slate-800 text-slate-800 bg-slate-100'
                          : row.type === 'Collection'
                          ? 'border-status-p1 text-status-p1 bg-yellow-50/50'
                          : 'border-status-p2 text-status-p2'
                      }`}>
                        {row.type}
                      </span>
                    </td>
                    <td className="p-3 text-right">
                      <button onClick={() => alert(`Schema 设置功能开发中: ${row.virtualSchema}`)} className="text-gray-400 hover:text-black p-1 rounded hover:bg-white/40 transition-colors cursor-pointer">
                        <Settings2 className="h-4 w-4" />
                      </button>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </div>

        <div className="text-center mt-4 pt-3 border-t border-white/20">
          <button onClick={handleExportSchemas} className="text-[11px] font-bold text-black hover:underline cursor-pointer">
            View All 42 Registered Schemas
          </button>
        </div>

      </section>

    </motion.div>
  );
}
