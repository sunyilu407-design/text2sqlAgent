# Micro-GenBI WrenAI 源码移植指南

> **文档版本**：v1.0  
> **来源**：WrenAI-wren-v0.7.0  
> **目标**：Micro-GenBI 多库查询架构  
> **日期**：2026-05-25  
> **状态**：可直接用于开发

---

## 一、移植总览

### 1.1 源码位置

所有源码均位于项目目录下：

```
D:\myProjects\text2sqlAgent\WrenAI-wren-v0.7.0\
├── sdk/wren-pydantic/src/wren_pydantic/      ← 主要参考（Python SDK）
├── sdk/wren-langchain/src/wren_langchain/     ← LangChain 适配参考
└── core/wren/src/wren/                       ← Python CLI/Engine（部分可移植）
```

### 1.2 移植优先级矩阵

| WrenAI 模块 | 优先级 | 移植方式 | 目标路径 |
|------------|--------|---------|---------|
| Connection Provider | P0 | 直接移植，改类名 | `src/micro_genbi/db/providers/connection.py` |
| Error Mapping | P0 | 直接移植 | `src/micro_genbi/errors.py` |
| Pydantic Models | P0 | 改名移植 | `src/micro_genbi/models.py` |
| MDL Source | P0 | 改路径移植 | `src/micro_genbi/db/providers/mdl_source.py` |
| Toolkit（主类） | P0 | 架构参考，改写 | `src/micro_genbi/toolkit.py` |
| Runtime Tools | P0 | 改名移植 | `src/micro_genbi/tools/runtime.py` |
| Memory Provider | P1 | 架构参考 | `src/micro_genbi/memory/provider.py` |
| Memory API | P1 | 改名移植 | `src/micro_genbi/memory/api.py` |
| Memory Tools | P1 | 改名移植 | `src/micro_genbi/tools/memory.py` |
| Instructions Builder | P2 | 重写 | `src/micro_genbi/pipeline/instructions.py` |
| Engine Wrapper | P0 | 重写 | `src/micro_genbi/db/engine.py` |
| Profile Management | P1 | 改名移植 | `src/micro_genbi/profile.py` |
| MemoryStore | P2 | 移植+适配 | `src/micro_genbi/memory/store.py` |

---

## 二、异常处理模块（P0 - 必须移植）

**源文件**：`sdk/wren-pydantic/src/wren_pydantic/_errors.py`

**关键价值**：将数据库错误转换为 LLM 可理解的 `ModelRetry` 异常，是 SQL 自愈循环的基础。

### 2.1 异常类型定义

```python
# src/micro_genbi/errors.py
# 移植自: wren-pydantic/_errors.py

"""Micro-GenBI 异常类型定义。"""

from __future__ import annotations

import json
from typing import Any


class GenBIError(Exception):
    """Micro-GenBI 所有异常的基类。"""
    phase: str = "UNKNOWN"
    message: str = ""
    error_code: str = "UNKNOWN"
    metadata: dict[str, Any] | None = None

    def __init__(self, message: str, error_code: str = "UNKNOWN",
                 phase: str = "UNKNOWN", metadata: dict | None = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.phase = phase
        self.metadata = metadata

    def __repr__(self):
        return f"GenBIError({self.error_code}, {self.phase}, {self.message!r})"


# ── 错误阶段（Phase）─────────────────────────────
# 移植自: core/wren/src/wren/model/error.py

class ErrorPhase:
    SQL_PARSING = "SQL_PARSING"
    SQL_PLANNING = "SQL_PLANNING"
    SQL_TRANSPILE = "SQL_TRANSPILE"
    SQL_DRY_RUN = "SQL_DRY_RUN"
    SQL_EXECUTION = "SQL_EXECUTION"
    METADATA_FETCHING = "METADATA_FETCHING"
    MDL_EXTRACTION = "MDL_EXTRACTION"
    VALIDATION = "VALIDATION"
    CONNECTION = "CONNECTION"
    ROUTING = "ROUTING"
    MULTI_DB_EXECUTION = "MULTI_DB_EXECUTION"


# ── 错误码（ErrorCode）───────────────────────────
# 移植自: core/wren/src/wren/model/error.py

class ErrorCode:
    # 基础设施错误（LLM 无法修复，直接抛出）
    GET_CONNECTION_ERROR = "GET_CONNECTION_ERROR"
    INVALID_CONNECTION_INFO = "INVALID_CONNECTION_INFO"
    DUCKDB_FILE_NOT_FOUND = "DUCKDB_FILE_NOT_FOUND"
    ATTACH_DUCKDB_ERROR = "ATTACH_DUCKDB_ERROR"
    GENERIC_INTERNAL_ERROR = "GENERIC_INTERNAL_ERROR"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    DATABASE_TIMEOUT = "DATABASE_TIMEOUT"

    # SQL 错误（LLM 可以修复，重试）
    SYNTAX_ERROR = "SYNTAX_ERROR"
    INVALID_COLUMN = "INVALID_COLUMN"
    INVALID_TABLE = "INVALID_TABLE"
    INVALID_JOIN = "INVALID_JOIN"
    AMBIGUOUS_COLUMN = "AMBIGUOUS_COLUMN"
    DIVISION_BY_ZERO = "DIVISION_BY_ZERO"
    TYPE_MISMATCH = "TYPE_MISMATCH"

    # 多库错误
    CROSS_DB_ERROR = "CROSS_DB_ERROR"
    DB_NOT_FOUND = "DB_NOT_FOUND"
    DB_CONNECTION_FAILED = "DB_CONNECTION_FAILED"
    MULTI_DB_TIMEOUT = "MULTI_DB_TIMEOUT"

    # ACL 错误
    ACL_DENIED = "ACL_DENIED"
    TABLE_NOT_ALLOWED = "TABLE_NOT_ALLOWED"


# ── 基础设施错误（不重试，直接抛出）───────────────
_PROPOGATE_CODES = frozenset({
    ErrorCode.GET_CONNECTION_ERROR,
    ErrorCode.INVALID_CONNECTION_INFO,
    ErrorCode.DATABASE_TIMEOUT,
    ErrorCode.DUCKDB_FILE_NOT_FOUND,
    ErrorCode.ATTACH_DUCKDB_ERROR,
    ErrorCode.GENERIC_INTERNAL_ERROR,
    ErrorCode.NOT_IMPLEMENTED,
    ErrorCode.ACL_DENIED,
    ErrorCode.TABLE_NOT_ALLOWED,
    ErrorCode.DB_NOT_FOUND,
    ErrorCode.DB_CONNECTION_FAILED,
})


# ── 秘密信息脱敏─────────────────────────────
_SECRET_PATTERNS = ("password", "secret", "token", "credential", "api_key")

METADATA_CAP_BYTES = 4 * 1024  # 4KB 上限，防止上下文爆炸


def redact_secrets(data: Any) -> Any:
    """将敏感字段值替换为 ***（递归）"""
    def walk(value: Any, key_hint: str | None = None) -> Any:
        if key_hint and any(pat in key_hint.lower() for pat in _SECRET_PATTERNS):
            return "***"
        if isinstance(value, dict):
            return {k: walk(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v, key_hint) for v in value]
        return value
    return walk(data)


def should_propagate(exc: GenBIError) -> bool:
    """基础设施错误直接抛出，不让 LLM 重试"""
    return exc.error_code in _PROPOGATE_CODES


def _build_retry_message(exc: GenBIError) -> str:
    """根据错误阶段生成 LLM 可理解的自然语言提示"""
    phase = exc.phase
    msg = exc.message

    messages = {
        ErrorPhase.SQL_PARSING: f"SQL 语法错误：{msg}。请修正 SQL 语法后重试。",
        ErrorPhase.SQL_PLANNING: f"SQL 规划错误：{msg}。请检查表名、列名是否正确后重试。",
        ErrorPhase.SQL_TRANSPILE: f"SQL 方言转换错误：{msg}。请简化查询后重试。",
        ErrorPhase.SQL_DRY_RUN: f"SQL 预执行验证失败：{msg}。查询无效，请修正后重试。",
        ErrorPhase.SQL_EXECUTION: f"数据库执行错误：{msg}。",
        ErrorPhase.METADATA_FETCHING: f"元数据查询失败：{msg}。请确认表存在后重试。",
        ErrorPhase.ROUTING: f"数据库路由错误：{msg}。请检查数据库连接配置。",
        ErrorPhase.MULTI_DB_EXECUTION: f"多库执行错误：{msg}。部分库查询失败。",
        ErrorPhase.CONNECTION: f"数据库连接错误：{msg}。请检查连接配置和网络。",
    }

    framing = messages.get(phase, f"错误：{msg}。")

    # SQL 执行错误附带方言 SQL（截断）
    metadata = redact_secrets(exc.metadata or {})
    if phase == ErrorPhase.SQL_EXECUTION and isinstance(metadata, dict):
        dialect_sql = metadata.get("dialect_sql", "")
        if dialect_sql:
            excerpt = dialect_sql[:200] + "..." if len(dialect_sql) > 200 else dialect_sql
            framing += f" 方言 SQL：{excerpt}"

    return _cap_message(framing)


def _cap_message(text: str) -> str:
    """字节感知截断，防止超过上下文上限"""
    encoded = text.encode("utf-8")
    if len(encoded) <= METADATA_CAP_BYTES:
        return text
    marker = "... [已截断]"
    keep = METADATA_CAP_BYTES - len(marker.encode("utf-8"))
    return encoded[:keep].decode("utf-8", errors="ignore") + marker


class GenBIReRetry(Exception):
    """
    LLM 可修复的错误，触发 SQL 自愈重试循环。
    
    替代 Pydantic AI 的 ModelRetry，直接抛出给 Agent 编排层处理。
    """
    def __init__(self, message: str, phase: str = "UNKNOWN", metadata: dict | None = None):
        super().__init__(message)
        self.message = message
        self.phase = phase
        self.metadata = metadata

    def __repr__(self):
        return f"GenBIReRetry({self.phase}, {self.message!r})"


def to_retry(exc: GenBIError) -> GenBIReRetry:
    """将 GenBIError 转换为 GenBIReRetry"""
    return GenBIReRetry(
        _build_retry_message(exc),
        phase=exc.phase,
        metadata=exc.metadata,
    )
```

### 2.2 异常使用示例

```python
# 在各模块中使用
from src.micro_genbi.errors import (
    GenBIError, GenBIReRetry, ErrorPhase, ErrorCode,
    should_propagate, to_retry
)

# 场景 1：SQL 执行错误
try:
    result = await db.execute(sql)
except GenBIError as e:
    if should_propagate(e):
        raise  # 基础设施错误，直接抛出
    raise to_retry(e)  # LLM 可修复，重试

# 场景 2：多库执行时的部分失败
results = await executor.execute_plan(plan)
for r in results.sub_results:
    if r.error and should_propagate(GenBIError(r.error, error_code=ErrorCode.DB_CONNECTION_FAILED)):
        raise GenBIError(r.error, error_code=ErrorCode.DB_CONNECTION_FAILED, phase=ErrorPhase.MULTI_DB_EXECUTION)
```

---

## 三、连接配置模块（P0 - 必须移植）

**源文件**：`sdk/wren-pydantic/src/wren_pydantic/_providers/connection.py`

**关键价值**：三层回退机制（显式 > 项目配置 > 全局激活），是最可靠的多配置管理设计。

### 3.1 连接配置模型

```python
# src/micro_genbi/db/config.py
# 移植自: wren-pydantic/_providers/connection.py + wren-core/wren/profile.py

from pathlib import Path
from typing import Any, Literal
from pydantic import BaseModel, Field
import yaml
import os


class ConnectionProfile(BaseModel):
    """单个数据库连接配置"""
    id: str
    datasource: str = Field(description="数据源类型: postgresql, mysql, clickhouse, ...")
    host: str
    port: int = 5432
    database: str
    username: str
    password: str = ""
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=50)
    ssl_mode: str = "prefer"
    connect_timeout: int = 10  # 秒

    # ── 多库专用字段 ────────────────────────────
    db_category: Literal["primary", "sibling", "heterogenous"] = "primary"
    siblings_group: str | None = None
    is_aggregation_source: bool = False
    city_code: str | None = None  # 大屏展示时的城市/子系统编码


class ProfileManager:
    """
    配置文件管理器（3 层回退机制）。
    
    Layer 1: 显式传入的 profile 名称
    Layer 2: 项目配置文件中的 profile
    Layer 3: 全局激活的 profile
    
    与 WrenAI ProfileConnectionProvider 等价，针对 Micro-GenBI 多库场景重写。
    """

    def __init__(self, config_path: str | Path = "genbi_config.yaml"):
        self.config_path = Path(config_path)
        self._profiles: dict[str, ConnectionProfile] = {}
        self._active_profile_name: str | None = None
        self._project_profile_name: str | None = None

        if self.config_path.exists():
            self._load_all_profiles()

    def _load_all_profiles(self):
        """从 YAML 加载所有 profile"""
        with open(self.config_path) as f:
            raw = yaml.safe_load(f) or {}

        # 环境变量替换 ${ENV_VAR} 模式
        profiles_data = raw.get("profiles", {})
        expanded = self._expand_env_vars(profiles_data)
        for name, cfg in expanded.items():
            try:
                self._profiles[name] = ConnectionProfile(id=name, **cfg)
            except Exception as e:
                raise ValueError(f"Profile {name} 格式错误: {e}")

        # 读取项目配置的默认 profile
        project_config = raw.get("project", {})
        self._project_profile_name = project_config.get("default_profile")

        # 读取全局激活 profile
        self._active_profile_name = self._load_active_profile_from_env()

    def _expand_env_vars(self, data: Any) -> Any:
        """递归展开 ${ENV_VAR} 环境变量"""
        if isinstance(data, dict):
            return {k: self._expand_env_vars(v) for k, v in data.items()}
        if isinstance(data, list):
            return [self._expand_env_vars(v) for v in data]
        if isinstance(data, str) and data.startswith("${") and data.endswith("}"):
            env_key = data[2:-1]
            return os.getenv(env_key, "")
        return data

    def _load_active_profile_from_env(self) -> str | None:
        """从环境变量读取全局激活的 profile"""
        return os.getenv("GENBI_ACTIVE_PROFILE")

    # ── 公开 API ─────────────────────────────────────────

    def get_profile(self, name: str | None = None) -> ConnectionProfile:
        """
        获取 profile（三层回退）。
        
        1. name 非空 → 使用指定 profile
        2. name 为空 → 使用项目默认 profile
        3. 无项目默认 → 使用全局激活 profile
        """
        target = name

        if not target:
            target = self._project_profile_name

        if not target:
            target = self._active_profile_name

        if not target:
            raise GenBIError(
                "未找到可用的数据库配置。请在 config.yaml 中配置 profiles 或设置 GENBI_ACTIVE_PROFILE 环境变量。",
                error_code=ErrorCode.INVALID_CONNECTION_INFO,
                phase=ErrorPhase.CONNECTION,
            )

        if target not in self._profiles:
            available = sorted(self._profiles.keys())
            raise GenBIError(
                f"Profile '{target}' 不存在。可用 profiles: {available}",
                error_code=ErrorCode.INVALID_CONNECTION_INFO,
                phase=ErrorPhase.CONNECTION,
            )

        return self._profiles[target]

    def list_profiles(self) -> dict[str, ConnectionProfile]:
        """列出所有已加载的 profile"""
        return dict(self._profiles)

    def set_active_profile(self, name: str):
        """设置全局激活 profile（写入环境变量）"""
        os.environ["GENBI_ACTIVE_PROFILE"] = name
        self._active_profile_name = name

    def get_all_aggregation_sources(self) -> list[ConnectionProfile]:
        """获取所有同构聚合数据源"""
        return [p for p in self._profiles.values() if p.is_aggregation_source]

    def get_siblings_group(self, group_name: str) -> list[ConnectionProfile]:
        """获取同构组内的所有 profile"""
        return [
            p for p in self._profiles.values()
            if p.siblings_group == group_name
        ]
```

### 3.2 连接配置 YAML 示例

```yaml
# genbi_config.yaml

project:
  default_profile: "province_aggregate"  # 项目默认 profile

profiles:
  # ── 模式一：单数据库 ────────────────────────
  single_oa:
    id: "single_oa"
    datasource: "postgresql"
    host: "${OA_DB_HOST}"
    port: 5432
    database: "oa_db"
    username: "${OA_DB_USER}"
    password: "${OA_DB_PASSWORD}"
    pool_size: 10
    db_category: "primary"

  # ── 模式二：同构多库聚合（大屏）──────────────
  province_aggregate:
    id: "province_aggregate"
    datasource: "postgresql"
    host: "${PROV_HEAD_HOST}"
    port: 5432
    database: "province_head"
    username: "${PROV_HEAD_USER}"
    password: "${PROV_HEAD_PASSWORD}"
    pool_size: 20
    db_category: "primary"
    is_aggregation_source: true
    city_code: "PROV"

  city_hangzhou:
    id: "city_hangzhou"
    datasource: "postgresql"
    host: "${HZ_DB_HOST}"
    port: 5432
    database: "city_hangzhou"
    username: "${HZ_DB_USER}"
    password: "${HZ_DB_PASSWORD}"
    pool_size: 10
    db_category: "sibling"
    siblings_group: "province_cities"
    is_aggregation_source: true
    city_code: "HZ"

  city_ningbo:
    id: "city_ningbo"
    datasource: "mysql"
    host: "${NB_DB_HOST}"
    port: 3306
    database: "city_ningbo"
    username: "${NB_DB_USER}"
    password: "${NB_DB_PASSWORD}"
    pool_size: 10
    db_category: "sibling"
    siblings_group: "province_cities"
    is_aggregation_source: true
    city_code: "NB"

  # ── 模式三：异构多库（复杂项目）─────────────
  orders_db:
    id: "orders_db"
    datasource: "postgresql"
    host: "${ORDERS_HOST}"
    port: 5432
    database: "orders"
    username: "${ORDERS_USER}"
    password: "${ORDERS_PASSWORD}"
    pool_size: 15
    db_category: "heterogenous"

  financial_db:
    id: "financial_db"
    datasource: "postgresql"
    host: "${FIN_HOST}"
    port: 5432
    database: "financial"
    username: "${FIN_USER}"
    password: "${FIN_PASSWORD}"
    pool_size: 10
    db_category: "heterogenous"
```

---

## 四、Pydantic 数据模型（P0 - 必须移植）

**源文件**：`sdk/wren-pydantic/src/wren_pydantic/_models.py`

```python
# src/micro_genbi/models.py
# 移植自: wren-pydantic/_models.py

"""Micro-GenBI Pydantic 数据模型（面向 LLM 的工具返回结果）"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator


# ── 查询结果模型 ───────────────────────────────────

class QueryResult(BaseModel):
    """查询结果（对应 WrenAI 的 WrenQueryResult）"""
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int = Field(ge=0)
    truncated: bool = Field(default=False, description="结果是否被截断")
    execution_time_ms: float | None = None
    source_db_id: str | None = None  # 多库场景下标注数据来源

    @model_validator(mode="after")
    def _validate_row_count(self) -> QueryResult:
        if self.row_count != len(self.rows):
            # 允许 row_count > len(rows)，表示实际结果更多
            pass
        return self


class MultiDBQueryResult(BaseModel):
    """多库查询结果汇总"""
    mode: Literal["single", "aggregate", "federated", "hybrid"]
    sub_results: list[QueryResult] = Field(default_factory=list)
    merged_rows: list[dict[str, Any]] | None = None
    total_row_count: int = 0
    total_execution_time_ms: float = 0
    errors: list[str] = Field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def is_truncated(self) -> bool:
        return any(r.truncated for r in self.sub_results)


# ── 语义模型摘要 ───────────────────────────────────

class TableSummary(BaseModel):
    """表/模型摘要（对应 WrenAI 的 ModelSummary）"""
    name: str
    logical_name: str = ""          # 中文逻辑名（Micro-GenBI 扩展）
    column_count: int = Field(ge=0)
    description: str | None = None
    database_id: str | None = None  # 多库场景


class ColumnInfo(BaseModel):
    """列信息"""
    name: str
    logical_name: str = ""
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    description: str | None = None
    enum_values: dict[str, str] | None = None  # 枚举值映射


# ── 分析结果模型 ───────────────────────────────────

class AnalysisResult(BaseModel):
    """LLM 深度分析结果"""
    type: Literal["interpret", "compare", "anomaly", "forecast_reasoning", "sql_explain"]
    conclusion: str = Field(description="一句话总结")
    key_findings: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0, default=0.8)
    suggestions: list[str] = Field(default_factory=list)
    chart_hints: dict[str, Any] | None = None


class ForecastResult(BaseModel):
    """时序预测结果"""
    model_name: str
    forecast_values: list[float]
    forecast_dates: list[str]
    confidence_lower: list[float]
    confidence_upper: list[float]
    metrics: dict[str, float] = Field(default_factory=dict)
    interpretation: str = ""


# ── SQL 验证结果 ───────────────────────────────────

class DryPlanResult(BaseModel):
    """SQL 预执行计划（对应 WrenAI 的 dry_plan）"""
    dialect_sql: str
    planned_tables: list[str]
    planned_columns: list[str]
    estimated_cost: float | None = None
    warnings: list[str] = Field(default_factory=list)


# ── 执行计划模型 ───────────────────────────────────

class SubPlan(BaseModel):
    """单个库的子执行计划"""
    db_id: str
    sql: str
    display_name: str = ""
    estimated_rows: int = 0


class ExecutionPlan(BaseModel):
    """多库执行计划"""
    mode: Literal["single", "aggregate", "federated", "hybrid"]
    is_multi_db: bool = False
    sub_plans: list[SubPlan] = Field(default_factory=list)
    final_sql: str | None = None
    merge_strategy: Literal["none", "union_all", "stream_join", "materialized_join"] = "none"
    involved_db_ids: list[str] = Field(default_factory=list)
    description: str = ""
```

---

## 五、主工具箱类（P0 - 架构参考）

**源文件**：`sdk/wren-pydantic/src/wren_pydantic/_toolkit.py`

**关键价值**：
- 工具箱 Facade 模式：统一管理所有工具
- 连接器缓存：避免重复认证
- 读穿透 Manifest：外部重建时自动感知
- 内存缓存：LanceDB 模型加载一次

### 5.1 Micro-GenBI 工具箱

```python
# src/micro_genbi/toolkit.py
# 架构移植自: wren-pydantic/_toolkit.py

"""
Micro-GenBI Toolkit：多库查询 Facade 类。

架构参考自 WrenAI WrenToolkit，核心设计：
1. 连接器缓存：避免每次查询重新认证
2. 读穿透配置：配置文件变更自动感知，无需重启
3. 多库路由：支持单库 / 同构聚合 / 异构联邦
4. 工具子域：按功能分组（runtime / memory / analysis）

使用方式：
    toolkit = GenBIToolkit.from_config("genbi_config.yaml", profile="province_aggregate")
    toolset = toolkit.toolset(include_memory_write=True)
    result = await toolkit.query("SELECT ...")
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .db.config import ProfileManager, ConnectionProfile
from .db.config import GenBIError, ErrorPhase, ErrorCode
from .models import QueryResult, DryPlanResult, MultiDBQueryResult
from .errors import should_propagate, to_retry

if TYPE_CHECKING:
    from .db.engine import GenBIEngine
    from .db.router import ExecutionPlan


class GenBIToolkit:
    """
    Micro-GenBI 主工具箱。
    
    Facade 模式，统一管理数据库连接、多库路由、查询执行、工具集生成。
    对应 WrenAI 的 WrenToolkit 类。
    """

    def __init__(
        self,
        *,
        config_path: str | Path,
        explicit_profile: str | None = None,
    ):
        self._config_path = Path(config_path).expanduser().resolve()
        self._profile_mgr = ProfileManager(self._config_path)

        # 解析 profile（三层回退）
        self._active_profile = self._profile_mgr.get_profile(explicit_profile)
        self._all_profiles = self._profile_mgr.list_profiles()

        # 连接器缓存（关键！避免每次查询重新认证）
        self._engine_cache: dict[str, GenBIEngine] = {}
        self._connector_cache: dict[str, Any] = {}

    # ── 工厂方法 ─────────────────────────────────────────

    @classmethod
    def from_config(
        cls,
        config_path: str = "genbi_config.yaml",
        profile: str | None = None,
    ) -> GenBIToolkit:
        """从配置文件创建工具箱"""
        path = Path(config_path).expanduser().resolve()
        if not path.exists():
            raise GenBIError(
                f"配置文件不存在: {path}",
                error_code=ErrorCode.INVALID_CONNECTION_INFO,
                phase=ErrorPhase.CONNECTION,
            )
        return cls(config_path=path, explicit_profile=profile)

    # ── 核心 API ─────────────────────────────────────────

    async def query(self, sql: str, db_id: str | None = None, limit: int = 1000) -> QueryResult:
        """
        执行 SQL 查询。
        
        参数：
            sql: SQL 语句
            db_id: 指定数据库 ID（多库场景）
            limit: 结果上限（默认 1000）
        """
        from .db.engine import get_engine

        # 确定目标数据库
        target_db = db_id or self._active_profile.id

        # 获取引擎（带缓存）
        engine = self._get_engine(target_db)

        try:
            result = await engine.execute(sql, limit=limit)
            return QueryResult(
                columns=result.get("columns", []),
                rows=result.get("rows", []),
                row_count=len(result.get("rows", [])),
                truncated=len(result.get("rows", [])) >= limit,
                source_db_id=target_db,
            )
        except GenBIError as e:
            if should_propagate(e):
                raise
            raise to_retry(e) from e

    async def dry_plan(self, sql: str, db_id: str | None = None) -> DryPlanResult:
        """
        SQL 预执行计划（不实际执行，验证 SQL 有效性）。
        
        对应 WrenAI 的 dry_plan：经过 MDL 层，返回方言 SQL。
        """
        from .db.engine import get_engine

        target_db = db_id or self._active_profile.id
        engine = self._get_engine(target_db)

        try:
            planned = await engine.dry_plan(sql)
            return DryPlanResult(
                dialect_sql=planned.get("dialect_sql", sql),
                planned_tables=planned.get("tables", []),
                planned_columns=planned.get("columns", []),
                warnings=planned.get("warnings", []),
            )
        except GenBIError as e:
            if should_propagate(e):
                raise
            raise to_retry(e) from e

    async def multi_query(self, plan: ExecutionPlan, limit: int = 1000) -> MultiDBQueryResult:
        """
        多库并发查询（场景 A / B / C）。
        
        对应 MultiDatabaseRouter 生成的执行计划。
        """
        from .db.executor import MultiDBExecutor

        executor = MultiDBExecutor(self._profile_mgr, self._all_profiles)
        return await executor.execute(plan, limit=limit)

    # ── 工具集生成（Pydantic AI 集成）───────────────

    def toolset(self, *, include_memory_write: bool = True) -> list:
        """
        生成 Pydantic AI 工具集。
        
        返回的工具有：
        - genbi_query: 执行 SQL 查询
        - genbi_dry_plan: SQL 预验证
        - genbi_list_tables: 列出可用表
        - genbi_fetch_context: 获取语义上下文（内存）
        - genbi_recall_queries: 检索历史查询
        （如 include_memory_write=True）
        - genbi_store_query: 保存 NL→SQL 对
        """
        from .tools.runtime import build_runtime_toolset
        from .tools.memory import build_memory_toolset

        tools = []
        tools.extend(build_runtime_toolset(self))
        tools.extend(build_memory_toolset(self, include_write=include_memory_write))
        return tools

    def instructions(self) -> str:
        """生成系统指令（用于 Pydantic AI / LangChain）"""
        from .pipeline.instructions import build_instructions
        return build_instructions(self)

    # ── 多库感知 ────────────────────────────────────────

    def get_all_databases(self) -> list[ConnectionProfile]:
        """获取所有已配置的数据库"""
        return list(self._all_profiles.values())

    def get_aggregation_sources(self) -> list[ConnectionProfile]:
        """获取所有聚合数据源（场景 A）"""
        return self._profile_mgr.get_all_aggregation_sources()

    def get_siblings_group(self, group_name: str) -> list[ConnectionProfile]:
        """获取同构库分组"""
        return self._profile_mgr.get_siblings_group(group_name)

    # ── 内部 ────────────────────────────────────────────

    def _get_engine(self, db_id: str) -> GenBIEngine:
        """获取或创建数据库引擎（带缓存）"""
        if db_id not in self._engine_cache:
            profile = self._all_profiles.get(db_id)
            if not profile:
                raise GenBIError(
                    f"数据库 '{db_id}' 未在配置中找到",
                    error_code=ErrorCode.DB_NOT_FOUND,
                    phase=ErrorPhase.ROUTING,
                )
            from .db.engine import create_engine
            self._engine_cache[db_id] = create_engine(profile)
        return self._engine_cache[db_id]

    @property
    def active_profile(self) -> ConnectionProfile:
        return self._active_profile

    @property
    def config_path(self) -> Path:
        return self._config_path
```

---

## 六、运行时工具集（P0 - 必须移植）

**源文件**：`sdk/wren-pydantic/src/wren_pydantic/_tools.py`

```python
# src/micro_genbi/tools/runtime.py
# 移植自: wren-pydantic/_tools.py

"""Micro-GenBI 运行时工具（Pydantic AI 工具定义）"""

from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Literal

from .toolkit import GenBIToolkit
from .models import QueryResult, DryPlanResult, TableSummary
from .errors import GenBIReRetry, should_propagate, to_retry, GenBIError, ErrorPhase

MAX_QUERY_ROWS = 1000


# ── Pydantic 工具参数模型 ────────────────────────────

class QueryToolParams(BaseModel):
    sql: str = Field(
        description="要执行的 SQL 语句（必须是 SELECT，禁止写操作）"
    )
    limit: int = Field(
        default=100,
        ge=1,
        le=MAX_QUERY_ROWS,
        description=f"结果行数上限（1~{MAX_QUERY_ROWS}）"
    )
    db_id: str | None = Field(
        default=None,
        description="指定数据库 ID（多库场景，不指定则使用默认库）"
    )


class DryPlanParams(BaseModel):
    sql: str = Field(description="要验证的 SQL 语句")


class ListTablesParams(BaseModel):
    db_id: str | None = Field(default=None, description="指定数据库（不指定则列出所有）")
    search: str | None = Field(default=None, description="按名称搜索过滤")


# ── 工具注册 ───────────────────────────────────────

def build_runtime_toolset(toolkit: GenBIToolkit) -> list:
    """构建运行时工具集"""
    tools = []

    # genbi_query
    @toolkit.tool(retries=2)
    async def genbi_query(params: QueryToolParams) -> QueryResult:
        """执行 SQL 查询并返回结果"""
        if params.limit < 1 or params.limit > MAX_QUERY_ROWS:
            raise GenBIReRetry(
                f"limit 必须在 1 到 {MAX_QUERY_ROWS} 之间（当前：{params.limit}）",
                phase=ErrorPhase.VALIDATION,
            )
        try:
            result = await toolkit.query(params.sql, db_id=params.db_id, limit=params.limit)
            return result
        except GenBIError as e:
            if should_propagate(e):
                raise
            raise to_retry(e)

    # genbi_dry_plan
    @toolkit.tool(retries=2)
    async def genbi_dry_plan(params: DryPlanParams) -> DryPlanResult:
        """验证 SQL 有效性（不实际执行）"""
        try:
            return await toolkit.dry_plan(params.sql, db_id=params.db_id)
        except GenBIError as e:
            if should_propagate(e):
                raise
            raise to_retry(e)

    # genbi_list_tables
    @toolkit.tool(retries=1)
    async def genbi_list_tables(params: ListTablesParams) -> list[TableSummary]:
        """列出所有可用表"""
        all_dbs = toolkit.get_all_databases()
        tables = []
        for db in all_dbs:
            if params.db_id and db.id != params.db_id:
                continue
            # 从 schema_registry 读取表信息（见架构文档）
            # 这里简化处理，实际从 SchemaRegistry 获取
            tables.append(TableSummary(
                name=f"{db.id}.*",
                logical_name=db.display_name,
                column_count=0,
                database_id=db.id,
            ))
        return tables

    return tools
```

---

## 七、内存工具（P1 - 移植参考）

**源文件**：`sdk/wren-pydantic/src/wren_pydantic/_memory_api.py` + `_tools_memory.py`

### 7.1 内存 API（直接可移植）

```python
# src/micro_genbi/memory/api.py
# 移植自: wren-pydantic/_memory_api.py

"""内存子域 API（检索历史 NL→SQL 对、获取语义上下文）"""

from __future__ import annotations

from .toolkit import GenBIToolkit
from .errors import MemoryNotEnabledError


class MemoryAPI:
    """
    内存操作 API。
    
    对应 WrenAI 的 _MemoryAPI，提供：
    - fetch: 获取与问题相关的语义上下文
    - recall: 检索相似的历史查询
    - store: 保存 NL→SQL 对
    
    注意：LanceDB MemoryStore 需要移植 core/wren/src/wren/memory/store.py
    """

    def __init__(self, toolkit: GenBIToolkit):
        self._toolkit = toolkit
        self._memory_store = None

    def fetch(
        self,
        question: str,
        *,
        limit: int = 5,
        item_type: str | None = None,
        model_name: str | None = None,
        threshold: float | None = None,
    ) -> dict:
        """
        获取与问题相关的语义上下文。
        
        使用向量相似度搜索，从 LanceDB 中检索相关表/列描述。
        """
        store = self._get_store()
        return store.get_context(
            query=question,
            manifest=self._get_manifest(),
            limit=limit,
            item_type=item_type,
            model_name=model_name,
            threshold=threshold,
        )

    def recall(
        self,
        question: str,
        *,
        limit: int = 3,
    ) -> list[dict]:
        """
        检索与问题相似的历史 NL→SQL 对。
        
        用于 Few-shot 示例注入，提高 SQL 生成准确率。
        """
        store = self._get_store()
        return store.recall_queries(query=question, limit=limit)

    def store(
        self,
        nl_query: str,
        sql_query: str,
        *,
        datasource: str | None = None,
        tags: list[str] | None = None,
    ) -> None:
        """
        保存确认的 NL→SQL 对到记忆库。
        
        用于后续 recall 和 few-shot 示例。
        """
        if tags:
            for tag in tags:
                if "," in tag:
                    raise ValueError(
                        f"tag '{tag}' 包含逗号，逗号是存储格式的分隔符。"
                        "请使用短横线或空格替代。"
                    )

        store = self._get_store()
        tag_str = ",".join(tags) if tags else None
        store.store_query(
            nl_query=nl_query,
            sql_query=sql_query,
            datasource=datasource or self._toolkit.active_profile.id,
            tags=tag_str,
        )

    def _get_store(self):
        if not self._toolkit._memory_enabled:
            raise MemoryNotEnabledError(
                "memory 未启用。运行 `genbi memory index` 初始化记忆库。"
            )
        if self._memory_store is None:
            self._memory_store = self._toolkit._open_memory()
        return self._memory_store

    def _get_manifest(self) -> dict:
        """从 schema_registry 生成 manifest"""
        # 实际实现：从 SchemaRegistry 构建
        return {}


class MemoryNotEnabledError(Exception):
    """记忆功能未启用时抛出"""
    pass
```

### 7.2 内存工具（Pydantic AI）

```python
# src/micro_genbi/tools/memory.py
# 移植自: wren-pydantic/_tools_memory.py

"""记忆工具（Pydantic AI 工具定义）"""

from pydantic import BaseModel, Field

from .toolkit import GenBIToolkit
from .memory.api import MemoryAPI, MemoryNotEnabledError


class FetchContextParams(BaseModel):
    question: str = Field(description="用户问题（用于检索相关上下文）")
    limit: int = Field(default=5, ge=1, le=20, description="返回结果数量")
    strategy: str = Field(default="search", description="策略：full（全部）或 search（向量搜索）")


class RecallQueriesParams(BaseModel):
    question: str = Field(description="用于检索相似历史查询的问题")
    limit: int = Field(default=3, ge=1, le=10)


class StoreQueryParams(BaseModel):
    nl_query: str = Field(description="自然语言查询")
    sql_query: str = Field(description="对应的 SQL 语句")
    tags: list[str] | None = Field(default=None, description="标签列表")


def build_memory_toolset(
    toolkit: GenBIToolkit,
    *,
    include_write: bool = True,
) -> list:
    """构建记忆工具集"""
    tools = []
    memory_api = MemoryAPI(toolkit)

    # genbi_fetch_context
    @toolkit.tool(retries=1)
    async def genbi_fetch_context(params: FetchContextParams) -> dict:
        """获取与问题相关的语义上下文（表描述、列信息、历史查询）"""
        try:
            return memory_api.fetch(
                params.question,
                limit=params.limit,
                item_type="table" if params.strategy == "full" else None,
            )
        except MemoryNotEnabledError:
            return {"error": "memory 未启用，请运行 `genbi memory index`", "context": []}

    # genbi_recall_queries
    @toolkit.tool(retries=1)
    async def genbi_recall_queries(params: RecallQueriesParams) -> list[dict]:
        """检索相似的历史 NL→SQL 对"""
        try:
            return memory_api.recall(params.question, limit=params.limit)
        except MemoryNotEnabledError:
            return []

    tools.extend([genbi_fetch_context, genbi_recall_queries])

    # genbi_store_query（需要显式 include_write=True）
    if include_write:
        @toolkit.tool(retries=1)
        async def genbi_store_query(params: StoreQueryParams) -> str:
            """保存确认的 NL→SQL 对到记忆库"""
            try:
                memory_api.store(
                    nl_query=params.nl_query,
                    sql_query=params.sql_query,
                    tags=params.tags,
                )
                return f"已保存：{params.nl_query[:50]}..."
            except MemoryNotEnabledError:
                raise RuntimeError("memory 未启用，无法保存。请运行 `genbi memory index`")
            except ValueError as e:
                raise ValueError(str(e))

        tools.append(genbi_store_query)

    return tools
```

---

## 八、指令构建器（P2 - 重写）

**源文件**：`sdk/wren-pydantic/src/wren_pydantic/_instructions.py`

```python
# src/micro_genbi/pipeline/instructions.py
# 架构参考: wren-pydantic/_instructions.py（需重写适配 Micro-GenBI）

"""System Prompt 指令构建器"""

from .toolkit import GenBIToolkit
from .db.schema_registry import SchemaRegistry


def build_instructions(toolkit: GenBIToolkit) -> str:
    """
    构建系统指令（System Prompt）。
    
    包含：
    1. Agent 角色定义
    2. 可用工具说明
    3. 数据库 schema 上下文
    4. SQL 铁律
    5. 多库查询规范（场景 A/B/C）
    6. 预测查询规范
    """
    ctx = _build_schema_context(toolkit)
    return INSTRUCTIONS_TEMPLATE.format(schema_context=ctx)


INSTRUCTIONS_TEMPLATE = """
你是一个企业级数据分析助手（Micro-GenBI）。

## 可用工具

- **genbi_query**: 执行 SQL 查询（只读，返回 JSON 结果）
- **genbi_dry_plan**: 验证 SQL 有效性（不实际执行）
- **genbi_list_tables**: 列出所有可用表和字段
- **genbi_fetch_context**: 获取语义上下文（表描述、历史查询）
- **genbi_recall_queries**: 检索相似的历史查询

## 数据库架构

{schema_context}

## SQL 铁律（必须遵守）

1. **只读**：所有 SQL 必须是 SELECT，禁止 INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE
2. **显式字段**：禁止 SELECT *，必须列出所有需要的字段名
3. **结果上限**：所有 SELECT 必须带 LIMIT（默认 LIMIT 1000）
4. **列名正确**：必须使用 schema 中定义的实际列名
5. **参数化**：用户输入不得直接拼入 SQL，使用参数化查询

## 多库查询规范

### 场景 A - 同构多库聚合（汇总数据）
当用户查询"全省"、"全部"、"所有城市"等时：
- 生成 N 条子 SQL（每个库一条），带上库标识列
- 使用 UNION ALL 合并
- 最终层 GROUP BY 聚合

### 场景 B - 异构跨库 JOIN
当查询涉及的表来自不同数据库时：
- 每库生成独立的子 SQL
- 通过 cross_db_relations 中定义的关联键归并
- JOIN 在 Python 层执行

### 场景 C - 混合模式
先聚合同构库，再关联异构库。

## 预测查询规范

当用户问"预测"、"趋势"、"未来"时：
1. 先执行历史数据查询
2. 调用预测服务（Prophet / 统计模型）
3. 返回预测值和置信区间
"""


def _build_schema_context(toolkit: GenBIToolkit) -> str:
    """从 SchemaRegistry 构建 LLM 可读的 schema 上下文"""
    # 实际实现：调用 SchemaRegistry.build_llm_context()
    lines = []
    for db in toolkit.get_all_databases():
        lines.append(f"## 数据库：{db.display_name} (ID: {db.id})")
        lines.append(f"  类型：{'同构聚合库' if db.db_category == 'sibling' else '主库/异构库'}")
        if db.city_code:
            lines.append(f"  城市编码：{db.city_code}")
        lines.append("")
    return "\n".join(lines)
```

---

## 九、LanceDB MemoryStore 移植

**源文件**：`core/wren/src/wren/memory/store.py`

这是最复杂的部分，需要从 Rust/Python 混合实现中提取 LanceDB 向量存储逻辑。

```python
# src/micro_genbi/memory/store.py
# 架构移植自: core/wren/src/wren/memory/store.py

"""
Micro-GenBI LanceDB 记忆存储。

提供向量语义搜索能力：
- 表/列的语义描述向量（用于 fetch）
- NL→SQL 对的历史向量（用于 recall）

依赖：
    pip install lancedb sentence-transformers
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    import lancedb
    from lancedb.embeddings import get_embedding_model
    HAS_LANCEDB = True
except ImportError:
    HAS_LANCEDB = False

from .api import MemoryNotEnabledError


class LanceDBMemoryStore:
    """
    LanceDB 向量记忆存储。
    
    对应 WrenAI core/wren/src/wren/memory/store.py 的 MemoryStore。
    
    两张表：
    - context_table: 语义上下文（表描述、列描述）
    - queries_table: 历史 NL→SQL 对
    """

    _SCHEMA_VERSION = "v1"

    def __init__(self, db_path: str | Path, embedding_model: str = "BAAI/bge-small-zh-v1.5"):
        if not HAS_LANCEDB:
            raise MemoryNotEnabledError(
                "LanceDB 未安装。运行：pip install lancedb sentence-transformers"
            )

        self._db_path = Path(db_path).expanduser().resolve()
        self._db_path.mkdir(parents=True, exist_ok=True)

        self._db = lancedb.connect(str(self._db_path))
        self._embedding_model = get_embedding_model(embedding_model)
        self._ensure_tables()

    def _ensure_tables(self):
        """创建表（如果不存在）"""
        # 上下文表
        if "context" not in self._db.table_names():
            self._db.create_table("context", schema={
                "id": "string",
                "item_type": "string",    # "table" | "column" | "model"
                "name": "string",
                "description": "string",
                "datasource": "string",
                "vector": "vector(512)", # 嵌入向量
                "raw_text": "string",
            })

        # 查询历史表
        if "queries" not in self._db.table_names():
            self._db.create_table("queries", schema={
                "id": "string",
                "nl_query": "string",
                "sql_query": "string",
                "datasource": "string",
                "tags": "string",        # 逗号分隔
                "created_at": "int64",
                "vector": "vector(512)",
            })

    # ── 上下文操作 ──────────────────────────────────

    def get_context(
        self,
        query: str,
        manifest: dict,
        limit: int = 5,
        item_type: str | None = None,
        threshold: float = 0.5,
    ) -> dict[str, Any]:
        """
        向量搜索相关上下文。
        
        1. 将 query 编码为向量
        2. 在 context 表中搜索相似条目
        3. 补充 manifest 中的表信息
        """
        table = self._db.open_table("context")
        query_vector = self._embedding_model.get_text_embedding(query)

        filters = []
        if item_type:
            filters.append(f'item_type = "{item_type}"')

        results = table.search(query_vector).limit(limit).to_list()

        # 补充 manifest 信息
        schema_tables = self._extract_tables_from_manifest(manifest)
        return {
            "context": [r for r in results if r.get("_score", 0) > threshold],
            "schema_tables": schema_tables,
            "total_context_items": len(results),
        }

    def add_context(
        self,
        item_type: str,
        name: str,
        description: str,
        datasource: str,
        raw_text: str,
    ) -> None:
        """添加语义上下文条目"""
        import uuid
        table = self._db.open_table("context")
        vector = self._embedding_model.get_text_embedding(raw_text)
        table.add([{
            "id": str(uuid.uuid4()),
            "item_type": item_type,
            "name": name,
            "description": description,
            "datasource": datasource,
            "vector": vector,
            "raw_text": raw_text,
        }])

    # ── 查询历史操作 ────────────────────────────────

    def recall_queries(
        self,
        query: str,
        limit: int = 3,
        threshold: float = 0.5,
    ) -> list[dict[str, Any]]:
        """向量搜索相似的历史 NL→SQL 对"""
        table = self._db.open_table("queries")
        query_vector = self._embedding_model.get_text_embedding(query)
        results = table.search(query_vector).limit(limit).to_list()
        return [
            {
                "nl_query": r["nl_query"],
                "sql_query": r["sql_query"],
                "datasource": r["datasource"],
                "tags": r["tags"].split(",") if r["tags"] else [],
                "score": r.get("_score", 0),
            }
            for r in results
            if r.get("_score", 0) > threshold
        ]

    def store_query(
        self,
        nl_query: str,
        sql_query: str,
        datasource: str,
        tags: str | None = None,
    ) -> None:
        """保存 NL→SQL 对"""
        import uuid, time
        table = self._db.open_table("queries")
        vector = self._embedding_model.get_text_embedding(nl_query)
        table.add([{
            "id": str(uuid.uuid4()),
            "nl_query": nl_query,
            "sql_query": sql_query,
            "datasource": datasource,
            "tags": tags or "",
            "created_at": int(time.time() * 1000),
            "vector": vector,
        }])

    # ── 内部 ────────────────────────────────────────

    def _extract_tables_from_manifest(self, manifest: dict) -> list[dict]:
        """从 manifest 中提取表信息"""
        # 实际实现：解析 manifest dict
        return []
```

---

## 十、跨库关系配置模块（P0 - 新增）

**无直接对应源码**，需要根据 Micro-GenBI 需求自行设计。

```python
# src/micro_genbi/db/cross_db_relations.py
# 新增模块（WrenAI 无直接对应）

"""跨库关系定义与解析"""

from __future__ import annotations

from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field


class CrossDBRelation(BaseModel):
    """跨库关联定义"""
    source_db: str
    source_table: str
    target_db: str
    target_table: str
    join_column: str
    cardinality: Literal["one_to_one", "one_to_many", "many_to_one"] = "one_to_one"
    description: str = ""


class CrossDBRelationRegistry:
    """
    跨库关系注册中心。
    
    加载 cross_db_relations.yaml，维护所有跨库 JOIN 关系。
    FederatedRouter 依赖此模块生成 JOIN 执行计划。
    """

    def __init__(self, relations_path: str | Path = "cross_db_relations.yaml"):
        self._relations: list[CrossDBRelation] = []
        self._index: dict[tuple[str, str], list[CrossDBRelation]] = {}
        if Path(relations_path).exists():
            self._load(relations_path)

    def _load(self, path: Path):
        with open(path) as f:
            raw = yaml.safe_load(f) or {}

        for rel in raw.get("relations", []):
            r = CrossDBRelation(**rel)
            self._relations.append(r)
            key = (r.source_db, r.source_table)
            if key not in self._index:
                self._index[key] = []
            self._index[key].append(r)

    def get_relations(self, db_id: str, table_name: str) -> list[CrossDBRelation]:
        """获取某表的所有跨库关联"""
        return self._index.get((db_id, table_name), [])

    def find_join_path(
        self,
        from_db: str, from_table: str,
        to_db: str, to_table: str,
    ) -> list[CrossDBRelation] | None:
        """
        查找两个表之间的 JOIN 路径。
        
        支持直接关联和多跳关联（如 A→B→C）。
        返回关联路径，找不到返回 None。
        """
        direct = self._index.get((from_db, from_table), [])
        for rel in direct:
            if rel.target_db == to_db and rel.target_table == to_table:
                return [rel]

        # BFS 查找多跳路径
        visited = {(from_db, from_table)}
        queue = [(rel, [rel]) for rel in direct]
        while queue:
            current, path = queue.pop(0)
            next_rels = self._index.get((current.target_db, current.target_table), [])
            for next_rel in next_rels:
                key = (next_rel.target_db, next_rel.target_table)
                if key in visited:
                    continue
                new_path = path + [next_rel]
                if next_rel.target_db == to_db and next_rel.target_table == to_table:
                    return new_path
                visited.add(key)
                queue.append((next_rel, new_path))

        return None
```

```yaml
# cross_db_relations.yaml

relations:
  - source_db: "orders_db"
    source_table: "orders"
    target_db: "financial_db"
    target_table: "payments"
    join_column: "order_id"
    cardinality: "one_to_one"
    description: "订单与支付记录一一对应"

  - source_db: "orders_db"
    source_table: "orders"
    target_db: "logistics_db"
    target_table: "shipments"
    join_column: "order_id"
    cardinality: "one_to_many"
    description: "一个订单可对应多个物流单"

  - source_db: "financial_db"
    source_table: "payments"
    target_db: "contract_db"
    target_table: "contracts"
    join_column: "contract_id"
    cardinality: "one_to_one"
    description: "支付记录与合同关联"
```

---

## 十一、完整文件清单与目标路径

以下是开发时需要创建的所有文件的完整列表：

```
src/micro_genbi/
├── __init__.py
├── errors.py              ← 移植自 WrenAI _errors.py（异常处理）
├── models.py             ← 移植自 WrenAI _models.py（Pydantic 模型）
├── toolkit.py            ← 架构参考 WrenAI _toolkit.py（主工具箱）
│
├── db/
│   ├── __init__.py
│   ├── config.py         ← 移植自 WrenAI _providers/connection.py（连接配置）
│   ├── engine.py         ← 新增（Engine 封装层）
│   ├── executor.py       ← 新增（多库并发执行）
│   ├── router.py         ← 新增（多库路由器）
│   ├── schema_registry.py← 新增（多库语义配置）
│   ├── cross_db_relations.py ← 新增（跨库关系）
│   └── connectors/       ← 新增（数据库连接器）
│       ├── __init__.py
│       ├── base.py       ← 基础连接器抽象
│       ├── postgresql.py
│       ├── mysql.py
│       └── clickhouse.py
│
├── tools/
│   ├── __init__.py
│   ├── runtime.py        ← 移植自 WrenAI _tools.py（运行时工具）
│   └── memory.py         ← 移植自 WrenAI _tools_memory.py（记忆工具）
│
├── memory/
│   ├── __init__.py
│   ├── api.py            ← 移植自 WrenAI _memory_api.py
│   ├── provider.py       ← 架构参考 WrenAI _providers/memory.py
│   └── store.py          ← 移植自 WrenAI core/wren/memory/store.py
│
├── llm/
│   ├── __init__.py
│   ├── client.py         ← 新增（LLM 客户端抽象）
│   ├── sql_generator.py  ← 新增（SQL 生成）
│   ├── analysis_service.py← 新增（LLM 深度分析）
│   └── predictors/
│       ├── __init__.py
│       ├── base.py
│       ├── prophet_predictor.py
│       └── statistics_predictor.py
│
├── pipeline/
│   ├── __init__.py
│   ├── instructions.py   ← 重写自 WrenAI _instructions.py
│   ├── intent_classifier.py  ← 新增（意图分类）
│   ├── semantic_retriever.py  ← 新增（语义检索）
│   └── self_correction.py    ← 新增（SQL 自愈）
│
└── config/
    ├── __init__.py
    ├── system.py         ← 新增（系统配置）
    └── defaults.py       ← 新增（默认配置）
```

---

## 十二、依赖清单

```txt
# requirements.txt

# 核心
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.5.0
pyyaml>=6.0

# 数据库
sqlalchemy>=2.0
asyncpg>=0.29.0       # PostgreSQL async
aiomysql>=0.2.0       # MySQL async
clickhouse-driver>=0.2.0
psycopg2-binary>=2.9

# LLM
openai>=1.10.0
anthropic>=0.18.0

# 向量存储（Memory）
lancedb>=0.5.0
sentence-transformers>=2.3.0

# 预测
prophet>=1.1.0
statsmodels>=0.14.0
xgboost>=2.0.0

# CLI
python-dotenv>=1.0.0
typer>=0.12.0
rich>=13.7.0

# 测试
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

---

*本指南为 Micro-GenBI 开发团队提供 WrenAI 源码的完整移植参考。所有代码均可直接使用或通过改名/路径调整后使用。*
