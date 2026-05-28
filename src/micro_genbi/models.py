"""Micro-GenBI Pydantic 数据模型

定义系统内所有核心数据结构。
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional, Literal

from pydantic import BaseModel, Field, ConfigDict, computed_field


# =============================================================================
# 枚举定义
# =============================================================================

class QueryStatus(str, Enum):
    """查询状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class IntentType(str, Enum):
    """意图类型"""
    QUERY = "query"                    # 数据查询
    AGGREGATION = "aggregation"       # 聚合统计
    COMPARISON = "comparison"          # 对比分析
    TREND = "trend"                   # 趋势分析
    FILTER = "filter"                 # 条件筛选
    RANKING = "ranking"               # 排名
    UNKNOWN = "unknown"               # 未知


class ChartType(str, Enum):
    """图表类型"""
    AUTO = "auto"
    BAR = "bar"
    LINE = "line"
    PIE = "pie"
    SCATTER = "scatter"
    TABLE = "table"
    AREA = "area"
    HEATMAP = "heatmap"


class DatabaseType(str, Enum):
    """数据库类型"""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    CLICKHOUSE = "clickhouse"
    ORACLE = "oracle"
    SQLSERVER = "sqlserver"


class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


# =============================================================================
# 基础数据结构
# =============================================================================

class ColumnInfo(BaseModel):
    """列信息"""
    name: str = Field(..., description="列名")
    display_name: Optional[str] = Field(None, description="显示名称")
    data_type: str = Field(..., description="数据类型")
    description: Optional[str] = Field(None, description="列描述")
    nullable: bool = Field(True, description="是否可为空")
    primary_key: bool = Field(False, description="是否为主键")
    foreign_key: Optional[str] = Field(None, description="外键引用")

    model_config = ConfigDict(populate_by_name=True)


class TableInfo(BaseModel):
    """表信息"""
    name: str = Field(..., description="表名")
    display_name: Optional[str] = Field(None, description="显示名称")
    description: Optional[str] = Field(None, description="表描述")
    columns: list[ColumnInfo] = Field(default_factory=list, description="列列表")
    row_count: Optional[int] = Field(None, description="行数估算")

    model_config = ConfigDict(populate_by_name=True)

    @computed_field
    @property
    def column_names(self) -> list[str]:
        return [col.name for col in self.columns]


class DatabaseInfo(BaseModel):
    """数据库信息"""
    id: str = Field(..., description="数据库 ID")
    name: str = Field(..., description="数据库名称")
    display_name: Optional[str] = Field(None, description="显示名称")
    type: DatabaseType = Field(DatabaseType.POSTGRESQL, description="数据库类型")
    tables: list[TableInfo] = Field(default_factory=list, description="表列表")
    is_default: bool = Field(False, description="是否为默认数据库")

    model_config = ConfigDict(populate_by_name=True)


class RelationshipInfo(BaseModel):
    """表关系信息"""
    from_table: str = Field(..., description="源表")
    from_column: str = Field(..., description="源列")
    to_table: str = Field(..., description="目标表")
    to_column: str = Field(..., description="目标列")
    relationship_type: str = Field("many-to-one", description="关系类型")
    description: Optional[str] = Field(None, description="关系描述")


# =============================================================================
# Schema 相关
# =============================================================================

class SchemaConfig(BaseModel):
    """Schema 配置"""
    version: str = Field("1.0", description="配置版本")
    databases: list[DatabaseInfo] = Field(default_factory=list, description="数据库列表")
    relationships: list[RelationshipInfo] = Field(default_factory=list, description="表关系")
    table_aliases: dict[str, str] = Field(default_factory=dict, description="表别名映射")
    semantic_descriptions: dict[str, dict[str, Any]] = Field(
        default_factory=dict, description="语义描述"
    )


class SchemaResponse(BaseModel):
    """Schema API 响应"""
    databases: list[dict[str, Any]] = Field(default_factory=list, description="数据库列表")

    model_config = ConfigDict(populate_by_name=True)


class TableSummary(BaseModel):
    """表摘要信息"""
    name: str = Field(..., description="表名")
    display_name: str = Field(..., description="显示名称")
    description: Optional[str] = Field(None, description="表描述")
    columns: list[ColumnInfo] = Field(default_factory=list, description="列信息")
    sample_values: dict[str, Any] = Field(default_factory=dict, description="示例值")


# =============================================================================
# 查询相关
# =============================================================================

class QueryRequest(BaseModel):
    """查询请求"""
    query: str = Field(..., description="自然语言查询")
    project_id: Optional[str] = Field(None, description="项目 ID")
    connection_id: Optional[str] = Field(None, description="数据库连接 ID")
    session_id: Optional[str] = Field(None, description="会话 ID")
    user_id: Optional[str] = Field(None, description="用户 ID")
    role: Optional[str] = Field("user", description="用户角色")
    generate_chart: bool = Field(True, description="是否生成图表")
    chart_type: Optional[ChartType] = Field(None, description="强制图表类型")
    dialect: Optional[str] = Field(None, description="SQL 方言")
    timeout_seconds: int = Field(60, ge=1, le=300, description="超时秒数")
    max_rows: int = Field(1000, ge=1, le=10000, description="最大返回行数")


class QueryResponse(BaseModel):
    """查询响应"""
    sql: str = Field(..., description="生成的 SQL")
    data: list[dict[str, Any]] = Field(default_factory=list, description="查询结果")
    columns: list[ColumnInfo] = Field(default_factory=list, description="列信息")
    row_count: int = Field(0, description="返回行数")
    chart: Optional[dict[str, Any]] = Field(None, description="图表配置")
    summary: Optional[str] = Field(None, description="结果摘要")
    session_id: Optional[str] = Field(None, description="会话 ID")
    execution_time_ms: int = Field(0, description="执行耗时（毫秒）")
    steps_timing: dict[str, int] = Field(default_factory=dict, description="各步骤耗时")
    # 多库模式扩展
    query_mode: Optional[str] = Field(None, description="查询模式: single/aggregate/federated")
    query_mode_label: Optional[str] = Field(None, description="查询模式标签")
    query_mode_emoji: Optional[str] = Field(None, description="查询模式图标")
    query_mode_color: Optional[str] = Field(None, description="查询模式颜色")
    is_multi_db: bool = Field(False, description="是否为多库查询")
    sub_results: list[dict[str, Any]] = Field(
        default_factory=list, description="子查询结果列表（多库场景）"
    )
    rejected_reason: Optional[str] = Field(
        None, description="拒绝查询原因（配置缺失时）"
    )


class QueryResult(BaseModel):
    """查询结果（内部使用）"""
    sql: str = Field(..., description="SQL 语句")
    data: list[dict[str, Any]] = Field(default_factory=list, description="数据")
    columns: list[ColumnInfo] = Field(default_factory=list, description="列信息")
    row_count: int = Field(0, description="行数")
    intent: IntentType = Field(IntentType.QUERY, description="识别出的意图")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="置信度")
    tables_used: list[str] = Field(default_factory=list, description="使用的表")
    execution_time_ms: int = Field(0, description="执行耗时")
    error: Optional[str] = Field(None, description="错误信息")


# =============================================================================
# 异步任务相关
# =============================================================================

class TaskInfo(BaseModel):
    """任务信息"""
    task_id: str = Field(..., description="任务 ID")
    status: TaskStatus = Field(TaskStatus.PENDING, description="任务状态")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")

    model_config = ConfigDict(use_enum_values=True)


class TaskResult(BaseModel):
    """任务结果"""
    task_id: str = Field(..., description="任务 ID")
    status: TaskStatus = Field(..., description="最终状态")
    result: Optional[QueryResponse] = Field(None, description="查询结果")
    error: Optional[dict[str, Any]] = Field(None, description="错误信息")
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    current_step: Optional[str] = Field(None, description="当前步骤")


class TaskProgressEvent(BaseModel):
    """任务进度事件（SSE）"""
    event: str = Field(..., description="事件类型")
    step: Optional[str] = Field(None, description="步骤名称")
    progress: Optional[int] = Field(None, ge=0, le=100, description="进度")
    message: Optional[str] = Field(None, description="消息")
    timestamp: datetime = Field(default_factory=datetime.now)


# =============================================================================
# 意图分类
# =============================================================================

class IntentClassification(BaseModel):
    """意图分类结果"""
    intent: IntentType = Field(..., description="意图类型")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="置信度")
    reasoning: Optional[str] = Field(None, description="推理过程")
    suggested_aggregations: list[str] = Field(default_factory=list, description="建议的聚合函数")
    time_filter: Optional[str] = Field(None, description="时间过滤条件")


# =============================================================================
# 分析结果
# =============================================================================

class AnalysisResult(BaseModel):
    """分析结果"""
    type: str = Field(..., description="分析类型")
    summary: str = Field(..., description="分析摘要")
    findings: list[str] = Field(default_factory=list, description="关键发现")
    anomalies: list[dict[str, Any]] = Field(default_factory=list, description="异常数据")
    recommendations: list[str] = Field(default_factory=list, description="建议")


class ForecastResult(BaseModel):
    """预测结果"""
    metric: str = Field(..., description="预测指标")
    forecast_values: list[dict[str, Any]] = Field(default_factory=list, description="预测值")
    confidence_interval: tuple[float, float] = Field(..., description="置信区间")
    model_used: str = Field(..., description="使用的模型")
    accuracy_metrics: dict[str, float] = Field(default_factory=dict, description="准确度指标")


# =============================================================================
# 执行计划
# =============================================================================

class SubPlan(BaseModel):
    """子执行计划"""
    step: str = Field(..., description="步骤名称")
    sql: Optional[str] = Field(None, description="SQL 语句")
    database: Optional[str] = Field(None, description="目标数据库")
    dependencies: list[str] = Field(default_factory=list, description="依赖步骤")
    description: Optional[str] = Field(None, description="步骤描述")


class ExecutionPlan(BaseModel):
    """执行计划"""
    plans: list[SubPlan] = Field(default_factory=list, description="子计划列表")
    mode: str = Field("single", description="执行模式")
    estimated_time_ms: int = Field(0, description="预估耗时")


# =============================================================================
# 会话相关
# =============================================================================

class Message(BaseModel):
    """对话消息"""
    id: str = Field(..., description="消息 ID")
    role: Literal["user", "assistant", "system"] = Field(..., description="角色")
    content: str = Field(..., description="消息内容")
    sql: Optional[str] = Field(None, description="关联的 SQL")
    timestamp: datetime = Field(default_factory=datetime.now)


class Session(BaseModel):
    """会话"""
    id: str = Field(..., description="会话 ID")
    title: Optional[str] = Field(None, description="会话标题")
    messages: list[Message] = Field(default_factory=list, description="消息列表")
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")


# =============================================================================
# 用户与权限
# =============================================================================

class UserInfo(BaseModel):
    """用户信息"""
    id: str = Field(..., description="用户 ID")
    username: str = Field(..., description="用户名")
    email: Optional[str] = Field(None, description="邮箱")
    role: str = Field("user", description="角色")
    tenant_id: Optional[str] = Field(None, description="租户 ID")
    is_active: bool = Field(True, description="是否激活")


class Permission(BaseModel):
    """权限"""
    resource: str = Field(..., description="资源")
    actions: list[str] = Field(..., description="允许的操作")
    conditions: Optional[dict[str, Any]] = Field(None, description="附加条件")


# =============================================================================
# 健康检查
# =============================================================================

class HealthCheckResult(BaseModel):
    """健康检查结果"""
    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ..., description="健康状态"
    )
    latency_ms: Optional[int] = Field(None, description="延迟（毫秒）")
    message: Optional[str] = Field(None, description="状态消息")
    details: dict[str, Any] = Field(default_factory=dict, description="详细信息")


class SystemHealth(BaseModel):
    """系统健康状态"""
    status: Literal["healthy", "degraded", "unhealthy"] = Field(
        ..., description="整体状态"
    )
    timestamp: datetime = Field(default_factory=datetime.now)
    checks: dict[str, HealthCheckResult] = Field(default_factory=dict)
    version: str = Field("0.1.0", description="系统版本")


# =============================================================================
# 导出相关
# =============================================================================

class ExportRequest(BaseModel):
    """导出请求"""
    query_id: Optional[str] = Field(None, description="查询 ID")
    sql: Optional[str] = Field(None, description="SQL 语句")
    format: Literal["csv", "excel", "json", "sql", "pdf"] = Field("csv", description="导出格式")
    include_headers: bool = Field(True, description="是否包含表头")
    mask_sensitive: bool = Field(True, description="是否脱敏")
    max_rows: int = Field(10000, ge=1, le=100000, description="最大行数")


class ExportResponse(BaseModel):
    """导出响应"""
    export_id: str = Field(..., description="导出任务 ID")
    status: Literal["pending", "processing", "completed", "failed"] = Field(
        "pending", description="状态"
    )
    download_url: Optional[str] = Field(None, description="下载 URL")
    file_size: Optional[int] = Field(None, description="文件大小（字节）")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


# =============================================================================
# 审计日志
# =============================================================================

class AuditLogEntry(BaseModel):
    """审计日志条目"""
    id: str = Field(..., description="日志 ID")
    timestamp: datetime = Field(default_factory=datetime.now)
    event_type: str = Field(..., description="事件类型")
    user_id: Optional[str] = Field(None, description="用户 ID")
    tenant_id: Optional[str] = Field(None, description="租户 ID")
    ip_address: Optional[str] = Field(None, description="IP 地址")
    resource: str = Field(..., description="资源")
    action: str = Field(..., description="操作")
    result: Literal["success", "failed", "blocked"] = Field("success", description="结果")
    error_message: Optional[str] = Field(None, description="错误信息")
    metadata: dict[str, Any] = Field(default_factory=dict, description="元数据")
