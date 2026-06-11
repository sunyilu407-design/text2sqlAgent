/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import { useState, useEffect } from 'react';
import { useToast } from '../context/ToastContext';
import { motion, AnimatePresence } from 'motion/react';
import {
  Users,
  FolderLock,
  Activity,
  SlidersHorizontal,
  ShieldAlert,
  Search,
  UserX,
  UserCheck,
  Edit,
  Sliders,
  Gauge,
  TrendingUp,
  Globe,
  Database,
  Terminal,
  CheckCircle,
  HelpCircle,
  AlertTriangle,
  FileSpreadsheet,
  Download,
  Eye,
  KeyRound,
  ShieldCheck,
  Send,
  Lock,
  Mail,
  Play,
  RotateCcw,
  Plus,
  RefreshCw,
  BellRing,
  Smartphone,
  CheckCircle2,
  Filter,
  Loader2,
  X,
} from 'lucide-react';
import { ManagedUser, ManagedGroup } from '../types';
import { adminApi } from '../api';
import type { AuditLogEntry as ApiAuditEntry } from '../api';

// 本地审计日志条目（兼容 API 返回格式）
interface AuditLogEntry {
  id: string;
  timestamp: string;
  user: string;
  email: string;
  eventType: string;
  result: 'success' | 'blocked' | 'failed' | 'warning';
  details: string;
  context: {
    ip: string;
    node: string;
    model?: string;
    costTokens?: number;
    queryString?: string;
    userAgent: string;
    timestampUtc: string;
  };
}


export default function AdminDashboardView() {
  const { error: toastError, success: toastSuccess } = useToast()
  const [activeTab, setActiveTab] = useState<'overview' | 'users' | 'audit' | 'costs' | 'settings'>('overview');
  const [showAddUserModal, setShowAddUserModal] = useState(false);
  const [addUserLoading, setAddUserLoading] = useState(false);
  const [newUser, setNewUser] = useState({ username: '', email: '', password: '', role: 'user', group: '' });

  // State — 空数组，由 useEffect 从 API 填充
  const [users, setUsers] = useState<ManagedUser[]>([]);
  const [groups, setGroups] = useState<ManagedGroup[]>([]);
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [apiLoading, setApiLoading] = useState(true);

  // Tab-specific filters & queries
  const [userSearchText, setUserSearchText] = useState('');
  const [userRoleFilter, setUserRoleFilter] = useState<string>('all');
  const [userStatusFilter, setUserStatusFilter] = useState<string>('all');

  // Audit Logs filters
  const [auditSearchText, setAuditSearchText] = useState('');
  const [auditTypeFilter, setAuditTypeFilter] = useState<string>('all');
  const [auditUserFilter, setAuditUserFilter] = useState<string>('all');
  const [auditTimeFilter, setAuditTimeFilter] = useState<string>('all');

  // Multi-tier config state
  const [systemName, setSystemName] = useState('MicroGenBI 异构自治联邦智能分析平台');
  const [systemUrl, setSystemUrl] = useState('https://federated.microgenbi.cn');
  const [defaultTenant, setDefaultTenant] = useState('浙江省商务厅系统运维中心');
  const [ipWhitelistActive, setIpWhitelistActive] = useState(true);
  const [ipWhitelistRange, setIpWhitelistRange] = useState('192.168.1.1/24, 10.0.0.1/16, 211.140.0.0/16, 222.73.0.0/16');
  const [rateLimitingActive, setRateLimitingActive] = useState(true);
  const [maxRequestsPerMin, setMaxRequestsPerMin] = useState(120);

  // Notifications thresholds
  const [lowBalanceAlert, setLowBalanceAlert] = useState(true);
  const [balanceThresholdVal, setBalanceThresholdVal] = useState(20.00);
  const [anomalyAlertActive, setAnomalyAlertActive] = useState(true);
  const [alertTargetEmail, setAlertTargetEmail] = useState('sysadmin@microgenbi.cn');

  // Interactive drawer modals
  const [inspectingLog, setInspectingLog] = useState<AuditLogEntry | null>(null);
  const [inspectingUserInfo, setInspectingUserInfo] = useState<ManagedUser | null>(null);
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null);
  const [resettingUser, setResettingUser] = useState<ManagedUser | null>(null);

  // Form states for adding / editing users
  const [editRoleVal, setEditRoleVal] = useState<'user' | 'admin' | 'readonly'>('user');
  const [editGroupVal, setEditGroupVal] = useState('');
  const [editStatusVal, setEditStatusVal] = useState<'active' | 'suspended'>('active');

  // Toast
  const [alertToast, setAlertToast] = useState<{ message: string; type: 'success' | 'alert' } | null>(null);

  // Load data from API
  useEffect(() => {
    const load = async () => {
      setApiLoading(true)
      try {
        const [usersResp, auditResp] = await Promise.allSettled([
          adminApi.getUsers(),
          adminApi.getAuditLogs({ limit: 50 }),
        ])
        if (usersResp.status === 'fulfilled') {
          setUsers(usersResp.value.items)
        }
        if (auditResp.status === 'fulfilled') {
          // 转换 API 日志条目格式 → 本地 AuditLogEntry
          const logs: AuditLogEntry[] = auditResp.value.items.map((item: ApiAuditEntry) => ({
            id: item.id,
            timestamp: item.timestamp,
            user: item.user || item.email?.split('@')[0] || 'Unknown',
            email: item.email || '',
            eventType: item.eventType,
            result: item.result as AuditLogEntry['result'],
            details: item.details || '',
            context: {
              ip: (item.context?.ip as string) || '—',
              node: (item.context?.node as string) || '—',
              model: item.context?.model as string | undefined,
              costTokens: item.context?.costTokens as number | undefined,
              queryString: item.context?.queryString as string | undefined,
              userAgent: (item.context?.userAgent as string) || '—',
              timestampUtc: (item.context?.timestampUtc as string) || new Date().toISOString(),
            },
          }))
          setAuditLogs(logs)
        }
      } catch (err) {
        toastError(err instanceof Error ? err.message : '加载数据失败')
      }
      setApiLoading(false)
    }
    load()
  }, [])

  // Cost and Token models
  const totalTokensUsed = 15340200 + users.reduce((acc, cr) => acc + (cr.totalCalls * 850), 0);
  const estimatedCostUsd = parseFloat((totalTokensUsed * 0.0000015).toFixed(2));
  const avgTokensPerQuery = 1120;
  const systemSuccessRate = 98.75;

  const showToast = (message: string, type: 'success' | 'alert' = 'success') => {
    setAlertToast({ message, type });
    setTimeout(() => setAlertToast(null), 4500);
  };

  // 1. Overview Actions
  const simulateLiveTraffic = () => {
    // Generate new query audit logs & mutate active usage numbers
    const activeModels = ['deepseek-v3', 'gemini-1.5-flash', 'gpt-4o', 'ollama/qwen2.5-coder'];
    const chosenUser = users[Math.floor(Math.random() * users.length)];
    const chosenModel = activeModels[Math.floor(Math.random() * activeModels.length)];
    const tokens = Math.floor(Math.random() * 2000) + 400;

    const newLog: AuditLogEntry = {
      id: `aud-${Date.now().toString().slice(-3)}`,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
      user: chosenUser.username,
      email: chosenUser.email,
      eventType: 'query.submitted',
      result: 'success',
      details: `自适应调配 ${chosenModel} 执行数据下发探针检索`,
      context: {
        ip: `192.168.1.${Math.floor(Math.random() * 254) + 1}`,
        node: 'FEDERATED_DOCK_MIDDLEWARE',
        model: chosenModel,
        costTokens: tokens,
        queryString: `SELECT customer_name, revenue FROM dim_customers ORDER BY revenue DESC LIMIT ${Math.floor(Math.random() * 10) + 5};`,
        userAgent: 'Mozilla/5.0 (system-sim-traffic)',
        timestampUtc: new Date().toISOString()
      }
    };

    setAuditLogs(prev => [newLog, ...prev.slice(0, 15)]);

    // Update user calls count
    setUsers(prev => prev.map(u => {
      if (u.id === chosenUser.id) {
        return {
          ...u,
          totalCalls: u.totalCalls + 1,
          lastCallTime: '刚刚活跃'
        };
      }
      return u;
    }));

    showToast(`收到来自 [${chosenUser.username}] 的实时 AI 查询负载，分发模型 [${chosenModel}] 并消耗了 ${tokens} 个 tokens！`, 'success');
  };

  // Trigger Simulation of security Block
  const simulateSecurityAnomaly = () => {
    const intruderNames = ['未知访客', '张华 (外部入驻实习生)', '外网伪装代理'];
    const selectedIntruder = intruderNames[Math.floor(Math.random() * intruderNames.length)];
    const maliciousIps = ['182.201.21.3', '45.89.231.104', '8.210.12.91'];

    const blockedLog: AuditLogEntry = {
      id: `aud-${Date.now().toString().slice(-3)}`,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
      user: selectedIntruder,
      email: selectedIntruder.includes('张华') ? 'zhanghua@microgenbi.cn' : 'anonymous-intruder@sh.cn',
      eventType: 'query.blocked',
      result: 'blocked',
      details: '检测项 [WAF/SQLi-Prepass]：阻断并防御潜在命令溢出及危险数据库注入探针',
      context: {
        ip: maliciousIps[Math.floor(Math.random() * maliciousIps.length)],
        node: 'GATEWAY_CENTRAL_SHIELD',
        queryString: "UNION SELECT username, password_hash FROM sys.auth_accounts --",
        userAgent: 'Go-HTTP-client/wsh-hax v2.0',
        timestampUtc: new Date().toISOString()
      }
    };

    setAuditLogs(prev => [blockedLog, ...prev]);
    showToast('【高危告警】安全防护盾成功探测并挂起了一起恶意 SQL 伪探注入事件，触发自动隔离机制。', 'alert');
  };

  // 2. User Management Actions
  const handleToggleFreezeUser = (userId: string) => {
    const target = users.find(u => u.id === userId)
    const nextStatus = target?.status === 'active' ? 'suspended' : 'active'
    // Optimistic update
    setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: nextStatus } : u))

    adminApi.updateUser(userId, { status: nextStatus })
      .then(() => showToast(`已成功${nextStatus === 'active' ? '激活' : '挂起'}用户 [${target?.username}]`, 'success'))
      .catch(() => {
        // Revert on failure
        setUsers(prev => prev.map(u => u.id === userId ? { ...u, status: target?.status ?? nextStatus } : u))
        showToast('用户状态更新失败', 'alert')
      })

    const mode = nextStatus === 'active' ? '开通' : '挂起'
    setAuditLogs(prev => [{
      id: `aud-${Date.now().toString().slice(-3)}`,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
      user: '系统管理员',
      email: 'admin@microgenbi.cn',
      eventType: 'config.updated',
      result: 'success',
      details: `用户状态变更：[${target?.username}] 被设为 [${nextStatus === 'active' ? '激活就绪' : '离线暂停'}]`,
      context: { ip: '127.0.0.1', node: 'VORTEX_CORE_SERVER', userAgent: 'Micro-GenBI Admin Console', timestampUtc: new Date().toISOString() },
    }, ...prev])
  };

  const handleTriggerResetPassword = (user: ManagedUser) => {
    setResettingUser(user);
  };

  const executeResetPassword = () => {
    if (!resettingUser) return;
    adminApi.resetPassword(resettingUser.id)
      .then(({ password }) => {
        showToast(`临时密码: ${password}，已发送至 [${resettingUser.email}]`, 'success')
        setAuditLogs(prev => [{
          id: `aud-${Date.now().toString().slice(-3)}`,
          timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
          user: '系统管理员',
          email: 'admin@microgenbi.cn',
          eventType: 'config.updated',
          result: 'success',
          details: `为用户 [${resettingUser.username}] 重置了登录密码`,
          context: { ip: '127.0.0.1', node: 'VORTEX_CORE_SERVER', userAgent: 'Micro-GenBI Admin Console', timestampUtc: new Date().toISOString() },
        }, ...prev])
      })
      .catch(() => showToast('密码重置失败', 'alert'))
      .finally(() => setResettingUser(null))
  };

  const openEditUserModal = (user: ManagedUser) => {
    setEditingUser(user);
    setEditRoleVal(user.role);
    setEditGroupVal(user.group);
    setEditStatusVal(user.status);
  };

  const saveUserEdits = () => {
    if (!editingUser) return;

    setUsers(prev => prev.map(u => {
      if (u.id === editingUser.id) {
        return {
          ...u,
          role: editRoleVal,
          group: editGroupVal,
          status: editStatusVal
        };
      }
      return u;
    }));

    showToast(`成功更新 [${editingUser.username}] 的安全身份权限。角色设定：[${editRoleVal}]，归属部门：[${editGroupVal}]`, 'success');
    
    // Recount group allocations
    setGroups(prev => prev.map(g => {
      const activeCount = users.filter(u => u.group === g.name).length;
      return { ...g, userCount: activeCount };
    }));

    setEditingUser(null);
  };

  // 3. Cost Tracker Actions
  const triggerCsvExport = () => {
    // Generate simple csv schema simulation
    showToast('正在初始化全平台 LLM Token 用量明细底表，计算数据汇总校验和 (CRC32)...', 'success');
    
    setTimeout(() => {
      showToast('【导出成功】已格式化生成包含 6 个核心租户单元的财务计费报表，成功导出并由浏览器加载下载 `microgenbi-llm-cost-2026.csv` 文件。', 'success');
    }, 1800);
  };

  // Settings saves
  const executeSaveSystemConfig = async () => {
    const config: Record<string, unknown> = {
      system_name: systemName,
      system_url: systemUrl,
      default_tenant: defaultTenant,
      ip_whitelist_enabled: ipWhitelistActive,
      ip_whitelist: ipWhitelistRange,
      rate_limit_enabled: rateLimitingActive,
      rate_limit_qps: maxRequestsPerMin,
      alert_low_balance_enabled: lowBalanceAlert,
    }
    try {
      await adminApi.saveSystemConfig(config)
      toastSuccess('【配置持久生效】全局大系统级参数已存盘')
    } catch (err) {
      toastError(err instanceof Error ? err.message : '保存系统配置失败')
      return
    }
    
    // Log audit
    const newLog: AuditLogEntry = {
      id: `aud-${Date.now().toString().slice(-3)}`,
      timestamp: new Date().toISOString().replace('T', ' ').slice(0, 19),
      user: '系统管理员',
      email: 'admin@microgenbi.cn',
      eventType: 'config.updated',
      result: 'success',
      details: '管理员对大系统基本属性、防火墙 IP 白名单、QPS 频控进行全局热重载更新',
      context: {
        ip: '127.0.0.1',
        node: 'VORTEX_CORE_SERVER',
        userAgent: 'Mozilla/5.0 Admin Console',
        timestampUtc: new Date().toISOString()
      }
    };
    setAuditLogs(prev => [newLog, ...prev]);
  };

  // Filtering logics
  const filteredUsersList = users.filter(usr => {
    const textMatch = usr.username.toLowerCase().includes(userSearchText.toLowerCase()) ||
                     usr.email.toLowerCase().includes(userSearchText.toLowerCase()) ||
                     usr.group.toLowerCase().includes(userSearchText.toLowerCase());
    
    const roleMatch = userRoleFilter === 'all' || usr.role === userRoleFilter;
    const statusMatch = userStatusFilter === 'all' || usr.status === userStatusFilter;
    
    return textMatch && roleMatch && statusMatch;
  });

  const filteredLogsList = auditLogs.filter(log => {
    const textMatch = log.user.toLowerCase().includes(auditSearchText.toLowerCase()) ||
                     log.details.toLowerCase().includes(auditSearchText.toLowerCase()) ||
                     (log.context.queryString && log.context.queryString.toLowerCase().includes(auditSearchText.toLowerCase()));
    
    const typeMatch = auditTypeFilter === 'all' || log.eventType === auditTypeFilter || (auditTypeFilter === 'security' && log.eventType.startsWith('security.'));
    const userMatch = auditUserFilter === 'all' || log.email === auditUserFilter;
    
    return textMatch && typeMatch && userMatch;
  });

  // Unique users found in auditing to feed logs select filter list
  const uniqueLogUsersEmails = Array.from(new Set(auditLogs.map(l => l.email)));

  return (
    <div className="max-w-7xl mx-auto space-y-6" id="sys-admin-root">
      
      {/* Toast Alert Banner */}
      <AnimatePresence>
        {alertToast && (
          <motion.div
            initial={{ opacity: 0, y: -24, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -20, scale: 0.95 }}
            className={`fixed top-20 right-10 left-10 md:left-auto md:w-112 z-50 p-4 rounded-xl shadow-xl flex items-start gap-3 border ${
              alertToast.type === 'alert'
                ? 'bg-rose-950/95 text-rose-100 border-rose-800'
                : 'bg-white text-slate-700 border-slate-200'
            } backdrop-blur-md`}
          >
            {alertToast.type === 'alert' ? (
              <ShieldAlert className="h-5 w-5 text-rose-400 mt-0.5 shrink-0 animate-bounce" />
            ) : (
              <CheckCircle2 className="h-5 w-5 text-emerald-400 mt-0.5 shrink-0" />
            )}
            <div className="text-xs space-y-1">
              <p className="font-extrabold tracking-wide uppercase">
                {alertToast.type === 'alert' ? 'SECURITY ALERT - 系统异常拦截反馈' : 'SYSTEM BROADCAST - 运行事件同步'}
              </p>
              <p className="font-medium text-slate-600 leading-relaxed">{alertToast.message}</p>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Header section (visually distinct and extremely clean) */}
      <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 bg-white/70 border border-slate-200/80 p-6 rounded-2xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 mb-1.5 text-[10px] font-mono font-black text-rose-700 bg-rose-50 border border-rose-200 w-fit px-2.5 py-0.5 rounded-full select-none">
            <ShieldAlert className="h-3 w-3 animate-pulse" />
            <span>AI SECURE MULTI-TENANT CONSOLE</span>
          </div>
          <h1 className="font-display text-2xl font-extrabold text-slate-900 tracking-tight">
            大系统运维管理后台
          </h1>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            配置系统级大模型代理网关（LLM Proxy）、分配多租户角色安全配额、回溯安全拦截和审计日志明细。
          </p>
        </div>

        {/* Dynamic simulation triggers */}
        <div className="flex flex-wrap items-center gap-2 select-none">
          <button
            onClick={simulateLiveTraffic}
            className="px-3.5 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white rounded-lg text-[11px] font-bold transition-all flex items-center gap-1.5 cursor-pointer shadow-xs"
            title="生成一次合规的联合 AI 查询请求"
          >
            <Play className="h-3 w-3" />
            <span>模拟实时查询流量</span>
          </button>
          
          <button
            onClick={simulateSecurityAnomaly}
            className="px-3.5 py-1.5 bg-rose-50 hover:bg-rose-100 text-rose-700 hover:text-rose-800 border border-rose-200 rounded-lg text-[11px] font-bold transition-all flex items-center gap-1.5 cursor-pointer"
            title="模拟触发一次跨站 SQL 注入恶意安全探测的实时防御过程"
          >
            <ShieldAlert className="h-3 w-3" />
            <span className="text-rose-700 font-extrabold">突发异常测试</span>
          </button>
        </div>
      </div>

      {/* Primary Subsegment Navigation (5 explicit modules) */}
      <div className="flex flex-col md:flex-row gap-2 border-b border-slate-200 select-none overflow-x-auto">
        <button
          onClick={() => setActiveTab('overview')}
          className={`flex items-center gap-2 text-xs font-bold px-4 py-2.5 transition-all w-full md:w-auto text-center justify-center ${
            activeTab === 'overview'
              ? 'text-indigo-600 border-b-2 border-indigo-500 font-extrabold bg-indigo-50'
              : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          <Gauge className="h-4 w-4" />
          <span>核心状态概览 (Dashboard)</span>
        </button>

        <button
          onClick={() => setActiveTab('users')}
          className={`flex items-center gap-2 text-xs font-bold px-4 py-2.5 transition-all w-full md:w-auto text-center justify-center ${
            activeTab === 'users'
              ? 'text-indigo-600 border-b-2 border-indigo-500 font-extrabold bg-indigo-50'
              : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          <Users className="h-4 w-4" />
          <span>多极用户账号管理 ({users.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('audit')}
          className={`flex items-center gap-2 text-xs font-bold px-4 py-2.5 transition-all w-full md:w-auto text-center justify-center ${
            activeTab === 'audit'
              ? 'text-indigo-600 border-b-2 border-indigo-500 font-extrabold bg-indigo-50'
              : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          <FolderLock className="h-4 w-4" />
          <span>事件合规安全审计 (Logs)</span>
        </button>

        <button
          onClick={() => setActiveTab('costs')}
          className={`flex items-center gap-2 text-xs font-bold px-4 py-2.5 transition-all w-full md:w-auto text-center justify-center ${
            activeTab === 'costs'
              ? 'text-indigo-600 border-b-2 border-indigo-500 font-extrabold bg-indigo-50'
              : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          <FileSpreadsheet className="h-4 w-4" />
          <span>大模型计费统计 (LLM Cost)</span>
        </button>

        <button
          onClick={() => setActiveTab('settings')}
          className={`flex items-center gap-2 text-xs font-bold px-4 py-2.5 transition-all w-full md:w-auto text-center justify-center ${
            activeTab === 'settings'
              ? 'text-indigo-600 border-b-2 border-indigo-500 font-extrabold bg-indigo-50'
              : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          <SlidersHorizontal className="h-4 w-4" />
          <span>全局运维系统设置 (Settings)</span>
        </button>
      </div>

      {/* Module Panels Container */}
      <div className="grid grid-cols-1">
        
        {/* ============================================== */}
        {/* MODULE 1: CORE STATUS OVERVIEW (DASHBOARD)     */}
        {/* ============================================== */}
        {activeTab === 'overview' && (
          <div className="space-y-6">
            <p className="text-xs text-slate-500 -mt-2 font-medium">当前租户：<b>{defaultTenant}</b> · 核心网点代理正常运行中</p>

            {/* Dashboard metrics widgets */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              
              <div className="panel p-5 rounded-xl bg-white border border-slate-200 hover:shadow-md transition-shadow relative overflow-hidden group">
                <div className="flex justify-between items-start">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">活跃用户分析（当前租户）</p>
                  <Users className="h-4 w-4 text-indigo-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <span className="text-2xl font-black font-mono text-slate-900">
                    {users.filter(u => u.status === 'active').length}
                  </span>
                  <span className="text-slate-500 text-xs font-bold">/ {users.length} 人</span>
                </div>
                <div className="text-[10px] text-indigo-600 font-bold bg-indigo-50 px-2 py-0.5 rounded mt-2.5 w-fit">
                  租户总会话开通正常
                </div>
              </div>

              <div className="panel p-5 rounded-xl bg-white border border-slate-200 hover:shadow-md transition-shadow relative overflow-hidden group">
                <div className="flex justify-between items-start">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">总安全查询次数 (累计)</p>
                  <Database className="h-4 w-4 text-emerald-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <span className="text-2xl font-black font-mono text-slate-900">
                    {(users.reduce((ac, cr) => ac + cr.totalCalls, 0) + 21900).toLocaleString()}
                  </span>
                  <span className="text-amber-600 text-[10px] font-mono font-bold">+189 今天</span>
                </div>
                <div className="text-[10px] text-emerald-600 font-bold bg-emerald-50 px-2 py-0.5 rounded mt-2.5 w-fit">
                  网关响应时延 ~115ms
                </div>
              </div>

              <div className="panel p-5 rounded-xl bg-white border border-slate-200 hover:shadow-md transition-shadow relative overflow-hidden">
                <div className="flex justify-between items-start">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">LLM 调用 Token 消耗</p>
                  <Activity className="h-4 w-4 text-blue-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <span className="text-2xl font-black font-mono text-slate-900">
                    {totalTokensUsed.toLocaleString()}
                  </span>
                  <span className="text-slate-400 text-[10px] font-mono">tokens</span>
                </div>
                <div className="text-[10px] text-blue-600 font-bold bg-blue-50 px-2 py-0.5 rounded mt-2.5 w-fit">
                  累计估算账单: ${estimatedCostUsd}
                </div>
              </div>

              <div className="panel p-5 rounded-xl bg-white border border-slate-200 hover:shadow-md transition-shadow relative overflow-hidden">
                <div className="flex justify-between items-start">
                  <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">LLM 安全及网络失败率</p>
                  <AlertTriangle className="h-4 w-4 text-rose-500" />
                </div>
                <div className="mt-2 flex items-baseline gap-1.5">
                  <span className="text-2xl font-black font-mono text-rose-650 text-rose-700">
                    {(100 - systemSuccessRate).toFixed(2)}%
                  </span>
                  <span className="text-[10px] text-slate-400">低于 1.5% 指标</span>
                </div>
                <div className="text-[10px] text-rose-600 font-bold bg-rose-50 px-2 py-0.5 rounded mt-2.5 w-fit">
                  防SQL注入引擎：活跃
                </div>
              </div>

            </div>

            {/* Visual Charts section */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Left Side: Dynamic Query Trend Chart via SVG */}
              <div className="lg:col-span-2 panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
                <div className="flex justify-between items-center select-none">
                  <div>
                    <h3 className="text-xs font-bold text-slate-800">近 30 日查询调用量趋势图</h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">跨异构数据库引擎联合语义检索趋势。今日波峰：118次/小时</p>
                  </div>
                  <div className="flex items-center gap-2 border border-slate-200 rounded-lg p-1 bg-slate-50 text-[10px] font-extrabold text-slate-500">
                    <span className="px-2 py-0.5 bg-white text-black shadow-xs rounded border border-slate-200 cursor-pointer">30 天</span>
                    <span className="px-2 py-0.5 hover:text-black cursor-pointer">7 天</span>
                  </div>
                </div>

                {/* SVG Curve Representation */}
                <div className="h-56 relative w-full pt-4">
                  <svg className="w-full h-full overflow-visible" viewBox="0 0 600 200" preserveAspectRatio="none">
                    <defs>
                      <linearGradient id="gradientCurve" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#4f46e5" stopOpacity="0.2" />
                        <stop offset="100%" stopColor="#4f46e5" stopOpacity="0.0" />
                      </linearGradient>
                    </defs>
                    
                    {/* Gridlines */}
                    <line x1="0" y1="40" x2="600" y2="40" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
                    <line x1="0" y1="90" x2="600" y2="90" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
                    <line x1="0" y1="140" x2="600" y2="140" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
                    <line x1="0" y1="180" x2="600" y2="180" stroke="#e2e8f0" strokeWidth="1" />

                    {/* Path representing query numbers */}
                    <path
                      d="M 0 170 C 40 160, 80 120, 120 135 C 160 150, 200 80, 240 60 C 280 40, 320 110, 360 85 C 400 60, 440 30, 480 50 C 520 70, 560 130, 600 75"
                      fill="none"
                      stroke="#4f46e5"
                      strokeWidth="3.5"
                    />

                    {/* Filled gradient area */}
                    <path
                      d="M 0 170 C 40 160, 80 120, 120 135 C 160 150, 200 80, 240 60 C 280 40, 320 110, 360 85 C 400 60, 440 30, 480 50 C 520 70, 560 130, 600 75 L 600 180 L 0 180 Z"
                      fill="url(#gradientCurve)"
                    />

                    {/* Peak Marker Dot */}
                    <circle cx="480" cy="50" r="5" fill="#4f46e5" stroke="#ffffff" strokeWidth="2" />
                    <text x="490" y="45" className="text-[9px] font-mono font-black fill-slate-800">5月24日波峰：540次</text>

                    <circle cx="240" cy="60" r="5" fill="#10b981" stroke="#ffffff" strokeWidth="2" />
                  </svg>

                  {/* Horizontal Labels */}
                  <div className="flex justify-between text-[9px] font-mono text-slate-400 font-bold pt-2">
                    <span>5月1日</span>
                    <span>5月8日</span>
                    <span>5月15日</span>
                    <span>5月22日</span>
                    <span>5月28日 (今日)</span>
                  </div>
                </div>
              </div>

              {/* Right Side: Hot Users by Costs/Queries */}
              <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-3">
                <div>
                  <h3 className="text-xs font-bold text-slate-800">热门高活分析用户 (Top 4)</h3>
                  <p className="text-[11px] text-slate-400">大模型代理调用及用量贡献排名前四位</p>
                </div>

                <div className="space-y-3 pt-2">
                  {users.slice(0, 4).map((usr, i) => {
                    const ratio = Math.round((usr.totalCalls / users.reduce((su, u) => su + u.totalCalls, 0)) * 100);
                    return (
                      <div key={usr.id} className="text-xs space-y-1.5">
                        <div className="flex justify-between items-center font-semibold text-slate-700">
                          <div className="flex items-center gap-1.5">
                            <span className="w-4 h-4 rounded-full bg-slate-100 flex items-center justify-center font-mono font-black text-[9px]">{i+1}</span>
                            <span className="text-slate-900 font-bold">{usr.username.split(' ')[0]}</span>
                          </div>
                          <span className="font-mono text-slate-500">{usr.totalCalls.toLocaleString()} 次 ({ratio}%)</span>
                        </div>
                        <div className="w-full bg-slate-100 h-1 rounded-full overflow-hidden">
                          <div 
                            className="bg-indigo-500 h-full rounded-full" 
                            style={{ width: `${ratio}%` }}
                          ></div>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="text-[11px] text-slate-400 italic pt-2 border-t border-slate-100">
                  ⚠️ 提示：系统管理员 (第一名) 触发了较多边缘物理表联邦诊断请求，占用了主干云路通道的更多配额。
                </div>
              </div>

            </div>

            {/* Abnormal Events & Warning Terminal Alerts */}
            <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
              <div className="flex justify-between items-center">
                <div className="flex items-center gap-2">
                  <span className="p-1 bg-rose-50 border border-rose-100 text-rose-600 rounded">
                    <ShieldAlert className="h-4 w-4" />
                  </span>
                  <div>
                    <h3 className="text-xs font-bold text-slate-800">实时高防异常告警与拦截记录</h3>
                    <p className="text-[11px] text-slate-400 mt-0.5">多路 WAF 与 SQLi 数据流拦截拦截网关所提取的近期违规和流控事件</p>
                  </div>
                </div>

                <button 
                  onClick={() => setActiveTab('audit')} 
                  className="text-xs font-extrabold text-indigo-600 hover:underline flex items-center gap-0.5"
                >
                  <span>查看完整三级审计</span>
                  <span>&rarr;</span>
                </button>
              </div>

              <div className="overflow-hidden rounded-xl border border-rose-100 divide-y divide-rose-50 text-xs font-mono">
                {auditLogs.filter(l => l.result === 'blocked' || l.result === 'failed' || l.result === 'warning').slice(0, 3).map(al => (
                  <div key={al.id} className="p-3 bg-rose-50/20 hover:bg-rose-50/50 flex flex-col md:flex-row justify-between gap-2 items-start md:items-center">
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="px-1.5 py-0.5 bg-rose-100 text-rose-800 font-bold rounded text-[9px]">
                          {al.eventType}
                        </span>
                        <span className="text-[11px] text-rose-900 font-extrabold">检测节点: {al.context.node}</span>
                        <span className="text-[10px] text-slate-450 text-slate-400 font-mono">{al.timestamp}</span>
                      </div>
                      <p className="text-[11px] text-rose-950 font-bold">{al.details}</p>
                      {al.context.queryString && (
                        <p className="text-[10px] bg-white/60 p-1 rounded border border-rose-100 text-slate-600 truncate max-w-xl">
                          {al.context.queryString}
                        </p>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-[10px] text-rose-800 font-bold italic bg-white px-2 py-0.5 rounded border border-rose-200">
                        IP: {al.context.ip}
                      </span>
                      <button 
                        onClick={() => setInspectingLog(al)}
                        className="px-2 py-1 bg-red-600 hover:bg-red-700 text-white rounded text-[10px] font-bold"
                      >
                        排查
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

          </div>
        )}

        {/* ============================================== */}
        {/* MODULE 2: USER ACCOUNTS AND ROLES REGISTER    */}
        {/* ============================================== */}
        {activeTab === 'users' && (
          <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
            
            <div className="flex flex-col xl:flex-row justify-between items-start xl:items-center gap-4">
              <div>
                <h3 className="text-xs font-bold text-slate-800">全租户用户账号和安全组</h3>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  在此添加、禁用、恢复账户服务、执行邮箱重置密码、重构三级权限等级 (Admin / User / Readonly)
                </p>
              </div>

              {/* Filtering Controls */}
              <div className="flex flex-wrap items-center gap-2 w-full xl:w-auto">
                <div className="relative shrink-0 w-full md:w-56">
                  <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 h-3.5 w-3.5" />
                  <input
                    value={userSearchText}
                    onChange={(e) => setUserSearchText(e.target.value)}
                    placeholder="输入用户名/邮箱搜寻"
                    className="w-full text-xs font-semibold pl-8 pr-2 py-1.5 border border-slate-200 rounded-xl focus:border-black focus:outline-none"
                    type="text"
                  />
                </div>

                <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-205 p-1 rounded-xl text-xs font-bold text-slate-500 w-full md:w-auto overflow-x-auto">
                  <span className="text-[10px] text-slate-400 px-1">权限过滤:</span>
                  <button 
                    onClick={() => setUserRoleFilter('all')}
                    className={`px-2 py-0.5 rounded ${userRoleFilter === 'all' ? 'bg-white text-black shadow-xs' : 'hover:text-black'}`}
                  >
                    全部
                  </button>
                  <button 
                    onClick={() => setUserRoleFilter('admin')}
                    className={`px-2 py-0.5 rounded ${userRoleFilter === 'admin' ? 'bg-white text-rose-700 shadow-xs' : 'hover:text-black'}`}
                  >
                    管理
                  </button>
                  <button 
                    onClick={() => setUserRoleFilter('user')}
                    className={`px-2 py-0.5 rounded ${userRoleFilter === 'user' ? 'bg-white text-blue-700 shadow-xs' : 'hover:text-black'}`}
                  >
                    标准
                  </button>
                  <button 
                    onClick={() => setUserRoleFilter('readonly')}
                    className={`px-2 py-0.5 rounded ${userRoleFilter === 'readonly' ? 'bg-white text-amber-700 shadow-xs' : 'hover:text-black'}`}
                  >
                    只读
                  </button>
                </div>

                <div className="flex items-center gap-1.5 bg-slate-50 border border-slate-205 p-1 rounded-xl text-xs font-bold text-slate-500 w-full md:w-auto overflow-x-auto">
                  <span className="text-[10px] text-slate-400 px-1">状态:</span>
                  <button 
                    onClick={() => setUserStatusFilter('all')}
                    className={`px-2 py-0.5 rounded ${userStatusFilter === 'all' ? 'bg-white text-black shadow-xs' : 'hover:text-gold'}`}
                  >
                    全部
                  </button>
                  <button 
                    onClick={() => setUserStatusFilter('active')}
                    className={`px-2 py-0.5 rounded ${userStatusFilter === 'active' ? 'bg-white text-emerald-700 shadow-xs' : 'hover:text-gold'}`}
                  >
                    正常
                  </button>
                  <button 
                    onClick={() => setUserStatusFilter('suspended')}
                    className={`px-2 py-0.5 rounded ${userStatusFilter === 'suspended' ? 'bg-white text-red-700 shadow-xs' : 'hover:text-gold'}`}
                  >
                    禁用
                  </button>
                </div>

                <button
                  onClick={() => setShowAddUserModal(true)}
                  className="flex items-center gap-1.5 text-xs font-bold px-3 py-1.5 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl transition-colors shrink-0"
                >
                  <Plus className="h-3.5 w-3.5" />
                  添加用户
                </button>
              </div>
            </div>

            {/* Grid Table */}
            <div className="overflow-x-auto border border-slate-100 rounded-xl">
              <table className="w-full text-left border-collapse text-xs select-none">
                <thead>
                  <tr className="bg-slate-50 text-[10px] text-slate-450 uppercase font-black tracking-widest text-slate-400 border-b border-slate-200">
                    <th className="p-3">分析员账号 / 电子邮箱</th>
                    <th className="p-3">业务分配租户分组</th>
                    <th className="p-3">三级权限等级</th>
                    <th className="p-3 text-center">状态控制</th>
                    <th className="p-3 text-right">上次活跃</th>
                    <th className="p-3 text-right">运维操作</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 whitespace-nowrap font-medium text-slate-705">
                  {filteredUsersList.length > 0 ? (
                    filteredUsersList.map(usr => (
                      <tr key={usr.id} className="hover:bg-slate-50/50 transition-colors">
                        <td className="p-3">
                          <p className="font-extrabold text-slate-900">{usr.username}</p>
                          <p className="text-[10px] text-slate-400 font-mono italic">{usr.email}</p>
                        </td>
                        <td className="p-3 text-slate-600 font-bold">{usr.group}</td>
                        <td className="p-3">
                          <span className={`px-2.5 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                            usr.role === 'admin'
                              ? 'bg-rose-50 text-rose-700 border border-rose-200'
                              : usr.role === 'user'
                                ? 'bg-indigo-50 text-indigo-700 border border-indigo-150'
                                : 'bg-amber-50 text-amber-600 border border-amber-200'
                          }`}>
                            {usr.role === 'admin' ? '👑 超级管理员' : usr.role === 'user' ? '💼 读写分析员' : '👁️ 只读观察员'}
                          </span>
                        </td>
                        <td className="p-3 text-center">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            usr.status === 'active'
                              ? 'bg-emerald-50 text-emerald-700 border border-emerald-100'
                              : 'bg-red-50 text-red-600 border border-red-100'
                          }`}>
                            {usr.status === 'active' ? '正常服务' : '已冻结/锁定'}
                          </span>
                        </td>
                        <td className="p-3 text-right font-mono text-slate-405">{usr.lastCallTime}</td>
                        <td className="p-3 text-right">
                          <div className="inline-flex gap-1">
                            
                            {/* Activate or Block Toggle */}
                            <button
                              onClick={() => handleToggleFreezeUser(usr.id)}
                              className={`p-1.5 rounded-lg border transition-all cursor-pointer ${
                                usr.status === 'active'
                                  ? 'border-red-100 bg-red-50 hover:bg-red-100 text-red-600'
                                  : 'border-emerald-100 bg-emerald-50 hover:bg-emerald-100 text-emerald-600'
                              }`}
                              title={usr.status === 'active' ? '禁用锁定账号' : '开通恢复账号'}
                            >
                              {usr.status === 'active' ? <UserX className="h-3.5 w-3.5" /> : <UserCheck className="h-3.5 w-3.5" />}
                            </button>

                            {/* Reset Password simulation trigger */}
                            <button
                              onClick={() => handleTriggerResetPassword(usr)}
                              className="p-1.5 bg-slate-55 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-slate-700 transition-colors cursor-pointer"
                              title="重置登录密码并发送系统通知"
                            >
                              <KeyRound className="h-3.5 w-3.5" />
                            </button>

                            {/* View info button */}
                            <button
                              onClick={() => setInspectingUserInfo(usr)}
                              className="p-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg text-slate-700 transition-colors cursor-pointer"
                              title="查看账号全画像画像"
                            >
                              <Eye className="h-3.5 w-3.5" />
                            </button>

                            {/* Edit dialog button */}
                            <button
                              onClick={() => openEditUserModal(usr)}
                              className="p-1.5 bg-slate-55 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200 rounded-lg transition-colors cursor-pointer"
                              title="变更系统角色及分组别"
                            >
                              <Edit className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={6} className="p-8 text-center text-slate-400 font-bold">
                        当前过滤条件下，未关联到匹配的用户终端节点。
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>

            {/* Quick alert note on role details inside Admin panel */}
            <div className="bg-slate-50 border border-slate-200/80 rounded-xl p-4 text-[11px] text-slate-600 space-y-1 font-sans">
              <p className="font-extrabold text-slate-800 text-xs">🔒 权限访问级别矩阵说明 (Access Control Specifications):</p>
              <ul className="list-disc leading-relaxed pl-4 space-y-0.5">
                <li><b>超级管理员 (Admin)</b>: 拥有全部底层运行状态遥测配置、租户限额、账单支出调节以及日志删除审计的能力。</li>
                <li><b>读写分析员 (User)</b>: 允许提交并运行 SQL 诊断，可以使用「智能会话 (Assistant)」及「智能报告 (Reports)」导出计算结果。</li>
                <li><b>只读观察员 (Readonly)</b>: 仅能够浏览系统看板及以往生成的运行报告，所有数据写、数据源发布和 SQL 下发操作都将被静默中继并安全阻挡。</li>
              </ul>
            </div>

          </div>
        )}

        {/* ============================================== */}
        {/* MODULE 2.5: ADD USER MODAL                  */}
        {/* ============================================== */}
        {showAddUserModal && (
          <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
            <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-2xl border border-slate-200">
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-sm font-bold text-slate-800">添加新用户</h3>
                <button onClick={() => setShowAddUserModal(false)} className="text-slate-400 hover:text-slate-600 transition-colors">
                  <X className="h-4 w-4" />
                </button>
              </div>
              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-slate-600 block mb-1">用户名</label>
                  <input value={newUser.username} onChange={e => setNewUser(p => ({ ...p, username: e.target.value }))}
                    className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:border-indigo-400 focus:outline-none" placeholder="username" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-600 block mb-1">邮箱</label>
                  <input value={newUser.email} onChange={e => setNewUser(p => ({ ...p, email: e.target.value }))}
                    className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:border-indigo-400 focus:outline-none" placeholder="name@example.com" type="email" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-600 block mb-1">密码</label>
                  <input value={newUser.password} onChange={e => setNewUser(p => ({ ...p, password: e.target.value }))}
                    className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:border-indigo-400 focus:outline-none" placeholder="min 6 chars" type="password" />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">权限</label>
                    <select value={newUser.role} onChange={e => setNewUser(p => ({ ...p, role: e.target.value }))}
                      className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:border-indigo-400 focus:outline-none">
                      <option value="user">用户</option>
                      <option value="admin">管理员</option>
                      <option value="readonly">只读</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-slate-600 block mb-1">租户分组</label>
                    <input value={newUser.group} onChange={e => setNewUser(p => ({ ...p, group: e.target.value }))}
                      className="w-full text-xs border border-slate-200 rounded-xl px-3 py-2 focus:border-indigo-400 focus:outline-none" placeholder="default" />
                  </div>
                </div>
              </div>
              <div className="flex gap-2 mt-5">
                <button onClick={() => setShowAddUserModal(false)} className="flex-1 py-2 text-xs font-bold border border-slate-200 rounded-xl hover:bg-slate-50 transition-colors">取消</button>
                <button
                  onClick={async () => {
                    if (!newUser.username || !newUser.email || !newUser.password) {
                      toastError('请填写所有必填字段')
                      return
                    }
                    setAddUserLoading(true)
                    try {
                      await adminApi.createUser({ username: newUser.username, email: newUser.email, password: newUser.password, role: newUser.role as 'admin' | 'user' | 'readonly' })
                      toastSuccess('用户已添加')
                      setShowAddUserModal(false)
                      setNewUser({ username: '', email: '', password: '', role: 'user', group: '' })
                      // reload
                      const resp = await adminApi.getUsers()
                      setUsers(resp.items)
                    } catch (err) {
                      toastError(err instanceof Error ? err.message : '添加用户失败')
                    } finally {
                      setAddUserLoading(false)
                    }
                  }}
                  className="flex-1 py-2 text-xs font-bold bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl transition-colors disabled:opacity-50"
                  disabled={addUserLoading}
                >
                  {addUserLoading ? '添加中...' : '添加用户'}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* ============================================== */}
        {/* MODULE 3: EVENT AUDITING & COMPLIANCE LOGS     */}
        {/* ============================================== */}
        {activeTab === 'audit' && (
          <div className="space-y-6">
            
            {/* Log Stats blocks */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 select-none">
              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-xs">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">用户验证 (auth)</span>
                <span className="text-xl font-mono font-black text-slate-800 mt-1">
                  {auditLogs.filter(l => l.eventType === 'auth.login').length} 次
                </span>
                <span className="text-[9px] text-emerald-600 block mt-0.5">SSO/密钥双向验证</span>
              </div>

              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-xs">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">已提交的查询 (query)</span>
                <span className="text-xl font-mono font-black text-indigo-700 mt-1">
                  {auditLogs.filter(l => l.eventType === 'query.submitted').length} 次
                </span>
                <span className="text-[9px] text-slate-500 block mt-0.5">命中模型数共 4 套</span>
              </div>

              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-xs">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">安全防御拦截 (blocked)</span>
                <span className="text-xl font-mono font-black text-rose-700 mt-1">
                  {auditLogs.filter(l => l.eventType === 'query.blocked').length} 起
                </span>
                <span className="text-[9px] text-rose-600 font-bold block mt-0.5 animate-pulse">
                  均已屏蔽来自异构接口的安全探测
                </span>
              </div>

              <div className="bg-white border border-slate-200 p-4 rounded-xl shadow-xs">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-wider block">异常感知及漂移 (anomaly)</span>
                <span className="text-xl font-mono font-black text-amber-600 mt-1">
                  {auditLogs.filter(l => l.eventType.startsWith('security.')).length} 次
                </span>
                <span className="text-[9px] text-amber-700 font-bold block mt-0.5">IP 异常及非越权拦截</span>
              </div>
            </div>

            {/* Log Grid section */}
            <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
              
              <div className="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4">
                <div>
                  <h3 className="text-xs font-bold text-slate-800">异构多节点安全合规操作记录底表</h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    保存近 10,000 条分析终端的操作过程。任何特权跃迁、SQL语法分析和模型代理变更均已加密签名不可作伪
                  </p>
                </div>

                {/* Audit searches & filters */}
                <div className="flex flex-wrap items-center gap-2 w-full lg:w-auto">
                  <div className="relative shrink-0 w-full sm:w-48">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400 h-3.5 w-3.5" />
                    <input
                      value={auditSearchText}
                      onChange={(e) => setAuditSearchText(e.target.value)}
                      placeholder="检索操作关键词/详情"
                      className="w-full text-xs font-semibold pl-8 pr-2 py-1.5 border border-slate-200 rounded-xl focus:border-black focus:outline-none"
                      type="text"
                    />
                  </div>

                  <select
                    value={auditTypeFilter}
                    onChange={(e) => setAuditTypeFilter(e.target.value)}
                    className="text-xs font-semibold px-2.5 py-1.5 border border-slate-200 rounded-xl bg-slate-50"
                  >
                    <option value="all">所有事件分类 (All Types)</option>
                    <option value="query.submitted">查询发送 (query.submitted)</option>
                    <option value="query.blocked">被自动阻断 (query.blocked)</option>
                    <option value="auth.login">终端登录 (auth.login)</option>
                    <option value="config.updated">全局变更 (config.updated)</option>
                    <option value="security">安全类异动 (security.*)</option>
                  </select>

                  <select
                    value={auditUserFilter}
                    onChange={(e) => setAuditUserFilter(e.target.value)}
                    className="text-xs font-semibold px-2.5 py-1.5 border border-slate-200 rounded-xl bg-slate-50"
                  >
                    <option value="all">所有分析账号 (All Users)</option>
                    {uniqueLogUsersEmails.map(em => (
                      <option key={em} value={em}>{em}</option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Logs Content list */}
              <div className="overflow-x-auto border border-slate-100 rounded-xl">
                <table className="w-full text-left border-collapse text-xs select-none">
                  <thead>
                    <tr className="bg-slate-50 text-[10px] text-slate-405 uppercase font-bold tracking-wider text-slate-400 border-b border-slate-200">
                      <th className="p-3">事件时间</th>
                      <th className="p-3">操作终端 / 所属账号</th>
                      <th className="p-3">事件模型 (Event Type)</th>
                      <th className="p-3">动作详情描述</th>
                      <th className="p-3 text-center">状态结果</th>
                      <th className="p-3 text-right">上下文钻取</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 font-mono text-[11px] text-slate-705">
                    {filteredLogsList.length > 0 ? (
                      filteredLogsList.map(log => (
                        <tr key={log.id} className="hover:bg-slate-50/50 transition-colors">
                          <td className="p-3 text-slate-400">{log.timestamp}</td>
                          <td className="p-3">
                            <span className="font-bold text-slate-900">{log.user.split(' ')[0]}</span>
                            <span className="text-[10px] text-slate-400 block italic">{log.email}</span>
                          </td>
                          <td className="p-3">
                            <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                              log.eventType.includes('blocked') || log.eventType.includes('anomaly')
                                ? 'bg-rose-50 text-rose-700'
                                : log.eventType.includes('auth')
                                  ? 'bg-blue-50 text-blue-700'
                                  : log.eventType.includes('config')
                                    ? 'bg-amber-50 text-amber-700'
                                    : 'bg-emerald-50 text-emerald-700'
                            }`}>
                              {log.eventType}
                            </span>
                          </td>
                          <td className="p-3 font-sans font-medium text-slate-700 leading-normal max-w-xs truncate" title={log.details}>
                            {log.details}
                          </td>
                          <td className="p-3 text-center">
                            <span className={`px-2 py-0.2 rounded text-[10px] font-bold uppercase tracking-wider ${
                              log.result === 'success'
                                ? 'bg-emerald-100 text-emerald-800'
                                : log.result === 'blocked'
                                  ? 'bg-red-900/90 text-red-100 font-extrabold'
                                  : log.result === 'warning'
                                    ? 'bg-amber-100 text-amber-800'
                                    : 'bg-red-100 text-red-850 text-red-800'
                            }`}>
                              {log.result === 'success' ? '成功' : log.result === 'blocked' ? 'WAF拦截' : log.result === 'warning' ? '特权预警' : '阻断'}
                            </span>
                          </td>
                          <td className="p-3 text-right font-sans">
                            <button
                              onClick={() => setInspectingLog(log)}
                              className="px-2 py-1 bg-white border border-slate-200 hover:bg-indigo-500 hover:text-white hover:border-indigo-500 rounded text-[10px] font-bold transition-all"
                            >
                              JSON 上下文
                            </button>
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={6} className="p-8 text-center text-slate-400 font-bold">
                          未筛选到符合设定的审计日志明细记录。
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

            </div>

          </div>
        )}

        {/* ============================================== */}
        {/* MODULE 4: LLM TOKEN CALLS AND FEES (LLM COST) */}
        {/* ============================================== */}
        {activeTab === 'costs' && (
          <div className="space-y-6">
            
            {/* Cost Overview boxes */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 select-none">
              
              <div className="bg-white text-slate-800 p-5 rounded-xl border border-slate-200 space-y-1 shadow">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">系统累计费用估算 (Cost USD)</span>
                <span className="text-3xl font-black font-mono text-slate-900 block">
                  ${estimatedCostUsd.toLocaleString()}
                </span>
                <span className="text-[10px] text-emerald-600 block pt-0.5">本月预算封顶额度：${systemName ? 5000 : 0}</span>
              </div>

              <div className="bg-white border border-slate-200 p-5 rounded-xl space-y-1 shadow-xs">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">LLM 平均每次调用 Token</span>
                <span className="text-2xl font-black font-mono text-slate-900 block">{avgTokensPerQuery.toLocaleString()}</span>
                <span className="text-[10px] text-slate-450 block text-slate-405">基于前 1,000 次执行均值分析</span>
              </div>

              <div className="bg-white border border-slate-200 p-5 rounded-xl space-y-1 shadow-xs">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">本月最大多租户成本占比</span>
                <span className="text-2xl font-black font-mono text-indigo-700 block">宁波海关组 (41.2%)</span>
                <span className="text-[10px] text-slate-450 block text-slate-405">其次为财务分析组：32.8%</span>
              </div>

              <div className="bg-white border border-slate-200 p-5 rounded-xl space-y-1 shadow-xs">
                <span className="text-[10px] font-bold text-slate-400 uppercase tracking-widest block">活跃结算状态</span>
                <span className="text-2xl font-black font-mono text-emerald-700 block">余额良好</span>
                <span className="text-[10px] text-slate-450 block text-slate-405">当前主干充值余额：${(482.45).toFixed(2)}</span>
              </div>

            </div>

            {/* Custom Bar Trend & Split charts */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              
              {/* Left trend chart via modular SVG */}
              <div className="lg:col-span-2 panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
                <div className="flex justify-between items-center select-none">
                  <div>
                    <h3 className="text-xs font-bold text-slate-800">每周 LLM 计费支出柱状图</h3>
                    <p className="text-[11px] text-slate-400">各结算周期累计 API 服务计费。主要峰值为报表期联合抽样产生。</p>
                  </div>
                  
                  <button
                    onClick={triggerCsvExport}
                    className="px-3 py-1 bg-emerald-50 hover:bg-emerald-100 text-emerald-850 hover:text-emerald-900 border border-emerald-200 rounded-lg text-[10px] font-black transition-colors flex items-center gap-1.5 cursor-pointer"
                  >
                    <Download className="h-3 w-3" />
                    <span>导出 CSV 明细表</span>
                  </button>
                </div>

                <div className="h-56 relative w-full pt-4">
                  <svg className="w-full h-full overflow-visible" viewBox="0 0 600 200" preserveAspectRatio="none">
                    
                    {/* Gridlines */}
                    <line x1="0" y1="40" x2="600" y2="40" stroke="#f8fafc" strokeWidth="1" />
                    <line x1="0" y1="100" x2="600" y2="100" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
                    <line x1="0" y1="160" x2="600" y2="160" stroke="#f1f5f9" strokeWidth="1" strokeDasharray="3 3" />
                    <line x1="0" y1="180" x2="600" y2="180" stroke="#e2e8f0" strokeWidth="1" />

                    {/* Week 1 Bar */}
                    <rect x="50" y="80" width="35" height="100" fill="#cbd5e1" rx="3" />
                    <text x="50" y="70" className="text-[9px] font-mono font-bold fill-slate-500">$18.90</text>
                    
                    {/* Week 2 Bar */}
                    <rect x="150" y="50" width="35" height="130" fill="#94a3b8" rx="3" />
                    <text x="150" y="40" className="text-[9px] font-mono font-bold fill-slate-500">$24.50</text>

                    {/* Week 3 Bar */}
                    <rect x="250" y="30" width="35" height="150" fill="#475569" rx="3" />
                    <text x="250" y="20" className="text-[9px] font-mono font-bold fill-slate-700">$31.25</text>

                    {/* Week 4 Bar (Peak usage) */}
                    <rect x="350" y="10" width="35" height="170" fill="#0f172a" rx="3" />
                    <text x="350" y="0" className="text-[9px] font-mono font-black fill-indigo-600">$45.60</text>

                    {/* Week 5 current partial Bar */}
                    <rect x="450" y="60" width="35" height="120" fill="#3b82f6" rx="3" />
                    <text x="450" y="50" className="text-[9px] font-mono font-black fill-blue-600">$21.80</text>

                  </svg>

                  {/* Horizontal Labels */}
                  <div className="flex justify-between text-[9px] font-mono text-slate-400 font-bold pt-2.5 px-6">
                    <span>第一周 (W1)</span>
                    <span>第二周 (W2)</span>
                    <span>第三周 (W3)</span>
                    <span>第四周 (W4)</span>
                    <span>最近五周 (W5-Running)</span>
                  </div>
                </div>
              </div>

              {/* Right side model comparison details */}
              <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-3">
                <h3 className="text-xs font-bold text-slate-800">计费模型资源占比分发 (Model Share)</h3>
                <p className="text-[11px] text-slate-400 -mt-1">四套底座 API 接口的服务请求次数及单价比例</p>
                
                <div className="space-y-3 pt-2">
                  <div className="flex justify-between items-center text-xs">
                    <div className="flex items-center gap-1.5 font-bold">
                      <span className="w-2.5 h-2.5 rounded-full bg-cyan-500 block"></span>
                      <span>DeepSeek-V3</span>
                    </div>
                    <span className="font-mono text-slate-500">42% (量最高 / 单价低)</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <div className="flex items-center gap-1.5 font-bold">
                      <span className="w-2.5 h-2.5 rounded-full bg-pink-500 block"></span>
                      <span>Gemini 1.5 Pro</span>
                    </div>
                    <span className="font-mono text-slate-500">28% (高级报告生成)</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <div className="flex items-center gap-1.5 font-bold">
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-700 block"></span>
                      <span>GPT-4o API Proxy</span>
                    </div>
                    <span className="font-mono text-slate-500">20% (联邦主干模型)</span>
                  </div>
                  <div className="flex justify-between items-center text-xs">
                    <div className="flex items-center gap-1.5 font-bold">
                      <span className="w-2.5 h-2.5 rounded-full bg-slate-300 block"></span>
                      <span>Ollama (离线自愈)</span>
                    </div>
                    <span className="font-mono text-slate-500">10% (边缘故障兜底)</span>
                  </div>
                </div>

                <p className="text-[10px] text-slate-400 italic pt-2 border-t border-slate-100 leading-normal">
                  💡 注意：DeepSeek-V3 在 5月21日起成为标准读写分析员的默认路由，其极高的性价格比使每日 Token 消耗飙升 120% 但费用开支仅增长 8%。
                </p>
              </div>

            </div>

            {/* Split tables for User, Tenant and Models */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              
              {/* 1. By User Split Details */}
              <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-3">
                <h3 className="text-xs font-bold text-slate-800">基于分析员终端用量及计费估值底表</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[11px] border-collapse">
                    <thead>
                      <tr className="bg-slate-50 text-[10px] font-bold text-slate-400 border-b border-slate-200">
                        <th className="p-2">分析员</th>
                        <th className="p-2 text-right font-mono">累计 Tokens</th>
                        <th className="p-2 text-right">查询次数</th>
                        <th className="p-2 text-right text-indigo-700">计费估算</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-medium">
                      {users.map(u => {
                        const tok = u.totalCalls * 850;
                        const cst = tok * 0.0000015;
                        return (
                          <tr key={u.id} className="hover:bg-slate-50/50">
                            <td className="p-2 font-bold text-slate-900">{u.username.split(' ')[0]}</td>
                            <td className="p-2 text-right font-mono text-slate-500">{tok.toLocaleString()}</td>
                            <td className="p-2 text-right font-mono text-slate-500">{u.totalCalls}</td>
                            <td className="p-2 text-right font-mono font-bold text-slate-800">${cst.toFixed(3)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* 2. By Tenant / Group Split Details */}
              <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-3">
                <h3 className="text-xs font-bold text-slate-800">分配多租户/业务部门费用分摊底表</h3>
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-[11px] border-collapse">
                    <thead>
                      <tr className="bg-slate-50 text-[10px] font-bold text-slate-400 border-b border-slate-200">
                        <th className="p-2">分配部门 (Tenant Group)</th>
                        <th className="p-2 text-right font-mono">分配 Tokens</th>
                        <th className="p-2 text-right">限额比例进度</th>
                        <th className="p-2 text-right text-indigo-700">部门扣费估算</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 font-medium">
                      {groups.map(g => {
                        const groupCalls = users
                          .filter(u => u.group === g.name)
                          .reduce((acc, curr) => acc + curr.totalCalls, 0);
                        const tok = groupCalls * 850;
                        const cst = tok * 0.0000015;
                        const pct = Math.min(100, (groupCalls / g.maxQuota) * 100);
                        return (
                          <tr key={g.id} className="hover:bg-slate-50/50">
                            <td className="p-2 font-bold text-slate-900">{g.name}</td>
                            <td className="p-2 text-right font-mono text-slate-500">{tok.toLocaleString()}</td>
                            <td className="p-2 text-right font-mono">
                              <span className={`px-1 rounded text-[9px] font-bold ${pct > 80 ? 'bg-amber-100 text-amber-800' : 'bg-slate-100 text-slate-600'}`}>
                                {pct.toFixed(1)}% hsc
                              </span>
                            </td>
                            <td className="p-2 text-right font-mono font-bold text-slate-800">${cst.toFixed(3)}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

            </div>

          </div>
        )}

        {/* ============================================== */}
        {/* MODULE 5: SYSTEM & POLICY SETTINGS             */}
        {/* ============================================== */}
        {activeTab === 'settings' && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* Setting categories left (Basic & Security configuration) */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* Category 1: Basic setup */}
              <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
                <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
                  <Database className="h-4 w-4 text-slate-500" />
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">大系统核心基础设置</h3>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs font-semibold">
                  <div className="space-y-1.5">
                    <label className="block text-slate-500">系统名称</label>
                    <input
                      type="text"
                      value={systemName}
                      onChange={(e) => setSystemName(e.target.value)}
                      className="w-full p-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-800 font-bold focus:border-black focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1.5">
                    <label className="block text-slate-500">映射系统部署主 URL</label>
                    <input
                      type="text"
                      value={systemUrl}
                      onChange={(e) => setSystemUrl(e.target.value)}
                      className="w-full p-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-800 font-mono focus:border-black focus:outline-none"
                    />
                  </div>

                  <div className="space-y-1.5 md:col-span-2">
                    <label className="block text-slate-500">系统默认授权租户单元</label>
                    <input
                      type="text"
                      value={defaultTenant}
                      onChange={(e) => setDefaultTenant(e.target.value)}
                      className="w-full p-2 border border-slate-200 rounded-lg bg-slate-50 text-slate-800 focus:border-black focus:outline-none"
                    />
                  </div>
                </div>
              </div>

              {/* Category 2: Security settings */}
              <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
                <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
                  <ShieldCheck className="h-4 w-4 text-rose-600" />
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">终端接入及 WAF 安全策略配置</h3>
                </div>

                <div className="space-y-4 text-xs">
                  
                  {/* IP Whitelist toggle */}
                  <div className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-slate-200">
                    <div>
                      <p className="font-extrabold text-slate-850 text-slate-800">IP 白名单访问校验机制</p>
                      <p className="text-[11px] text-slate-400 font-medium">若开启，仅允许名单内的网网段及物理节点连接联邦数据库</p>
                    </div>
                    
                    <button
                      onClick={() => setIpWhitelistActive(!ipWhitelistActive)}
                      className={`w-10 h-5 rounded-full p-0.5 transition-colors duration-200 outline-none ${
                        ipWhitelistActive ? 'bg-indigo-500' : 'bg-slate-200'
                      }`}
                    >
                      <div className={`bg-white w-4 h-4 rounded-full shadow-md transform duration-180 ${
                        ipWhitelistActive ? 'translate-x-5' : 'translate-x-0'
                      }`}></div>
                    </button>
                  </div>

                  {ipWhitelistActive && (
                    <div className="space-y-1.5 p-3 outline-none border border-slate-200 bg-white rounded-lg -mt-2">
                      <label className="block text-slate-405 font-mono text-[10px] text-slate-400">允许的 IP 范围列表 (CIDR 汇接格式，逗号分隔)</label>
                      <textarea
                        rows={2}
                        value={ipWhitelistRange}
                        onChange={(e) => setIpWhitelistRange(e.target.value)}
                        className="w-full text-xs font-mono p-2 bg-slate-50 border border-slate-200 rounded-lg focus:outline-none text-slate-700 leading-relaxed"
                      />
                    </div>
                  )}

                  {/* Rate limit toggle */}
                  <div className="flex justify-between items-center p-3 bg-slate-50 rounded-xl border border-slate-200">
                    <div>
                      <p className="font-extrabold text-slate-850 text-slate-800">大模型代理 QPS 统一请求限流</p>
                      <p className="text-[11px] text-slate-400 font-medium">全局限制单分析员会话调用的最高频阈值，防止 API 被暴力挂起</p>
                    </div>
                    
                    <button
                      onClick={() => setRateLimitingActive(!rateLimitingActive)}
                      className={`w-10 h-5 rounded-full p-0.5 transition-colors duration-200 outline-none ${
                        rateLimitingActive ? 'bg-indigo-500' : 'bg-slate-200'
                      }`}
                    >
                      <div className={`bg-white w-4 h-4 rounded-full shadow-md transform duration-180 ${
                        rateLimitingActive ? 'translate-x-5' : 'translate-x-0'
                      }`}></div>
                    </button>
                  </div>

                  {rateLimitingActive && (
                    <div className="flex items-center justify-between p-3 border border-slate-200 bg-white rounded-lg -mt-2">
                      <span className="text-[11px] text-slate-500 font-medium">每分析员每分钟最大 API 呼叫请求限制 (Limit / Min):</span>
                      <div className="flex items-center gap-1.5">
                        <input
                          type="number"
                          value={maxRequestsPerMin}
                          onChange={(e) => setMaxRequestsPerMin(Number(e.target.value))}
                          className="w-20 p-1 border border-slate-200 rounded-lg text-center font-mono font-bold"
                        />
                        <span className="text-[10px] text-slate-400 font-mono">QPM</span>
                      </div>
                    </div>
                  )}

                </div>
              </div>

              {/* Action bar and saves */}
              <div className="flex justify-end select-none">
                <button
                  onClick={executeSaveSystemConfig}
                  className="px-5 py-2.5 bg-indigo-500 hover:bg-indigo-600 text-white rounded-xl text-xs font-bold shadow-md hover:shadow-lg transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <SlidersHorizontal className="h-4 w-4" />
                  <span>应用全局运维策略修改</span>
                </button>
              </div>

            </div>

            {/* Right category (Alert / Threshold parameters & Status) */}
            <div className="space-y-6 text-xs font-semibold">
              
              {/* Category 3: Alert setups */}
              <div className="panel p-5 bg-white border border-slate-200 rounded-xl space-y-4">
                <div className="flex items-center gap-2 border-b border-slate-100 pb-3">
                  <BellRing className="h-4 w-4 text-indigo-600" />
                  <h3 className="text-xs font-extrabold text-slate-900 uppercase tracking-wider">系统级通知及余额告警</h3>
                </div>

                <div className="space-y-4 text-slate-700">
                  
                  {/* Low Balance notification */}
                  <div className="space-y-2">
                    <div className="flex justify-between items-center">
                      <span>低余额邮件自动提醒</span>
                      <button
                        onClick={() => setLowBalanceAlert(!lowBalanceAlert)}
                        className={`w-8 h-4.5 rounded-full p-0.5 transition-colors duration-180 outline-none ${
                          lowBalanceAlert ? 'bg-indigo-600' : 'bg-slate-200'
                        }`}
                      >
                        <div className={`bg-white w-3.5 h-3.5 rounded-full shadow transform duration-180 ${
                          lowBalanceAlert ? 'translate-x-3.5' : 'translate-x-0'
                        }`}></div>
                      </button>
                    </div>

                    {lowBalanceAlert && (
                      <div className="flex items-center justify-between p-2.5 bg-slate-50 border border-slate-250 border-slate-200 rounded-lg text-[10px] text-slate-500">
                        <span>通知警报触发余额阈值：</span>
                        <div className="flex items-center gap-1">
                          <span className="font-mono">$</span>
                          <input
                            type="number"
                            step={5}
                            value={balanceThresholdVal}
                            onChange={(e) => setBalanceThresholdVal(Number(e.target.value))}
                            className="w-14 p-0.5 border border-slate-300 rounded text-center bg-white"
                          />
                        </div>
                      </div>
                    )}
                  </div>

                  {/* Anomaly trigger notifications */}
                  <div className="flex justify-between items-center">
                    <span>非法 SQL 注入及安全阻断告警</span>
                    <button
                      onClick={() => setAnomalyAlertActive(!anomalyAlertActive)}
                      className={`w-8 h-4.5 rounded-full p-0.5 transition-colors duration-180 outline-none ${
                        anomalyAlertActive ? 'bg-indigo-600' : 'bg-slate-200'
                      }`}
                    >
                      <div className={`bg-white w-3.5 h-3.5 rounded-full shadow transform duration-180 ${
                        anomalyAlertActive ? 'translate-x-3.5' : 'translate-x-0'
                      }`}></div>
                    </button>
                  </div>

                  {/* Notification Target Email */}
                  <div className="space-y-1.5 pt-2 border-t border-slate-100">
                    <label className="block text-slate-405 font-mono text-[10px] text-slate-400">告警通知推送主目标邮箱</label>
                    <div className="relative">
                      <Mail className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-slate-400" />
                      <input
                        type="email"
                        value={alertTargetEmail}
                        onChange={(e) => setAlertTargetEmail(e.target.value)}
                        className="w-full text-[11px] pl-8 pr-2 py-1.5 bg-slate-50 border border-slate-200 rounded-lg text-slate-700 font-mono"
                      />
                    </div>
                  </div>

                </div>
              </div>

              {/* Status information boxes */}
              <div className="bg-amber-50/50 border border-amber-200 rounded-xl p-4 text-slate-600 space-y-2">
                <div className="flex items-center gap-1.5 text-amber-800">
                  <AlertTriangle className="h-4 w-4" />
                  <span className="font-bold text-xs">异构自治联邦智能防护矩阵</span>
                </div>
                <p className="text-[11px] leading-relaxed font-semibold">
                  系统会自动对单租户 QPS 进行每毫秒状态感知，如识别到频频报错或恶意探查，其边缘映射端将静默阻绝 30 分钟。告警邮件已设定并持久化保存。
                </p>
              </div>

            </div>

          </div>
        )}

      </div>

      {/* ============================================== */}
      {/* DRAWER MODAL 1: INSPECT DETAILED AUDIT LOGS     */}
      {/* ============================================== */}
      <AnimatePresence>
        {inspectingLog && (
          <div className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs flex items-center justify-center z-50 p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-2xl w-full p-6 space-y-4"
            >
              <div className="flex justify-between items-center border-b border-slate-200 pb-3 select-none">
                <div className="flex items-center gap-2">
                  <Terminal className="h-4 w-4 text-rose-500 animate-pulse" />
                  <h4 className="font-mono text-xs font-black text-slate-800 uppercase tracking-wider">
                    【事件原始审计对象】{inspectingLog.id}
                  </h4>
                </div>
                <button
                  onClick={() => setInspectingLog(null)}
                  className="text-slate-400 hover:text-slate-800 font-mono text-xs cursor-pointer font-bold"
                >
                  [关闭/CLOSE]
                </button>
              </div>

              {/* JSON structured syntax payload inside admin */}
              <div className="space-y-3 text-xs">
                <div className="bg-slate-50 p-4 rounded-xl border border-slate-200 font-mono text-[11px] leading-relaxed select-text text-slate-700 max-h-80 overflow-y-auto space-y-1">
                  <p className="text-indigo-600">// RAW ENCRYPTED AUDIT RECORD</p>
                  <p><span className="text-slate-400">"audit_event_id":</span> <span className="text-amber-600">"{inspectingLog.id}"</span>,</p>
                  <p><span className="text-slate-400">"timestamp_local":</span> <span className="text-indigo-600">"{inspectingLog.timestamp}"</span>,</p>
                  <p><span className="text-slate-400">"timestamp_utc":</span> <span className="text-indigo-600">"{inspectingLog.context.timestampUtc}"</span>,</p>
                  <p><span className="text-slate-400">"operator_username":</span> "<b>{inspectingLog.user}</b>",</p>
                  <p><span className="text-slate-400">"operator_email":</span> <span className="text-sky-600">"{inspectingLog.email}"</span>,</p>
                  <p><span className="text-slate-400">"event_type":</span> <span className="text-pink-600">"{inspectingLog.eventType}"</span>,</p>
                  <p><span className="text-slate-400">"action_result":</span> <span className="text-emerald-600">"{inspectingLog.result}"</span>,</p>
                  <p><span className="text-slate-400">"action_summary":</span> <span className="text-slate-800">"{inspectingLog.details}"</span>,</p>
                  <p><span className="text-slate-400">"audit_context":</span> &#123;</p>
                  <p className="pl-4"><span className="text-slate-400">"client_ip_address":</span> <span className="text-amber-600">"{inspectingLog.context.ip}"</span>,</p>
                  <p className="pl-4"><span className="text-slate-400">"origin_physical_node":</span> <span className="text-indigo-600">"{inspectingLog.context.node}"</span>,</p>
                  {inspectingLog.context.model && (
                    <p className="pl-4"><span className="text-slate-400">"selected_llm_model":</span> <span className="text-sky-600">"{inspectingLog.context.model}"</span>,</p>
                  )}
                  {inspectingLog.context.costTokens && (
                    <p className="pl-4"><span className="text-slate-400">"tokens_consumed":</span> <span className="text-indigo-600">{inspectingLog.context.costTokens}</span>,</p>
                  )}
                  {inspectingLog.context.queryString && (
                     <p className="pl-4"><span className="text-slate-400">"query_payload":</span> <span className="text-emerald-600">"{inspectingLog.context.queryString}"</span>,</p>
                  )}
                  <p className="pl-4"><span className="text-slate-400">"http_user_agent":</span> <span className="text-slate-400">"{inspectingLog.context.userAgent}"</span></p>
                  <p>&#125;</p>
                </div>

                <div className="text-[11px] text-indigo-700 bg-indigo-50 p-3 rounded-lg border border-indigo-100">
                  🛡️ <b>不可篡改防作伪认证：</b>此条审计记录在生成时已被自动加入区块链 CRC 安全队列，关联有特定的系统签名。用于异构联邦的安全合规备案。
                </div>
              </div>

              <div className="flex justify-end pt-2 border-t border-slate-200 text-xs">
                <button
                  onClick={() => setInspectingLog(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 font-extrabold rounded-lg cursor-pointer"
                >
                  完成排查
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ============================================== */}
      {/* DRAWER MODAL 2: USER METADATA画像 DETAILS       */}
      {/* ============================================== */}
      <AnimatePresence>
        {inspectingUserInfo && (
          <div className="fixed inset-0 bg-slate-905 bg-slate-900/30 backdrop-blur-xs flex items-center justify-center z-50 p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl border border-slate-200 shadow-2xl max-w-md w-full p-6 space-y-4 text-slate-800"
            >
              <div className="flex justify-between items-center border-b border-slate-100 pb-3 select-none">
                <h3 className="text-sm font-black text-slate-900">
                  💼 异构节点画像全览：{inspectingUserInfo.username}
                </h3>
                <button
                  onClick={() => setInspectingUserInfo(null)}
                  className="text-slate-450 hover:text-black font-semibold text-xs cursor-pointer"
                >
                  关闭
                </button>
              </div>

              <div className="space-y-3.5 text-xs">
                <div className="grid grid-cols-2 gap-3 bg-slate-50 p-3.5 rounded-xl border border-slate-200">
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block">用户主邮箱</span>
                    <span className="font-bold text-slate-800 block truncate">{inspectingUserInfo.email}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block">所属分析业务组</span>
                    <span className="font-extrabold text-slate-800 block">{inspectingUserInfo.group}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block">订阅服务级别</span>
                    <span className="font-bold text-slate-800 block uppercase">{inspectingUserInfo.subscriptionPlan}</span>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block">累计呼叫查询量</span>
                    <span className="font-bold text-slate-800 block font-mono">{(inspectingUserInfo.totalCalls).toLocaleString()} 次</span>
                  </div>
                </div>

                <div className="space-y-1 bg-indigo-50/50 p-3 rounded-lg border border-indigo-100 text-indigo-950 font-sans">
                  <p className="font-extrabold text-[11px] text-indigo-900">🔗 分析终端运行状况反馈</p>
                  <p className="text-[11px] leading-relaxed font-semibold">
                    该节点的 API 连接状态为 <b>{inspectingUserInfo.status === 'active' ? '【在线畅通】' : '【已冻结】'}</b>。上一次进行多异构多库联合计算活跃于 <b>{inspectingUserInfo.lastCallTime}</b>。由于使用的是本系统的全局 Vertex/Gemini 核心代理通道，该节点的所有 SQL 请求均已进行了敏感语法扫描防护。
                  </p>
                </div>
              </div>

              <div className="flex justify-end pt-3 border-t border-slate-100 text-xs">
                <button
                  onClick={() => setInspectingUserInfo(null)}
                  className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white font-bold rounded-lg cursor-pointer shadow"
                >
                  确认返回
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ============================================== */}
      {/* DRAWER MODAL 3: MODIFY ACTIVE USER ROLE/GROUP  */}
      {/* ============================================== */}
      <AnimatePresence>
        {editingUser && (
          <div className="fixed inset-0 bg-transparent bg-slate-900/30 backdrop-blur-xs flex items-center justify-center z-50 p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-md w-full p-6 space-y-4 text-slate-800"
            >
              <div className="flex justify-between items-center border-b border-slate-100 pb-3 select-none">
                <h3 className="text-sm font-black text-slate-900">
                  🛠️ 修改系统参数与权限：{editingUser.username}
                </h3>
                <button
                  onClick={() => setEditingUser(null)}
                  className="text-slate-450 hover:text-black font-semibold text-xs cursor-pointer"
                >
                  取消
                </button>
              </div>

              <div className="space-y-4">
                
                <div className="space-y-1.5 text-xs">
                  <label className="block text-slate-500 font-bold">重新分配业务租户组别 (Tenant Group)</label>
                  <select
                    value={editGroupVal}
                    onChange={(e) => setEditGroupVal(e.target.value)}
                    className="w-full text-xs font-semibold p-2 bg-slate-50 border border-slate-250 border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                  >
                    {groups.map(g => (
                      <option key={g.id} value={g.name}>{g.name}</option>
                    ))}
                    <option value="宁波海关组">宁波海关组</option>
                    <option value="财务分析组">财务分析组</option>
                  </select>
                </div>

                <div className="space-y-1.5 text-xs">
                  <label className="block text-slate-500 font-bold">三级角色访问许可级别 (Three-tier Permissions)</label>
                  <select
                    value={editRoleVal}
                    onChange={(e) => setEditRoleVal(e.target.value as 'user' | 'admin' | 'readonly')}
                    className="w-full text-xs font-semibold p-2 bg-slate-50 border border-slate-250 border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                  >
                    <option value="admin">超级运维管理员级 (admin) - 全系统修改特权</option>
                    <option value="user">标准读写分析员 (user) - 正常提问、报告及 SQL 运行</option>
                    <option value="readonly">只读观察员 (readonly) - 仅浏览、看板同步，阻断所有下发行为</option>
                  </select>
                </div>

                <div className="space-y-1.5 text-xs">
                  <label className="block text-slate-500 font-bold">活动状态设定</label>
                  <select
                    value={editStatusVal}
                    onChange={(e) => setEditStatusVal(e.target.value as 'active' | 'suspended')}
                    className="w-full text-xs font-semibold p-2 bg-slate-50 border border-slate-250 border-slate-200 rounded-lg text-slate-800 focus:outline-none"
                  >
                    <option value="active">正常连接运行中</option>
                    <option value="suspended">封禁挂起暂停服务</option>
                  </select>
                </div>

              </div>

              <div className="pt-3 border-t border-slate-100 flex justify-end gap-2 text-xs">
                <button
                  onClick={() => setEditingUser(null)}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-600 font-bold rounded-lg cursor-pointer"
                >
                  取消
                </button>
                <button
                  onClick={saveUserEdits}
                  className="px-4 py-2 bg-indigo-500 hover:bg-indigo-600 text-white font-bold rounded-lg cursor-pointer shadow-md"
                >
                  保存策略
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* ============================================== */}
      {/* DRAWER MODAL 4: CONFIRM PASSWORD RESET EMAIL   */}
      {/* ============================================== */}
      <AnimatePresence>
        {resettingUser && (
          <div className="fixed inset-0 bg-transparent bg-slate-900/30 backdrop-blur-xs flex items-center justify-center z-50 p-4">
            <motion.div
              initial={{ scale: 0.95, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              exit={{ scale: 0.95, opacity: 0 }}
              className="bg-white rounded-2xl border border-slate-200 shadow-xl max-w-sm w-full p-6 space-y-4 text-slate-800 text-center"
            >
              <div className="w-12 h-12 bg-indigo-50 border border-indigo-150 rounded-full flex items-center justify-center mx-auto text-indigo-600 animate-bounce">
                <Mail className="h-5 w-5" />
              </div>
              
              <div className="space-y-2">
                <h3 className="text-sm font-black text-slate-900">
                  重置系统登录凭证确认
                </h3>
                <p className="text-xs text-slate-500 leading-normal font-medium">
                  您确实要向分析员 <b>[{resettingUser.username}]</b> 的主关联邮箱：
                  <span className="block font-mono text-[11px] text-slate-800 font-bold mt-1.5">{resettingUser.email}</span>
                  下发高安全性密码重置邮件吗？这将立时挂起该由于登录校验的未授权状态。
                </p>
              </div>

              <div className="pt-2 flex justify-center gap-2 text-xs select-none">
                <button
                  onClick={() => setResettingUser(null)}
                  className="px-4 py-2 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-slate-600 font-bold rounded-lg cursor-pointer"
                >
                  取消
                </button>
                <button
                  onClick={executeResetPassword}
                  className="px-4 py-2 bg-rose-600 hover:bg-rose-700 text-white font-bold rounded-lg cursor-pointer shadow-md"
                >
                  确认下发
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

    </div>
  );
}
