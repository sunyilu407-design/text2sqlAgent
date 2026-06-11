/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */
import { useState, useEffect, useRef } from 'react';
import { Search, Sparkles, Bell, Settings, User, LogOut, ShieldCheck, Check, X, FileText, Clock } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { ScreenType, UserSession } from '../types';
import { queryApi, adminApi } from '../api';
import { useToast } from '../context/ToastContext';

interface TopNavBarProps {
  currentScreen: ScreenType;
  onScreenChange: (screen: ScreenType) => void;
  onSearchChange?: (val: string) => void;
  session: UserSession | null;
  onLogout: () => void;
}

export interface NotificationItem {
  id: string;
  title: string;
  message: string;
  time: string;
  read: boolean;
}

const NAV_ITEMS: { key: ScreenType; label: string }[] = [
  { key: 'dashboard', label: '仪表盘' },
  { key: 'query',     label: '查询' },
  { key: 'registry',  label: '注册表' },
  { key: 'reports',  label: '报告' },
  { key: 'health',    label: '健康监控' },
];

export default function TopNavBar({
  currentScreen,
  onScreenChange,
  onSearchChange,
  session,
  onLogout,
}: TopNavBarProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<{name: string; type: string; description: string}[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Notification state
  const [showNotifications, setShowNotifications] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [loadingNotifications, setLoadingNotifications] = useState(false);
  const notificationRef = useRef<HTMLDivElement>(null);
  const { error: toastError } = useToast();

  // Fetch notifications on mount
  useEffect(() => {
    const fetchNotifications = async () => {
      setLoadingNotifications(true);
      try {
        const data = await adminApi.getSecurityAlerts();
        const mapped: NotificationItem[] = (data.items ?? []).map((alert) => ({
          id: alert.id,
          title: `[${alert.severity}] ${alert.type}`,
          message: alert.description,
          time: new Date(alert.timestamp).toLocaleString('zh-CN', {
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
          }),
          read: alert.acknowledged,
        }));
        setNotifications(mapped);
      } catch {
        toastError('获取通知失败');
      } finally {
        setLoadingNotifications(false);
      }
    };
    fetchNotifications();
  }, [toastError]);

  const unreadCount = notifications.filter((n) => !n.read).length;

  const handleMarkAllRead = () => {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  };

  const handleMarkRead = (id: string) => {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
    adminApi.ackAlert(id).catch(() => {});
  };

  // Close notification dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (notificationRef.current && !notificationRef.current.contains(e.target as Node)) {
        setShowNotifications(false);
      }
    };
    if (showNotifications) {
      document.addEventListener('mousedown', handler);
    }
    return () => {
      document.removeEventListener('mousedown', handler);
    };
  }, [showNotifications]);

  // Debounced global search
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults([]);
      setShowSearchDropdown(false);
      onSearchChange?.('');
      return;
    }
    onSearchChange?.(searchQuery);
    const timer = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const res = await queryApi.searchSchema(searchQuery);
        setSearchResults(res.results.slice(0, 8).map(r => ({
          name: r.table || '',
          type: r.database || 'table',
          description: r.description || '',
        })));
        setShowSearchDropdown(true);
      } catch {
        setSearchResults([]);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery, onSearchChange]);

  // Close dropdown on outside click
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowSearchDropdown(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <nav className="panel border-t-0 border-x-0 bg-white shadow-sm flex justify-between items-center w-full px-8 py-2.5 h-16 sticky top-0 z-50">

      {/* Left — Brand */}
      <div className="flex items-center gap-8">
        <div
          onClick={() => onScreenChange('dashboard')}
          className="flex items-center gap-2 cursor-pointer select-none"
        >
          <Sparkles className="h-5 w-5 text-indigo-500" />
          <span className="font-bold text-lg text-slate-800 tracking-tight">Micro-GenBI</span>
        </div>

        {/* Nav pills */}
        <div className="hidden lg:flex gap-1 items-center select-none">
          {NAV_ITEMS.map(({ key, label }) => {
            const isActive  = currentScreen === key;
            const isHealth = key === 'health';
            if (isHealth) {
              return (
                <button
                  key={key}
                  onClick={() => onScreenChange(key)}
                  className={`text-xs font-semibold px-3.5 py-1.5 rounded-full transition-all ${
                    isActive
                      ? 'text-white bg-emerald-500 shadow-sm'
                      : 'text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50'
                  }`}
                >
                  {label}
                </button>
              );
            }
            return (
              <button
                key={key}
                onClick={() => onScreenChange(key)}
                className={`text-xs font-semibold px-3.5 py-1.5 rounded-full transition-all ${
                  isActive
                    ? 'text-white bg-indigo-500 shadow-sm'
                    : 'text-slate-500 hover:text-slate-800 hover:bg-slate-100'
                }`}
              >
                {label}
              </button>
            );
          })}

          {/* Admin badge */}
          {session?.role === 'admin' && (
            <button
              onClick={() => onScreenChange('admin')}
              className={`text-xs font-bold px-3.5 py-1.5 rounded-full transition-all flex items-center gap-1 ${
                currentScreen === 'admin'
                  ? 'text-white bg-rose-500 shadow-sm'
                  : 'text-rose-600 hover:text-rose-700 hover:bg-rose-50 border border-rose-200'
              }`}
            >
              运维后台
            </button>
          )}
        </div>
      </div>

      {/* Right — Controls */}
      <div className="flex items-center gap-3">

        {/* Global search with dropdown */}
        <div className="relative hidden xl:block" ref={searchRef}>
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 h-4 w-4" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            onFocus={() => { if (searchResults.length > 0) setShowSearchDropdown(true); }}
            className="glass-input text-xs py-1.5 pl-9 pr-4 rounded-full w-44 text-slate-700
                       placeholder:text-slate-400 focus:w-64 transition-all duration-300 outline-none"
            placeholder="全局搜索..."
            type="text"
          />
          {searchQuery && (
            <button
              onClick={() => { setSearchQuery(''); setSearchResults([]); setShowSearchDropdown(false); }}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="h-3.5 w-3.5" />
            </button>
          )}

          {/* Search results dropdown */}
          <AnimatePresence>
            {showSearchDropdown && (
              <motion.div
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -4 }}
                transition={{ duration: 0.15 }}
                className="absolute top-full left-0 right-0 mt-2 bg-white rounded-xl shadow-xl border border-slate-200 overflow-hidden z-50"
              >
                {searchLoading ? (
                  <div className="px-4 py-3 text-xs text-slate-400 flex items-center gap-2">
                    <div className="h-4 w-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
                    搜索中...
                  </div>
                ) : searchResults.length > 0 ? (
                  <div className="max-h-72 overflow-y-auto">
                    {searchResults.map((result, i) => (
                      <button
                        key={`${result.name}-${i}`}
                        onClick={() => {
                          setShowSearchDropdown(false);
                          setSearchQuery('');
                          onSearchChange?.('');
                          onScreenChange('registry');
                        }}
                        className="w-full flex items-start gap-3 px-4 py-3 hover:bg-slate-50 transition-colors text-left border-b border-slate-100 last:border-b-0"
                      >
                        <FileText className="h-4 w-4 text-indigo-400 mt-0.5 flex-shrink-0" />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2">
                            <span className="text-xs font-bold text-slate-800 truncate">{result.name}</span>
                            <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 font-semibold">{result.type}</span>
                          </div>
                          {result.description && (
                            <p className="text-[10px] text-slate-400 mt-0.5 truncate">{result.description}</p>
                          )}
                        </div>
                        <Clock className="h-3 w-3 text-slate-300 flex-shrink-0 mt-1" />
                      </button>
                    ))}
                  </div>
                ) : (
                  <div className="px-4 py-3 text-xs text-slate-400">未找到相关结果</div>
                )}
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* AI Chat button */}
        <button
          onClick={() => onScreenChange('chat')}
          className={`flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-full
                      transition-all duration-200 ${
            currentScreen === 'chat'
              ? 'bg-indigo-600 text-white shadow-sm ring-2 ring-indigo-300'
              : 'bg-indigo-500 text-white hover:bg-indigo-600 shadow-sm hover:shadow-indigo-200/50'
          }`}
        >
          <Sparkles className="h-3.5 w-3.5" />
          AI 助手
        </button>

        {/* Notifications */}
        <div ref={notificationRef} className="relative">
          <button
            onClick={() => setShowNotifications((v) => !v)}
            className="relative p-2 text-slate-400 hover:text-slate-700 hover:bg-slate-100 rounded-full transition-colors"
            title="通知"
          >
            <Bell className="h-4.5 w-4.5" />
            {unreadCount > 0 && (
              <span className="absolute top-1.5 right-1.5 h-2 w-2 rounded-full bg-rose-500 animate-pulse" />
            )}
          </button>

          <AnimatePresence>
            {showNotifications && (
              <motion.div
                key="notification-dropdown"
                initial={{ opacity: 0, y: -8, scale: 0.96 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, y: -8, scale: 0.96 }}
                transition={{ duration: 0.15 }}
                className="absolute right-0 top-full mt-2 w-80 bg-white rounded-xl border border-slate-200 shadow-xl z-50 overflow-hidden"
              >
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
                  <span className="text-sm font-semibold text-slate-700">通知</span>
                  {unreadCount > 0 && (
                    <button
                      onClick={handleMarkAllRead}
                      className="flex items-center gap-1 text-xs text-indigo-500 hover:text-indigo-700 transition-colors"
                    >
                      <Check className="h-3 w-3" />
                      全部已读
                    </button>
                  )}
                </div>

                {/* List */}
                <div className="max-h-72 overflow-y-auto">
                  {loadingNotifications ? (
                    <div className="flex items-center justify-center py-8 text-xs text-slate-400">
                      加载中...
                    </div>
                  ) : notifications.length === 0 ? (
                    <div className="flex items-center justify-center py-8 text-xs text-slate-400">
                      暂无新通知
                    </div>
                  ) : (
                    notifications.map((item) => (
                      <button
                        key={item.id}
                        onClick={() => handleMarkRead(item.id)}
                        className={`w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-slate-50 transition-colors border-b border-slate-50 last:border-0 ${
                          !item.read ? 'bg-indigo-50/40' : ''
                        }`}
                      >
                        {/* Unread dot */}
                        <div className="mt-1.5 flex-shrink-0">
                          {!item.read && (
                            <span className="block h-2 w-2 rounded-full bg-indigo-500" />
                          )}
                          {item.read && (
                            <span className="block h-2 w-2 rounded-full bg-slate-200" />
                          )}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center justify-between gap-2">
                            <span className="text-xs font-medium text-slate-700 truncate">
                              {item.title}
                            </span>
                            <span className="text-[10px] text-slate-400 flex-shrink-0">
                              {item.time}
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 mt-0.5 line-clamp-2 leading-relaxed">
                            {item.message}
                          </p>
                        </div>
                      </button>
                    ))
                  )}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Settings */}
        <button
          onClick={() => onScreenChange('settings')}
          className={`p-2 rounded-full transition-colors ${
            currentScreen === 'settings'
              ? 'text-indigo-600 bg-indigo-50'
              : 'text-slate-400 hover:text-slate-700 hover:bg-slate-100'
          }`}
          title="设置"
        >
          <Settings className="h-4.5 w-4.5" />
        </button>

        {/* User menu */}
        {session ? (
          <div className="flex items-center gap-2">
            <div className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-full bg-slate-100 border border-slate-200">
              {session.role === 'admin' ? (
                <ShieldCheck className="h-3.5 w-3.5 text-indigo-500" />
              ) : (
                <User className="h-3.5 w-3.5 text-slate-400" />
              )}
              <span className="text-xs font-medium text-slate-600 max-w-[120px] truncate">
                {session.username}
              </span>
            </div>
            <button
              onClick={onLogout}
              className="p-2 text-slate-400 hover:text-rose-600 hover:bg-rose-50 rounded-full transition-colors"
              title="退出登录"
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        ) : (
          <button
            onClick={() => onScreenChange('auth')}
            className="text-xs font-semibold text-white bg-indigo-500 px-4 py-2 rounded-full
                       hover:bg-indigo-600 transition-colors shadow-sm"
          >
            登录
          </button>
        )}
      </div>
    </nav>
  );
}
