/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

export type ScreenType = 'dashboard' | 'query' | 'registry' | 'reports' | 'chat' | 'admin' | 'settings' | 'health' | 'auth';

export type UserRole = 'user' | 'admin' | 'readonly';

export interface UserSession {
  id?: string;
  username: string;
  email: string;
  role: UserRole;
  group: string;
  subscriptionPlan: 'free' | 'pro' | 'enterprise';
  createdAt: string;
}

export interface LLMConfig {
  endpoint: string;
  apiKey: string;
  modelName: string;
  temperature: number;
  maxTokens: number;
}

export interface ManagedUser {
  id: string;
  username: string;
  email: string;
  role: UserRole;
  group: string;
  subscriptionPlan: 'free' | 'pro' | 'enterprise';
  status: 'active' | 'suspended';
  llmConfigured: boolean;
  totalCalls: number;
  lastCallTime: string;
}

export interface ManagedGroup {
  id: string;
  name: string;
  description: string;
  userCount: number;
  maxQuota: number; // e.g. monthly query limits
}

export interface UserMetricsOverview {
  userEmail: string;
  endpointUrl: string;
  latencyMs: number;
  callsCount: number;
  errorRate: number; // percentage
  status: 'online' | 'error' | 'throttled';
}


export interface DatabaseTable {
  name: string;
  type: string; // e.g. "dim_customers", "fct_orders", "fct_order_items", "fct_payments", "dim_currency"
  columns: {
    name: string;
    type: string;
    isPrimary?: boolean;
    isChecked?: boolean;
  }[];
}

export interface DatabaseSource {
  id: string;
  name: string;
  status: 'active' | 'syncing' | 'offline';
  tables: DatabaseTable[];
  type?: 'postgres' | 'mongodb' | 'redis' | 'snowflake';
}

export interface SystemStatus {
  name: string;
  latency: string;
  status: 'active' | 'syncing' | 'delayed' | 'offline';
}

export interface QueryPreset {
  id: string;
  title: string;
  time: string;
  description: string;
  selectedTable?: string;
}

export interface ChatMessage {
  id: string;
  sender: 'user' | 'assistant';
  timestamp: string;
  text: string;
  chartData?: {
    label: string;
    value: number;
    type: 'normal' | 'anomaly';
  }[];
}

export interface SchemaRegistryItem {
  virtualSchema: string;
  sourceNode: string;
  sourceEntity: string;
  type: string; // e.g., "物理表", "Collection", "虚拟视图"
}

export interface NodeStatus {
  id: string;
  name: string;
  status: 'online' | 'syncing' | 'offline';
  metadata: string; // e.g. "142 Tables · 4.2TB"
  logo: string; // e.g. image or symbol path
}
