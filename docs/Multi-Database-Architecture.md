# Micro-GenBI 多库查询架构方案

> **文档版本**：v1.0  
> **作者**：Micro-GenBI Team  
> **日期**：2026-05-25  
> **状态**：设计阶段  
> **源码参考**：WrenAI-wren-v0.7.0（已下载至项目目录）

---

## 零、WrenAI 参考说明

本文档中所有涉及 WrenAI 的源码参考，均位于：

```
D:\myProjects\text2sqlAgent\WrenAI-wren-v0.7.0\
├── sdk/wren-pydantic/          ← Python SDK（主要参考）
├── sdk/wren-langchain/          ← LangChain 适配
└── core/wren/src/wren/         ← Python Engine + Memory
```

详细移植代码见配套文档：**`Micro-GenBI-WrenAI-Port-Guide.md`**，包含可直接拷贝使用的完整源码。

---

## 一、需求分析与场景定义

### 1.1 三类核心场景

用户提出的需求可以拆解为三个相互关联但本质不同的场景：

#### 场景 A：同构多库聚合（大屏 / 数据驾驶舱）

```
业务背景：省级系统连接 N 个地市级子系统的数据库，每个库的表结构完全相同。
查询模式：需要同时查询 N 个库，汇总后展示。
典型问题：
  - "显示全省本月所有子系统的营收总额"
  - "对比各市的年度 KPI 完成率"
  - "预测全省下一季度用电量趋势"
```

| 维度 | 特征 |
|------|------|
| 数据库关系 | 同构（identical schema） |
| 数据库数量 | 10~100 个 |
| 查询类型 | 聚合查询（GROUP BY 子系统编号/名称） |
| 数据量 | 大数据量，需要分布式计算 |
| 典型技术 | ClickHouse / TiDB / PostgreSQL FDW / Sharding |
| 预测能力 | 时序预测，多库聚合后建模 |

#### 场景 B：异构多库联邦查询（跨库 JOIN）

```
业务背景：大型项目拆解为多个功能库（如财务库、人事库、业务库）。
查询模式：跨库 JOIN，但引擎层面自动路由。
典型问题：
  - "查询同时使用 A 库和 B 库的用户余额数据"
  - "关联订单库和物流库，找出超时未送达的订单"
  - "财务库和合同库联合展示供应商付款情况"
```

| 维度 | 特征 |
|------|------|
| 数据库关系 | 异构（different schema） |
| 数据库数量 | 2~5 个 |
| 查询类型 | 跨库 JOIN / UNION / 子查询 |
| 数据量 | 中等，单次查询涉及多个库 |
| 典型技术 | PostgreSQL FDW / Apache Drill / Dremio / 自研路由层 |
| 预测能力 | 有限，跨库时序预测困难 |

#### 场景 C：混合模式（场景 A + 场景 B 的组合）

```
业务背景：省级系统下每个地市有多个异构子库，需要先聚合再关联。
典型问题：
  - "显示全省所有子系统中，财务支出最高的 5 个部门"
  - "关联全省 N 个订单库和 1 个统一商品库"
```

### 1.2 三种模式的对比矩阵

| 维度 | 场景 A（聚合型） | 场景 B（联邦型） | 场景 C（混合型） |
|------|-----------------|-----------------|-----------------|
| 库关系 | 同构 | 异构 | 同构+异构 |
| 库数量 | 10~100 | 2~5 | 2~100 |
| 核心算法 | Map-Reduce | Federated Join | 先聚合后关联 |
| LLM 复杂度 | 中 | 高 | 最高 |
| 延迟 | 中（并行拉取） | 高（JOIN 开销） | 高 |
| 预测支持 | 强 | 弱 | 中 |

---

## 二、当前系统能力评估

### 2.1 现有架构（基于 Micro-GenBI-Integration.md）

```
单数据库架构（现状）
┌──────────────────────────────────────────────────────────┐
│                     AskService（顶层编排）                │
│  ┌─────────┐  ┌──────────┐  ┌─────────┐  ┌───────────┐  │
│  │ Intent  │→ │ Semantic │→ │ SQL Gen │→ │ SQL Exec  │  │
│  │ G1      │  │ G2       │  │         │  │           │  │
│  └─────────┘  └──────────┘  └─────────┘  └─────┬─────┘  │
│                                                  │        │
│  ┌─────────┐  ┌──────────┐                     │        │
│  │ Chart   │← │ PostHook │← 截断+摘要          │        │
│  │ G4      │  │ G3       │                     │        │
│  └─────────┘  └──────────┘                     │        │
│                                                  ▼        │
│                                    ┌────────────────────┐ │
│                                    │  SQLAlchemy Engine │ │
│                                    │  [单数据库连接]      │ │
│                                    └────────────────────┘ │
│                                    ┌────────────────────┐ │
│                                    │    schema.yaml      │ │
│                                    │  [单库语义配置]      │ │
│                                    └────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

**核心缺失**：
- 只有单一 `engine` 实例，无多库管理
- `schema.yaml` 只有一份，无多库 schema 概念
- 无跨库 JOIN 路由逻辑
- 无同构多库并行分发机制
- 无大数据聚合 + 预测能力

### 2.2 WrenAI 参考能力分析

> **源码位置**：`sdk/wren-pydantic/src/wren_pydantic/`  
> **详细移植代码**：`Micro-GenBI-WrenAI-Port-Guide.md` 第二~九章

| WrenAI 模块 | 源码文件 | 对多库的支持 | Micro-GenBI 借鉴方案 |
|------------|---------|-------------|---------------------|
| Profile 系统 | `_providers/connection.py` | 单数据库切换（多 profile） | ✅ 迁移，支持切换不同数据库（移植指南第三章） |
| MDL 语义层 | `_providers/mdl_source.py` | 单数据库 | ⚠️ 扩展为多库 schema registry（移植指南第四章） |
| SQL Generation | `_toolkit.py` | 单库 SQL | ⚠️ 扩展支持跨库 SQL（移植指南第五章） |
| SQL Executor | `_tools.py` | 单数据库 | ❌ ExecutionEngine 全新设计（架构文档第六章） |
| LanceDB Memory | `_providers/memory.py` | 单数据库 | ⚠️ 移植并扩展多库（移植指南第七章） |
| Error Mapping | `_errors.py` | Phase-aware 错误 | ✅ 直接移植（移植指南第二章） |
| Pydantic Models | `_models.py` | WrenQueryResult | ✅ 改名移植（移植指南第四章） |
| Memory Tools | `_tools_memory.py` | fetch/recall/store | ✅ 改名移植（移植指南第七章） |

---

## 三、多库架构总体设计

### 3.1 架构分层

```
┌─────────────────────────────────────────────────────────────────┐
│                      AskService（顶层编排）                       │
│  ┌──────────┐ ┌───────────┐ ┌──────────┐ ┌──────────────────┐   │
│  │ Intent   │ │ Semantic  │ │ SQL Gen  │ │ Chart + Predict  │   │
│  │ Classifier│ │Retriever │ │(多库感知) │ │ (大数据可视化)     │   │
│  └────┬─────┘ └─────┬─────┘ └────┬─────┘ └────────┬─────────┘   │
│       └──────────────┴────────────┴───────────────┘             │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              MultiDatabaseRouter（新增）                   │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────────────┐   │  │
│  │  │ Aggregate  │  │  Federated │  │   Hybrid          │   │  │
│  │  │ Router     │  │  Router    │  │   Router          │   │  │
│  │  │(场景A)      │  │(场景B)      │  │   (场景C)         │   │  │
│  │  └─────┬──────┘  └─────┬──────┘  └─────────┬────────┘   │  │
│  └────────┼────────────────┼──────────────────┼────────────┘  │
│           │                │                  │               │
│           ▼                ▼                  ▼               │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              ExecutionEngine（并行执行层）               │   │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │   │
│  │  │ Executor │ │ Executor │ │ Executor │ │ Executor │   │   │
│  │  │ #0       │ │ #1       │ │ #2       │ │ #N       │   │   │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │              ResultAggregator（结果归并层）                │  │
│  │  场景A: UNION ALL + 最终聚合                                 │  │
│  │  场景B: Stream-Merge JOIN                                   │  │
│  │  场景C: 先聚合后关联                                        │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              │                                   │
│                              ▼                                   │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │           SchemaRegistry（多库语义配置）                   │  │
│  │  ┌────────────┐ ┌────────────┐ ┌────────────────────┐   │  │
│  │  │ DB_A        │ │ DB_B       │ │ DB_N               │   │  │
│  │  │ schema.yaml │ │ schema.yaml│ │ schema.yaml        │   │  │
│  │  │(同构聚合)    │ │(异构联邦)   │ │                    │   │  │
│  │  └────────────┘ └────────────┘ └────────────────────┘   │  │
│  └────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 多库查询类型决策树

```
用户自然语言查询
       │
       ▼
┌──────────────────┐
│ Intent 分类      │
│ (扩展 G1 层)     │
└────────┬─────────┘
         │
         ▼
┌──────────────────────────────────────────────┐
│ 自动判断查询模式：                           │
│                                              │
│ Q 涉及多个库名/子系统名？                    │
│   ├── YES → 场景 B 或 C（联邦/混合）         │
│   │         ↓                                │
│   │      schema.yaml 中查找表所在库           │
│   │      → FederatedRouter                   │
│   │                                          │
│   └── NO → Q 是否需要汇总全省/全集团数据？   │
│           ├── YES → 场景 A（聚合型）          │
│           │         ↓                         │
│           │      遍历所有同构库               │
│           │      → AggregateRouter           │
│           │                                   │
│           └── NO → 单库查询（现有逻辑）        │
│                     ↓                        │
│                  SingleRouter                │
└──────────────────────────────────────────────┘
```

---

## 四、核心组件详细设计

### 4.1 SchemaRegistry — 多库语义配置

#### 4.1.1 配置文件结构

每个数据库对应一个独立 `schema.yaml`，通过目录结构区分：

```
schema_registry/
├── _global.yaml              # 全局配置（通用字段映射、字典表）
├── province_a/               # 省库 A（主数据库）
│   ├── metadata.yaml         # 连接信息 + 表清单
│   ├── tables/               # 每张表一个 YAML 文件
│   │   ├── orders.yaml
│   │   ├── users.yaml
│   │   └── ...
│   └── relationships.yaml    # 库内 ER 关系
├── city_b/                   # 市库 B（同构）
│   ├── metadata.yaml
│   ├── tables/
│   └── relationships.yaml
├── city_c/                   # 市库 C（同构）
│   └── ...
├── financial_db/             # 财务库（异构，独立 schema）
│   ├── metadata.yaml
│   ├── tables/
│   └── relationships.yaml
└── warehouse_db/              # 仓储库（异构）
    ├── metadata.yaml
    ├── tables/
    └── relationships.yaml
```

#### 4.1.2 数据库分类元信息

```yaml
# province_a/metadata.yaml
database:
  id: "province_a"            # 全局唯一标识（LLM 引用）
  display_name: "省库 A（主库）"
  dialect: "postgresql"        # mysql / postgresql / sqlite / clickhouse
  connection:
    host: "${PROVINCE_A_HOST}"
    port: 5432
    database: "province_a_db"
    username: "${PROVINCE_A_USER}"
    password: "${PROVINCE_A_PASSWORD}"
    pool_size: 10
    max_overflow: 20

  # ── 多库分类 ────────────────────────────────
  db_category: "primary"       # primary | sibling | heterogenous
  siblings_group: null         # 同构组标识，null 表示主库或异构库
  is_aggregation_source: true  # 是否作为场景 A 的数据源
```

```yaml
# city_b/metadata.yaml
database:
  id: "city_b"
  display_name: "市库 B"
  dialect: "postgresql"
  connection:
    host: "${CITY_B_HOST}"
    port: 5432
    database: "city_b_db"
    username: "${CITY_B_USER}"
    password: "${CITY_B_PASSWORD}"
    pool_size: 5
    max_overflow: 10

  db_category: "sibling"       # 同构库
  siblings_group: "province_siblings"  # 同构组标识
  is_aggregation_source: true  # 参与场景 A 聚合
  alias_in_sql: "city_b"       # SQL 中的库前缀
```

#### 4.1.3 表级配置（每个库的 tables 目录下）

```yaml
# province_a/tables/orders.yaml
table:
  logical_name: "订单表"          # LLM 可见的逻辑名
  physical_name: "orders"        # 数据库中的实际表名
  database_id: "province_a"       # 所属数据库 ID
  description: "包含所有客户订单信息，含订单号/金额/状态/时间"
  
  columns:
    - name: "order_id"
      logical_name: "订单号"
      type: "varchar"
      is_primary_key: true
      description: "唯一订单标识"

    - name: "amount"
      logical_name: "订单金额"
      type: "decimal(12,2)"
      description: "含税订单总金额，单位：元"

    - name: "status"
      logical_name: "订单状态"
      type: "varchar"
      enum_values:            # 枚举值（关键！跨库 JOIN 时用于语义对齐）
        "PENDING": "待处理"
        "PAID": "已支付"
        "SHIPPED": "已发货"
        "COMPLETED": "已完成"
        "CANCELLED": "已取消"

    - name: "city_code"
      logical_name: "城市编码"
      type: "varchar"
      description: "关联城市维表，外键"

    - name: "created_at"
      logical_name: "创建时间"
      type: "timestamp"

  # ── 跨库关系 ────────────────────────────────────────────────
  cross_db_relations:
    - target_table: "financial_db.payments"    # 跨库引用
      join_column: "order_id"
      cardinality: "one_to_one"
      description: "订单与支付记录一一对应"

    - target_table: "warehouse_db.shipments"
      join_column: "order_id"
      cardinality: "one_to_many"
      description: "一个订单可对应多个物流单"
```

#### 4.1.4 SchemaRegistry 核心代码

```python
# src/micro_genbi/db/schema_registry.py

from pathlib import Path
from typing import TypedDict, NotRequired
import yaml
from dataclasses import dataclass, field
from collections import defaultdict


class ColumnDef(TypedDict):
    name: str
    logical_name: str
    type: str
    description: str
    enum_values: NotRequired[dict[str, str]]
    is_primary_key: NotRequired[bool]


class TableDef(TypedDict):
    logical_name: str
    physical_name: str
    database_id: str
    description: str
    columns: list[ColumnDef]
    cross_db_relations: NotRequired[list[dict]]


@dataclass
class DatabaseProfile:
    id: str
    display_name: str
    dialect: str
    connection: dict
    db_category: str          # primary / sibling / heterogenous
    siblings_group: str | None
    is_aggregation_source: bool
    alias_in_sql: str


@dataclass
class TableInfo:
    logical_name: str
    physical_name: str
    database_id: str
    description: str
    columns: list[ColumnDef]
    cross_db_relations: list[dict]

    @property
    def fqn(self) -> str:
        """Full qualified name: db_id.table_name"""
        return f"{self.database_id}.{self.physical_name}"


class SchemaRegistry:
    """
    多数据库语义配置注册中心。
    
    加载 schema_registry/ 目录下所有数据库的配置文件，
    提供全局表查找、跨库关系查询、同构库分组等能力。
    """

    def __init__(self, registry_path: str = "schema_registry"):
        self.registry_path = Path(registry_path)
        self._databases: dict[str, DatabaseProfile] = {}
        self._tables: dict[str, TableInfo] = {}      # key: "db_id.table_name"
        self._logical_names: dict[str, TableInfo] = {}  # key: logical_name -> TableInfo
        self._siblings: dict[str, list[str]] = defaultdict(list)  # group -> [db_ids]
        self._cross_db_relations: list[dict] = []

        self._load_all()

    def _load_all(self):
        for db_dir in self.registry_path.iterdir():
            if not db_dir.is_dir() or db_dir.name.startswith("_"):
                continue
            metadata_path = db_dir / "metadata.yaml"
            if not metadata_path.exists():
                continue

            with open(metadata_path) as f:
                meta = yaml.safe_load(f)

            db_cfg = meta["database"]
            db_id = db_cfg["id"]
            self._databases[db_id] = DatabaseProfile(**db_cfg)

            # 登记同构组
            if db_cfg.get("siblings_group"):
                self._siblings[db_cfg["siblings_group"]].append(db_id)

            # 加载每张表的配置
            tables_dir = db_dir / "tables"
            if tables_dir.exists():
                for table_file in tables_dir.glob("*.yaml"):
                    with open(table_file) as f:
                        t = yaml.safe_load(f)["table"]
                    info = TableInfo(
                        logical_name=t["logical_name"],
                        physical_name=t["physical_name"],
                        database_id=db_id,
                        description=t.get("description", ""),
                        columns=t.get("columns", []),
                        cross_db_relations=t.get("cross_db_relations", []),
                    )
                    self._tables[info.fqn] = info
                    self._logical_names[t["logical_name"]] = info

                    for rel in info.cross_db_relations:
                        self._cross_db_relations.append({
                            "source": info.fqn,
                            "target": rel["target_table"],
                            "join_column": rel["join_column"],
                            "cardinality": rel.get("cardinality", "one_to_one"),
                            "description": rel.get("description", ""),
                        })

    # ── 基础查询 ────────────────────────────────────────────────────

    def get_database(self, db_id: str) -> DatabaseProfile | None:
        return self._databases.get(db_id)

    def get_all_databases(self) -> list[DatabaseProfile]:
        return list(self._databases.values())

    def get_table(self, fqn: str) -> TableInfo | None:
        return self._tables.get(fqn)

    def find_table_by_logical_name(self, name: str) -> TableInfo | None:
        return self._logical_names.get(name)

    # ── 多库路由核心方法 ─────────────────────────────────────────────

    def find_table_databases(self, logical_name: str) -> list[TableInfo]:
        """
        查找某逻辑表在哪些数据库中存在。
        用于场景 A（聚合）：判断查询是否需要分发到多个同构库。
        """
        # 精确匹配
        if logical_name in self._logical_names:
            return [self._logical_names[logical_name]]

        # 模糊匹配（中文名）
        results = [
            t for t in self._logical_names.values()
            if logical_name in t.logical_name or t.logical_name in logical_name
        ]
        return results

    def get_siblings_group(self, db_id: str) -> list[DatabaseProfile]:
        """
        获取某数据库所属的同构组。
        用于场景 A：获取所有需要并行查询的库。
        """
        db = self._databases.get(db_id)
        if not db or not db.siblings_group:
            return [db] if db else []
        sibling_ids = self._siblings.get(db.siblings_group, [])
        return [self._databases[d] for d in sibling_ids if d in self._databases]

    def get_all_aggregation_sources(self) -> list[DatabaseProfile]:
        """
        获取所有标记为聚合数据源的数据库。
        用于场景 A：查询需要汇总全省数据时。
        """
        return [
            db for db in self._databases.values()
            if db.is_aggregation_source
        ]

    def get_cross_db_targets(self, source_fqn: str) -> list[TableInfo]:
        """
        获取某表所有跨库引用关系。
        用于场景 B：生成跨库 JOIN SQL。
        """
        targets = []
        for rel in self._cross_db_relations:
            if rel["source"] == source_fqn:
                target_db, target_table = rel["target_table"].split(".", 1)
                info = self._tables.get(rel["target_table"])
                if info:
                    targets.append(info)
        return targets

    def get_databases_involving_tables(self, table_names: list[str]) -> set[str]:
        """
        给定一组逻辑表名，返回涉及的所有数据库 ID。
        用于场景 B：判断是否需要联邦查询。
        """
        involved_dbs = set()
        for name in table_names:
            for table in self.find_table_databases(name):
                involved_dbs.add(table.database_id)
        return involved_dbs

    def is_multi_database_query(self, table_names: list[str]) -> tuple[bool, str]:
        """
        判断查询是否涉及多个数据库。
        返回：(is_multi, query_mode)
        query_mode: "single" | "aggregate" | "federated" | "hybrid"
        """
        involved = self.get_databases_involving_tables(table_names)

        if len(involved) == 0:
            return False, "single"
        if len(involved) == 1:
            return False, "single"

        # 检查是否为同构聚合
        all_sources = {db.id for db in self.get_all_aggregation_sources()}
        if involved.issubset(all_sources) and len(involved) > 1:
            return True, "aggregate"

        return True, "federated"

    # ── Prompt 注入 ─────────────────────────────────────────────────

    def build_llm_context(self, involved_db_ids: list[str] | None = None) -> str:
        """
        构建 LLM 可读的语义上下文（用于注入 System Prompt）。
        
        如果 involved_db_ids 为空，则注入所有库的 schema；
        如果指定，则只注入相关库的 schema（减少 token）。
        """
        lines = ["# 数据库语义配置\n"]

        if involved_db_ids:
            dbs = [self._databases[did] for did in involved_db_ids if did in self._databases]
        else:
            dbs = list(self._databases.values())

        for db in dbs:
            lines.append(f"## 数据库：{db.display_name} (ID: {db.id})")
            lines.append(f"类型：{'同构聚合库' if db.db_category == 'sibling' else '主库/异构库'}")

            # 收集该库所有表
            db_tables = [t for t in self._tables.values() if t.database_id == db.id]
            for t in db_tables:
                lines.append(f"\n### {t.logical_name} (`{t.fqn}`)")
                if t.description:
                    lines.append(f"描述：{t.description}")
                for col in t.columns:
                    enum_info = ""
                    if col.get("enum_values"):
                        items = " / ".join(f"{k}={v}" for k, v in col["enum_values"].items())
                        enum_info = f" [枚举：{items}]"
                    lines.append(f"- {col['logical_name']}({col['name']}): {col['type']}{enum_info}")

                # 跨库关系
                cross = [r for r in self._cross_db_relations if r["source"] == t.fqn]
                for r in cross:
                    lines.append(f"  → 可跨库关联到 `{r['target']}`（{r['description']}）")
            lines.append("")

        return "\n".join(lines)
```

---

## 五、MultiDatabaseRouter — 多库路由器

### 5.1 路由策略抽象

```python
# src/micro_genbi/db/router.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any
import sqlglot

class QueryMode(Enum):
    SINGLE = "single"       # 单库查询（现有逻辑）
    AGGREGATE = "aggregate" # 场景 A：同构多库聚合
    FEDERATED = "federated" # 场景 B：异构跨库 JOIN
    HYBRID = "hybrid"       # 场景 C：先聚合后关联


@dataclass
class QueryPlan:
    """
    多库查询执行计划。
    
    示例（场景 A - 聚合）：
        sub_plans = [
            {"db_id": "city_a", "sql": "SELECT ...", "alias": "t0"},
            {"db_id": "city_b", "sql": "SELECT ...", "alias": "t1"},
            ...
        ]
        union_sql = " UNION ALL ".join([p["sql"] for p in sub_plans])
        final_sql = f"SELECT city_code, SUM(amount) FROM ({union_sql}) GROUP BY city_code"
    
    示例（场景 B - 联邦）：
        sub_plans = [
            {"db_id": "orders_db", "sql": "SELECT ... FROM orders WHERE ..."},
            {"db_id": "financial_db", "sql": "SELECT ... FROM payments WHERE ..."},
        ]
        # 归并 JOIN 由 ResultAggregator 处理
    """
    mode: QueryMode
    is_multi_db: bool
    sub_plans: list[dict]           # [{"db_id": str, "sql": str, "alias": str}]
    final_sql: str | None           # 归并层的 SQL（如 UNION/GROUP）
    result_merge_strategy: str      # "union_all" | "stream_join" | "materialized_join"
    involved_db_ids: list[str]
    description: str                # 自然语言描述（调试用）


class DatabaseRouter(ABC):
    """数据库路由器抽象"""

    @abstractmethod
    def route(self, user_query: str, tables: list[str]) -> QueryPlan:
        """根据用户查询和涉及的表，生成多库执行计划"""
        ...


class AggregateRouter(DatabaseRouter):
    """
    场景 A 路由器：同构多库聚合。
    
    策略：
    1. 确定查询涉及的表（来自哪些同构库）
    2. 生成 N 条子 SQL（每个库一条），子 SQL 携带库标识列
    3. UNION ALL 合并结果
    4. 在归并层执行 GROUP BY 聚合
    """

    def __init__(self, registry: SchemaRegistry):
        self.registry = registry

    def route(self, user_query: str, tables: list[str]) -> QueryPlan:
        involved_dbs = self.registry.get_databases_involving_tables(tables)
        
        sub_plans = []
        for db_id in involved_dbs:
            db = self.registry.get_database(db_id)
            # 子 SQL 需要添加 DB 标识列（如 city_code）
            sub_sql = self._build_sub_sql(db_id, tables, user_query)
            sub_plans.append({
                "db_id": db_id,
                "sql": sub_sql,
                "display_name": db.display_name,
            })

        # 归并层：UNION ALL + 聚合
        union_sql = " UNION ALL ".join([p["sql"] for p in sub_plans])
        final_sql = f"SELECT * FROM ({union_sql}) AS aggregated_result"

        return QueryPlan(
            mode=QueryMode.AGGREGATE,
            is_multi_db=True,
            sub_plans=sub_plans,
            final_sql=final_sql,
            result_merge_strategy="union_all",
            involved_db_ids=list(involved_dbs),
            description=f"聚合查询，扫描 {len(sub_plans)} 个同构库",
        )

    def _build_sub_sql(self, db_id: str, tables: list[str], user_query: str) -> str:
        """生成子 SQL：带上库标识列，便于归并层识别来源"""
        # 实际由 LLM 生成，这里给出模板
        return f"SELECT *, '{db_id}' AS _source_db FROM {tables[0]}"


class FederatedRouter(DatabaseRouter):
    """
    场景 B 路由器：异构跨库 JOIN。
    
    策略：
    1. 识别查询涉及的异构库
    2. 生成每库的子 SQL（带主键/关联键）
    3. 由 ResultAggregator 执行流式归并 JOIN
    4. 支持三种归并策略：Broadcast Join / Shuffle Join / Lookup Join
    """

    def __init__(self, registry: SchemaRegistry):
        self.registry = registry

    def route(self, user_query: str, tables: list[str]) -> QueryPlan:
        involved_dbs = self.registry.get_databases_involving_tables(tables)
        
        sub_plans = []
        for db_id in involved_dbs:
            db = self.registry.get_database(db_id)
            sub_sql = self._build_sub_sql(db_id, tables, user_query)
            sub_plans.append({
                "db_id": db_id,
                "sql": sub_sql,
                "display_name": db.display_name,
            })

        return QueryPlan(
            mode=QueryMode.FEDERATED,
            is_multi_db=True,
            sub_plans=sub_plans,
            final_sql=None,  # 流式归并，不生成最终 SQL
            result_merge_strategy="stream_join",
            involved_db_ids=list(involved_dbs),
            description=f"联邦查询，涉及 {len(sub_plans)} 个异构库",
        )

    def _build_sub_sql(self, db_id: str, tables: list[str], user_query: str) -> str:
        return f"SELECT * FROM {tables[0]} WHERE _limit_clause"


class SingleRouter(DatabaseRouter):
    """单库路由器（现有逻辑）"""

    def route(self, user_query: str, tables: list[str]) -> QueryPlan:
        return QueryPlan(
            mode=QueryMode.SINGLE,
            is_multi_db=False,
            sub_plans=[],
            final_sql=None,
            result_merge_strategy="none",
            involved_db_ids=[],
            description="单库查询",
        )


class MultiDatabaseRouter:
    """
    多库路由主入口。
    
    根据 schema_registry 的信息，自动选择路由策略。
    """

    def __init__(self, registry: SchemaRegistry):
        self.registry = registry
        self._routers: dict[QueryMode, DatabaseRouter] = {
            QueryMode.AGGREGATE: AggregateRouter(registry),
            QueryMode.FEDERATED: FederatedRouter(registry),
            QueryMode.SINGLE: SingleRouter(),
        }

    def route(self, user_query: str, tables: list[str]) -> QueryPlan:
        """
        主路由入口。
        
        自动判断查询类型并分发到对应路由器。
        """
        is_multi, mode_str = self.registry.is_multi_database_query(tables)
        
        if not is_multi:
            return self._routers[QueryMode.SINGLE].route(user_query, tables)
        
        mode = QueryMode(mode_str)
        router = self._routers.get(mode, self._routers[QueryMode.FEDERATED])
        return router.route(user_query, tables)
```

---

## 六、ExecutionEngine — 多库并行执行层

### 6.1 连接池工厂

```python
# src/micro_genbi/db/connection_factory.py

from contextlib import asynccontextmanager
from typing import Any
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import create_engine as create_sync_engine
from sqlalchemy.pool import NullPool, QueuePool
import asyncpg

from .schema_registry import SchemaRegistry, DatabaseProfile


class ConnectionFactory:
    """
    多数据库连接池工厂。
    
    每个数据库维护独立的连接池，按需创建和销毁。
    支持同步（SQLAlchemy 1.x）和异步（asyncpg）两种模式。
    """

    def __init__(self, registry: SchemaRegistry):
        self.registry = registry
        self._sync_engines: dict[str, Any] = {}
        self._async_engines: dict[str, Any] = {}
        self._async_session_makers: dict[str, async_sessionmaker] = {}

    # ── 同步连接（SQLAlchemy 1.x ORM） ───────────────────────────────

    def get_sync_engine(self, db_id: str):
        """获取同步引擎（用于小数据量或同步 API）"""
        if db_id not in self._sync_engines:
            db = self.registry.get_database(db_id)
            self._sync_engines[db_id] = create_sync_engine(
                self._build_dsn(db),
                poolclass=QueuePool,
                pool_size=db.connection.get("pool_size", 5),
                max_overflow=db.connection.get("max_overflow", 10),
                pool_pre_ping=True,
                echo=False,
            )
        return self._sync_engines[db_id]

    # ── 异步连接（asyncpg / aiomysql） ───────────────────────────────

    async def get_async_engine(self, db_id: str):
        """获取异步引擎（推荐，用于大数据量查询）"""
        if db_id not in self._async_engines:
            db = self.registry.get_database(db_id)
            dialect = db.dialect

            if dialect == "postgresql":
                engine = create_async_engine(
                    self._build_async_dsn(db),
                    poolclass=QueuePool,
                    pool_size=db.connection.get("pool_size", 10),
                    max_overflow=db.connection.get("max_overflow", 20),
                    pool_pre_ping=True,
                )
            elif dialect == "mysql":
                import aiomysql
                pool = await aiomysql.create_pool(
                    host=db.connection["host"],
                    port=db.connection.get("port", 3306),
                    user=db.connection["username"],
                    password=db.connection["password"],
                    db=db.connection["database"],
                    minsize=2,
                    maxsize=db.connection.get("pool_size", 10),
                )
                self._async_engines[db_id] = pool
                return pool
            else:
                # 其他方言走标准异步
                engine = create_async_engine(
                    self._build_async_dsn(db),
                    pool_size=db.connection.get("pool_size", 5),
                    max_overflow=db.connection.get("max_overflow", 10),
                )
            self._async_engines[db_id] = engine

        return self._async_engines[db_id]

    async def execute_async(self, db_id: str, sql: str, params: dict | None = None):
        """在指定数据库上执行异步 SQL"""
        db = self.registry.get_database(db_id)
        dialect = db.dialect

        if dialect == "postgresql":
            engine = await self.get_async_engine(db_id)
            async with engine.connect() as conn:
                result = await conn.execute(text(sql), params or {})
                rows = result.fetchall()
                cols = result.keys()
                return [dict(zip(cols, row)) for row in rows]

        elif dialect == "mysql":
            pool = await self.get_async_engine(db_id)
            async with pool.acquire() as conn:
                async with conn.cursor() as cur:
                    await cur.execute(sql, params or {})
                    rows = await cur.fetchall()
                    cols = [d[0] for d in cur.description] if cur.description else []
                    return [dict(zip(cols, row)) for row in rows]

        else:
            # 通用异步（SQLAlchemy Core）
            engine = await self.get_async_engine(db_id)
            from sqlalchemy import text
            async with engine.begin() as conn:
                result = await conn.execute(text(sql), params or {})
                if result.returns_rows:
                    rows = result.fetchall()
                    cols = result.keys()
                    return [dict(zip(cols, row)) for row in rows]
                return []

    def _build_dsn(self, db: DatabaseProfile) -> str:
        conn = db.connection
        if db.dialect == "postgresql":
            return f"postgresql+psycopg2://{conn['username']}:{conn['password']}@{conn['host']}:{conn.get('port', 5432)}/{conn['database']}"
        elif db.dialect == "mysql":
            return f"mysql+pymysql://{conn['username']}:{conn['password']}@{conn['host']}:{conn.get('port', 3306)}/{conn['database']}"
        elif db.dialect == "clickhouse":
            return f"clickhouse+async://{conn['username']}:{conn['password']}@{conn['host']}:{conn.get('port', 8123)}/{conn['database']}"
        raise ValueError(f"Unsupported dialect: {db.dialect}")

    def _build_async_dsn(self, db: DatabaseProfile) -> str:
        conn = db.connection
        if db.dialect == "postgresql":
            return f"postgresql+asyncpg://{conn['username']}:{conn['password']}@{conn['host']}:{conn.get('port', 5432)}/{conn['database']}"
        elif db.dialect == "mysql":
            return f"mysql+aiomysql://{conn['username']}:{conn['password']}@{conn['host']}:{conn.get('port', 3306)}/{conn['database']}"
        elif db.dialect == "clickhouse":
            return f"clickhouse+asynchttp://{conn['username']}:{conn['password']}@{conn['host']}:{conn.get('port', 8123)}/{conn['database']}"
        raise ValueError(f"Unsupported dialect: {db.dialect}")

    async def close_all(self):
        """关闭所有连接池"""
        for engine in self._sync_engines.values():
            engine.dispose()
        for engine in self._async_engines.values():
            if hasattr(engine, 'terminate'):
                engine.terminate()
            else:
                await engine.dispose()
```

### 6.2 多库并行执行器

```python
# src/micro_genbi/db/executor.py

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any
import logging

from .connection_factory import ConnectionFactory
from .router import QueryPlan, QueryMode
from .schema_registry import SchemaRegistry

logger = logging.getLogger(__name__)


@dataclass
class SubQueryResult:
    """单个库的查询结果"""
    db_id: str
    sql: str
    data: list[dict] | None
    row_count: int
    elapsed_ms: float
    error: str | None = None


@dataclass
class MultiDBExecutionResult:
    """多库查询最终结果"""
    plan: QueryPlan
    sub_results: list[SubQueryResult]
    merged_data: list[dict] | None
    total_row_count: int
    total_elapsed_ms: float
    errors: list[str]


class ExecutionEngine:
    """
    多库并行执行引擎。
    
    策略：
    - 场景 A（AGGREGATE）：并发执行所有子 SQL，最后 UNION 归并
    - 场景 B（FEDERATED）：并发执行所有子 SQL，流式归并 JOIN
    - 场景 C（HYBRID）：先聚合，再关联
    """

    def __init__(self, registry: SchemaRegistry, factory: ConnectionFactory):
        self.registry = registry
        self.factory = factory

    async def execute_plan(self, plan: QueryPlan) -> MultiDBExecutionResult:
        """
        执行多库查询计划。
        
        并发执行所有子查询，然后根据归并策略合并结果。
        """
        start = asyncio.get_event_loop().time()
        sub_results: list[SubQueryResult] = []

        if plan.mode == QueryMode.SINGLE:
            # 单库，直接执行（现有逻辑）
            return await self._execute_single(plan)

        # ── 多库并发执行 ────────────────────────────────────────────
        tasks = []
        for sub_plan in plan.sub_plans:
            task = self._execute_sub_query(sub_plan["db_id"], sub_plan["sql"])
            tasks.append(task)

        # 并发执行所有子查询（asyncio.gather）
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for sub_plan, result in zip(plan.sub_plans, results):
            if isinstance(result, Exception):
                sub_results.append(SubQueryResult(
                    db_id=sub_plan["db_id"],
                    sql=sub_plan["sql"],
                    data=None,
                    row_count=0,
                    elapsed_ms=0,
                    error=str(result),
                ))
            else:
                sub_results.append(result)

        # ── 归并结果 ──────────────────────────────────────────────
        merged = await self._merge_results(plan, sub_results)

        elapsed = (asyncio.get_event_loop().time() - start) * 1000
        errors = [r.error for r in sub_results if r.error]

        return MultiDBExecutionResult(
            plan=plan,
            sub_results=sub_results,
            merged_data=merged,
            total_row_count=len(merged) if merged else 0,
            total_elapsed_ms=elapsed,
            errors=errors,
        )

    async def _execute_sub_query(self, db_id: str, sql: str) -> SubQueryResult:
        """在单个数据库上执行查询"""
        import time
        start = time.perf_counter()

        try:
            data = await self.factory.execute_async(db_id, sql)
            elapsed = (time.perf_counter() - start) * 1000
            return SubQueryResult(
                db_id=db_id,
                sql=sql,
                data=data,
                row_count=len(data),
                elapsed_ms=elapsed,
            )
        except Exception as e:
            elapsed = (time.perf_counter() - start) * 1000
            logger.error(f"Query failed on {db_id}: {e}")
            return SubQueryResult(
                db_id=db_id,
                sql=sql,
                data=None,
                row_count=0,
                elapsed_ms=elapsed,
                error=str(e),
            )

    async def _merge_results(
        self, plan: QueryPlan, sub_results: list[SubQueryResult]
    ) -> list[dict] | None:
        """根据归并策略合并多库结果"""

        if plan.result_merge_strategy == "union_all":
            # 场景 A：UNION ALL 归并（最常见的大屏聚合）
            merged: list[dict] = []
            for r in sub_results:
                if r.data:
                    merged.extend(r.data)
            return merged

        elif plan.result_merge_strategy == "stream_join":
            # 场景 B：流式 JOIN（两表归并）
            return await self._stream_join(sub_results)

        elif plan.result_merge_strategy == "materialized_join":
            # 场景 B（大表）：物化 JOIN（拉取全部数据后内存 JOIN）
            return await self._materialized_join(sub_results)

        return None

    async def _stream_join(self, sub_results: list[SubQueryResult]) -> list[dict]:
        """流式 JOIN（用于中小表，数据量 < 10000 行）"""
        if len(sub_results) < 2:
            return sub_results[0].data if sub_results else []

        # 以第一个结果为基准，逐条匹配
        primary = sub_results[0].data or []
        secondary = {r["join_key"]: r for r in (sub_results[1].data or [])} if len(sub_results) > 1 else {}

        merged = []
        for row in primary:
            key = row.get("join_key") or row.get("order_id")
            if key in secondary:
                merged.append({**row, **secondary[key]})
            else:
                # LEFT JOIN 语义：保留主表行
                merged.append(row)

        return merged

    async def _materialized_join(self, sub_results: list[SubQueryResult]) -> list[dict]:
        """物化 JOIN（用于大表，先拉取后内存 JOIN）"""
        # 构建哈希表优化 JOIN
        if not sub_results:
            return []

        primary = sub_results[0].data or []
        others = sub_results[1:]

        # 构建索引
        index: dict[Any, list[dict]] = {}
        for other in others:
            for row in (other.data or []):
                key = row.get("join_key") or row.get("order_id")
                if key not in index:
                    index[key] = []
                index[key].append(row)

        merged = []
        for row in primary:
            key = row.get("join_key") or row.get("order_id")
            if key in index:
                for idx_row in index[key]:
                    merged.append({**row, **idx_row})

        return merged

    async def _execute_single(self, plan: QueryPlan) -> MultiDBExecutionResult:
        """单库执行（现有逻辑的封装）"""
        if not plan.involved_db_ids:
            return MultiDBExecutionResult(
                plan=plan, sub_results=[], merged_data=[],
                total_row_count=0, total_elapsed_ms=0, errors=["No database specified"]
            )

        db_id = plan.involved_db_ids[0]
        # 这里实际执行单库 SQL（由 SQLAgentExecutor 调用）
        return MultiDBExecutionResult(
            plan=plan, sub_results=[], merged_data=[],
            total_row_count=0, total_elapsed_ms=0, errors=[]
        )
```

---

## 七、大数据与预测能力

### 7.1 大数据场景分析

场景 A（同构多库聚合）本质上是一个分布式数据聚合问题。根据数据规模和技术选型，有三条路径：

#### 路径一：ClickHouse（推荐，适合超大规模）

```
场景：省级数据，日增量 > 1 亿行，需要亚秒级查询响应。

架构：
┌──────────────────────────────────────────────────────────┐
│                  各地市 DB (MySQL/PG)                    │
│           (CDC 实时同步 → Kafka → ClickHouse)             │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    ClickHouse Cluster                     │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐           │
│  │ SHARD  │ │ SHARD  │ │ SHARD  │ │ SHARD  │           │
│  │ city_a │ │ city_b │ │ city_c │ │ city_d │           │
│  └────────┘ └────────┘ └────────┘ └────────┘           │
│                       │                                  │
│                  Replica Set                             │
│                       ▼                                  │
│                  SELECT ... FROM cluster()                │
└──────────────────────────────────────────────────────────┘
```

**Micro-GenBI 对接方式**：
```python
# src/micro_genbi/db/connectors/clickhouse_connector.py

class ClickHouseConnector(DBConnector):
    """
    ClickHouse 连接器。
    
    支持：
    - Cluster 模式（集群聚合查询）
    - 物化视图（预聚合）
    - Dictionary（维表）
    """
    
    async def cluster_query(self, sql: str, cluster_name: str = "default") -> list[dict]:
        """
        执行集群聚合查询。
        
        示例：
        SELECT city, sum(amount) 
        FROM cluster('{cluster_name}', default, orders)
        GROUP BY city
        """
        cluster_sql = f"SELECT * FROM cluster('{cluster_name}', default, ({sql}))"
        return await self.execute(cluster_sql)

    async def get_materialized_view(self, view_name: str, limit: int = 1000) -> list[dict]:
        """读取物化视图（预聚合数据，用于大屏加速）"""
        sql = f"SELECT * FROM {view_name} LIMIT {limit}"
        return await self.execute(sql)
```

#### 路径二：PostgreSQL FDW（适合中等规模，无需额外组件）

```
场景：子库数量 10~20 个，MySQL/PostgreSQL 混布，不想引入 ClickHouse。

架构：
┌──────────────────────────────────────────────────────────┐
│              PostgreSQL 中心节点（联邦协调器）             │
│                                                          │
│  CREATE FOREIGN TABLE city_a_orders (... )              │
│    SERVER city_a OPTIONS (host '10.0.1.1', port '5432'); │
│                                                          │
│  CREATE FOREIGN TABLE city_b_orders (... )               │
│    SERVER city_b OPTIONS (host '10.0.2.1', port '5432'); │
│                                                          │
│  -- 统一查询                                              │
│  SELECT city, SUM(amount) FROM (                         │
│    SELECT 'city_a' as city, amount FROM city_a_orders    │
│    UNION ALL                                             │
│    SELECT 'city_b' as city, amount FROM city_b_orders     │
│  ) t GROUP BY city                                       │
└──────────────────────────────────────────────────────────┘
```

#### 路径三：Python 并行拉取（轻量实现，适合 < 10 库）

```
架构：Micro-GenBI ExecutionEngine 并发拉取各库数据，内存聚合。

适用场景：
- 库数量 < 10
- 单库数据量 < 10 万行
- 查询延迟 < 5 秒可接受

（当前 ExecutionEngine 默认实现）
```

### 7.2 预测能力设计

#### 7.2.1 预测类型划分

| 预测类型 | 适用场景 | 技术方案 | 数据要求 |
|---------|---------|---------|---------|
| 时序预测 | 全省营收趋势/用电量预测 | Prophet / ARIMA | ≥ 24 个月历史数据 |
| 同比环比 | 月度/季度 KPI 对比预测 | 统计模型 | ≥ 12 个月数据 |
| 回归预测 | 影响因素分析 | XGBoost / LightGBM | 含特征列的历史数据 |
| 异常检测 | 异常值预警 | Isolation Forest / DBSCAN | ≥ 1000 条基线数据 |

#### 7.2.2 预测服务架构

```python
# src/micro_genbi/predict/predictor.py

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
import pandas as pd
from datetime import datetime


@dataclass
class ForecastResult:
    """预测结果"""
    model_name: str
    forecast_values: list[float]
    forecast_dates: list[str]
    confidence_lower: list[float]    # 置信区间下界
    confidence_upper: list[float]   # 置信区间上界
    metrics: dict[str, float]       # MAPE / RMSE / R²
    interpretation: str             # 自然语言解读


class TimeSeriesPredictor(ABC):
    """时序预测器抽象"""

    @abstractmethod
    async def forecast(
        self,
        df: pd.DataFrame,
        date_column: str,
        value_column: str,
        periods: int = 3,
        frequency: str = "MS",  # 月度起始 "MS", 季度 "QS", 周 "W"
    ) -> ForecastResult:
        """执行时序预测"""
        ...


class ProphetPredictor(TimeSeriesPredictor):
    """
    Facebook Prophet 预测器。
    
    适合：
    - 包含季节性（节假日）的商业数据
    - 日/周/月/年 周期数据
    - 有缺失值和异常值的数据
    """

    def __init__(self):
        try:
            from prophet import Prophet
            self.Prophet = Prophet
        except ImportError:
            raise ImportError("prophet not installed. Run: pip install prophet")

    async def forecast(
        self,
        df: pd.DataFrame,
        date_column: str,
        value_column: str,
        periods: int = 3,
        frequency: str = "MS",
    ) -> ForecastResult:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._forecast_sync,
                                          df, date_column, value_column, periods, frequency)

    def _forecast_sync(
        self, df: pd.DataFrame, date_column: str, value_column: str,
        periods: int, frequency: str
    ) -> ForecastResult:
        from prophet import Prophet

        # 准备数据格式（Prophet 要求 ds/y）
        prophet_df = df[[date_column, value_column]].copy()
        prophet_df.columns = ["ds", "y"]
        prophet_df["ds"] = pd.to_datetime(prophet_df["ds"])

        model = Prophet(
            yearly_seasonality=True,
            weekly_seasonality=True,
            daily_seasonality=False,
            seasonality_mode="multiplicative",
        )
        model.fit(prophet_df)

        future = model.make_future_dataframe(periods=periods, freq=frequency)
        forecast = model.predict(future)

        future_forecast = forecast.tail(periods)

        # 计算 MAPE
        actual = prophet_df["y"].values
        pred = forecast["yhat"].values[:len(actual)]
        mape = float(np.mean(np.abs((actual - pred) / (actual + 1e-10))) * 100)

        return ForecastResult(
            model_name="Prophet",
            forecast_values=future_forecast["yhat"].tolist(),
            forecast_dates=future_forecast["ds"].dt.strftime("%Y-%m-%d").tolist(),
            confidence_lower=future_forecast["yhat_lower"].tolist(),
            confidence_upper=future_forecast["yhat_upper"].tolist(),
            metrics={"MAPE": mape, "R2": self._calc_r2(actual, pred)},
            interpretation=self._interpret(future_forecast, mape),
        )

    def _calc_r2(self, actual: np.ndarray, pred: np.ndarray) -> float:
        ss_res = np.sum((actual - pred) ** 2)
        ss_tot = np.sum((actual - np.mean(actual)) ** 2)
        return float(1 - ss_res / (ss_tot + 1e-10))

    def _interpret(self, forecast: pd.DataFrame, mape: float) -> str:
        last_val = forecast["yhat"].iloc[-1]
        first_val = forecast["yhat"].iloc[0]
        trend_pct = (last_val - first_val) / (first_val + 1e-10) * 100
        return (f"基于 Prophet 模型预测，未来趋势{'上升' if trend_pct > 0 else '下降'} "
                f"{abs(trend_pct):.1f}%，MAPE={mape:.1f}%")


class StatisticsPredictor(TimeSeriesPredictor):
    """
    统计预测器（轻量，无需额外依赖）。
    
    支持：
    - 同比增长率预测
    - 移动平均预测
    - 指数平滑预测
    """

    async def forecast(
        self,
        df: pd.DataFrame,
        date_column: str,
        value_column: str,
        periods: int = 3,
        frequency: str = "MS",
    ) -> ForecastResult:
        import numpy as np

        values = df[value_column].values
        dates = df[date_column].values

        # 同比增长率
        n = len(values)
        if n >= 12:
            yoy_rates = []
            for i in range(12, n):
                if values[i - 12] != 0:
                    yoy_rates.append(values[i] / values[i - 12])
            yoy_rate = np.mean(yoy_rates) if yoy_rates else 1.0
        else:
            yoy_rate = 1.0

        # 指数平滑预测
        alpha = 0.3
        smoothed = [values[0]]
        for v in values[1:]:
            smoothed.append(alpha * v + (1 - alpha) * smoothed[-1])

        last_value = values[-1]
        forecast_values = [last_value * (yoy_rate ** (i + 1)) for i in range(periods)]

        # 趋势判断
        trend = "上升" if yoy_rate > 1 else "下降"
        trend_pct = (yoy_rate - 1) * 100

        return ForecastResult(
            model_name="Statistics (YoY + Exponential Smoothing)",
            forecast_values=forecast_values,
            forecast_dates=[f"预测期 {i+1}" for i in range(periods)],
            confidence_lower=[v * 0.85 for v in forecast_values],
            confidence_upper=[v * 1.15 for v in forecast_values],
            metrics={"YoY_Rate": float(yoy_rate)},
            interpretation=f"基于同比分析，预测趋势{trend} {abs(trend_pct):.1f}%，置信区间 ±15%",
        )


class PredictionService:
    """
    预测服务入口。
    
    自动选择最合适的预测器，并缓存模型。
    """

    def __init__(self, cache_ttl: int = 3600):
        self._predictors: dict[str, TimeSeriesPredictor] = {}
        self._cache: dict[str, ForecastResult] = {}
        self._cache_ttl = cache_ttl

    async def predict(
        self,
        data: list[dict],
        date_column: str,
        value_column: str,
        model: str = "auto",
        periods: int = 3,
        frequency: str = "MS",
    ) -> ForecastResult:
        """
        预测入口。
        
        model 可选：prophet / statistics / xgboost / auto
        auto 模式下，数据量 > 100 条自动选择 Prophet，否则用 Statistics
        """
        import hashlib
        cache_key = hashlib.md5(
            f"{date_column}:{value_column}:{model}:{periods}:{frequency}".encode()
        ).hexdigest()

        if cache_key in self._cache:
            return self._cache[cache_key]

        df = pd.DataFrame(data)

        if model == "auto":
            model = "prophet" if len(df) > 100 else "statistics"

        predictor = self._get_predictor(model)
        result = await predictor.forecast(df, date_column, value_column, periods, frequency)

        self._cache[cache_key] = result
        return result

    def _get_predictor(self, model: str) -> TimeSeriesPredictor:
        if model not in self._predictors:
            if model == "prophet":
                self._predictors[model] = ProphetPredictor()
            elif model == "statistics":
                self._predictors[model] = StatisticsPredictor()
            else:
                raise ValueError(f"Unknown predictor: {model}")
        return self._predictors[model]
```

---

## 八、扩展 LLM Prompt 设计

### 8.1 多库感知的 System Prompt

```python
# src/micro_genbi/pipeline/multi_db_prompt.py

SYSTEM_PROMPT_MULTI_DB = """
你是一个企业级数据分析助手，支持多数据库联合查询。

## 数据库架构

{schema_context}
（由 SchemaRegistry.build_llm_context() 动态注入）

## 多库查询规范

### 场景 A - 同构多库聚合（汇总全省/全集团数据）
当用户查询涉及"全省"、"全部"、"所有城市"等汇总需求时：
- 使用 `UNION ALL` 将各库的子查询合并
- 每个子 SELECT 带上库标识列（如 `_source_db` 或 `city_name`）
- 最终层执行 GROUP BY 聚合

示例：
SELECT city_name, SUM(revenue) AS total_revenue
FROM (
    SELECT '城市A' AS city_name, revenue FROM city_a.revenue
    UNION ALL
    SELECT '城市B' AS city_name, revenue FROM city_b.revenue
    UNION ALL
    SELECT '城市C' AS city_name, revenue FROM city_c.revenue
) t
GROUP BY city_name

### 场景 B - 异构跨库 JOIN
当查询涉及的表来自不同数据库时：
- 使用显式库前缀：`database_id.table_name`
- JOIN 条件通过 cross_db_relations 中的定义确定
- 注意：跨库 JOIN 在 Python 层执行归并，不在 SQL 层做

示例（Python 归并）：
子查询1: SELECT order_id, amount FROM orders_db.orders
子查询2: SELECT order_id, status FROM financial_db.payments
→ Python StreamJoin 按 order_id 归并

### 场景 C - 混合模式
先聚合各同构库，再关联异构库。

## 预测查询规范
当用户查询包含"预测"、"趋势"、"未来"等关键词时：
- 先执行历史数据查询（带 LIMIT）
- 将结果交给 PredictionService 处理
- 返回预测结果和置信区间

## SQL 铁律（必须遵守）
1. 所有 SELECT 必须追加 LIMIT 1000
2. 禁止 SELECT *，必须显式列出字段
3. 禁止 DROP / DELETE / UPDATE / TRUNCATE / ALTER / GRANT
4. 跨库字段名必须使用 schema 中的 logical_name 映射
5. 同构库聚合时，UNION ALL 的各子查询必须有相同的列结构
"""
```

---

## 九、扩展 AskService 顶层编排

```python
# src/micro_genbi/service/multi_db_ask_service.py

from dataclasses import dataclass
from .schema_registry import SchemaRegistry
from .db.router import MultiDatabaseRouter, QueryPlan
from .db.executor import ExecutionEngine
from .db.connection_factory import ConnectionFactory
from .llm.sql_generator import SQLGenerator
from .pipeline.multi_db_prompt import SYSTEM_PROMPT_MULTI_DB


class MultiDBAskService:
    """
    多库查询顶层编排服务。
    
    完整流程：
    1. IntentClassifier → 判断是否为多库查询
    2. SchemaRegistry → 注入相关库的语义上下文
    3. SQLGenerator → 生成多库 SQL
    4. MultiDatabaseRouter → 制定执行计划
    5. ExecutionEngine → 并行执行所有子查询
    6. ResultAggregator → 归并结果
    7. PredictionService → （如需要）执行预测
    8. ChartEngine → 生成可视化配置
    """

    def __init__(self, registry_path: str = "schema_registry"):
        self.registry = SchemaRegistry(registry_path)
        self.factory = ConnectionFactory(self.registry)
        self.router = MultiDatabaseRouter(self.registry)
        self.executor = ExecutionEngine(self.registry, self.factory)
        self.sql_gen = SQLGenerator(self.registry)
        self.prediction_svc = PredictionService()

    async def ask(self, user_query: str, session_id: str | None = None,
                  predict: bool = False, periods: int = 3) -> dict:
        """
        多库查询主入口。
        
        参数：
            user_query: 自然语言查询
            session_id: 会话 ID（用于多轮对话）
            predict: 是否执行预测
            periods: 预测期数（默认 3）
        """
        # Step 1: 识别涉及的表（从 LLM 或规则引擎）
        tables = await self._identify_tables(user_query)

        # Step 2: 判断查询模式
        is_multi_db, mode = self.registry.is_multi_database_query(tables)

        # Step 3: 生成 SQL（单库或多库）
        if is_multi_db:
            sql, plan = await self._generate_multi_db_sql(user_query, tables, mode)
        else:
            sql, plan = await self._generate_single_db_sql(user_query, tables)

        # Step 4: 执行查询
        result = await self.executor.execute_plan(plan)

        # Step 5: 预测（如需要）
        chart_config = None
        if predict and result.merged_data:
            forecast = await self.prediction_svc.predict(
                result.merged_data,
                date_column="stat_date",
                value_column="amount",
                periods=periods,
            )
            chart_config = self._build_forecast_chart(forecast, result.merged_data)
        elif result.merged_data:
            chart_config = self._infer_chart(result.merged_data, user_query)

        # Step 6: 截断 + 摘要（Context Hygiene）
        summary = self._summarize_result(result, user_query)

        return {
            "sql": sql,
            "data": result.merged_data[:10] if result.merged_data else [],  # 截断
            "row_count": result.total_row_count,
            "elapsed_ms": result.total_elapsed_ms,
            "query_mode": mode,
            "chart": chart_config,
            "summary": summary,
            "errors": result.errors,
        }

    async def _identify_tables(self, user_query: str) -> list[str]:
        """从查询中识别涉及的表（逻辑名）"""
        # 简单规则匹配 + LLM 辅助识别
        all_tables = list(self.registry._logical_names.keys())
        # 优先精确匹配
        matched = [t for t in all_tables if t in user_query or 
                   any(t in user_query for t in [t, t.replace("表", "")])]
        if matched:
            return matched
        # fallback: LLM 识别
        return await self.sql_gen.identify_tables(user_query, list(self.registry._logical_names.keys()))

    async def _generate_multi_db_sql(
        self, user_query: str, tables: list[str], mode: str
    ) -> tuple[str, QueryPlan]:
        """生成多库 SQL"""
        involved_dbs = list(self.registry.get_databases_involving_tables(tables))
        ctx = self.registry.build_llm_context(involved_dbs)
        prompt = SYSTEM_PROMPT_MULTI_DB.format(schema_context=ctx)
        prompt += f"\n\n用户问题：{user_query}\n涉及的表：{tables}\n查询模式：{mode}"
        return await self.sql_gen.generate(prompt)

    async def _generate_single_db_sql(self, user_query: str, tables: list[str]) -> tuple[str, QueryPlan]:
        """生成单库 SQL"""
        db_id = list(self.registry.get_databases_involving_tables(tables))[0]
        ctx = self.registry.build_llm_context([db_id])
        prompt = SYSTEM_PROMPT_MULTI_DB.format(schema_context=ctx)
        prompt += f"\n\n用户问题：{user_query}\n涉及的表：{tables}"
        sql = await self.sql_gen.generate(prompt)
        plan = self.router.route(user_query, tables)
        return sql, plan
```

---

## 十、模式选择配置系统（用户可配置的架构模式）

用户在实际部署时，需要能够选择适合自己业务场景的数据库架构模式，而不是系统自动推断。以下是完整的三模式配置方案。

### 10.1 配置模型

```python
# src/micro_genbi/config/multi_db_config.py

from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional
import yaml


class ArchitectureMode(Enum):
    """
    三种数据库架构模式。
    
    用户在部署时选择一种模式，后续所有查询都基于该模式运行。
    模式在配置文件中指定，不支持运行时动态切换。
    """
    SINGLE = "single"          # 模式一：单数据库
    AGGREGATE = "aggregate"    # 模式二：同构多库（大屏展示）
    FEDERATED = "federated"   # 模式三：异构多库（复杂项目）


class DatabaseConfig(BaseModel):
    """单个数据库连接配置"""
    id: str = Field(..., description="数据库唯一标识（LLM 引用名）")
    display_name: str = Field(..., description="中文显示名")
    dialect: str = Field(default="postgresql", description="数据库方言")
    host: str
    port: int = Field(default=5432)
    database: str
    username: str
    password: str
    pool_size: int = Field(default=5, ge=1, le=100)
    max_overflow: int = Field(default=10, ge=0, le=50)
    # ── 模式二专用字段 ──────────────────────
    siblings_group: Optional[str] = Field(default=None, description="同构组标识")
    is_aggregation_source: bool = Field(default=False, description="是否参与聚合")
    city_code: Optional[str] = Field(default=None, description="城市/子系统编码（大屏标识）")


class SystemConfig(BaseModel):
    """系统级配置"""
    mode: ArchitectureMode = Field(default=ArchitectureMode.SINGLE)
    default_db_id: Optional[str] = Field(default=None, description="默认数据库（单库模式）")
    
    # ── 预测配置 ──────────────────────────
    enable_prediction: bool = Field(default=False, description="是否启用预测功能")
    default_predictor: str = Field(default="auto", description="预测器：auto / prophet / statistics")
    forecast_periods: int = Field(default=3, ge=1, le=12, description="默认预测期数")
    
    # ── 大数据配置 ────────────────────────
    enable_bigdata: bool = Field(default=False, description="是否启用大数据模式")
    clickhouse_cluster: Optional[str] = Field(default=None, description="ClickHouse 集群名")
    use_materialized_view: bool = Field(default=True, description="是否优先查询物化视图")
    
    # ── LLM 配置 ─────────────────────────
    llm_provider: str = Field(default="deepseek")
    llm_model: str = Field(default="deepseek-chat")
    enable_llm_analysis: bool = Field(default=True, description="是否启用 LLM 深度分析")


class ConfigLoader:
    """配置文件加载器（支持 YAML 和环境变量覆盖）"""

    @staticmethod
    def load(config_path: str = "config.yaml") -> SystemConfig:
        with open(config_path) as f:
            raw = yaml.safe_load(f)
        
        # 环境变量覆盖（生产环境常用）
        import os
        if os.getenv("GENBI_MODE"):
            raw["mode"] = os.getenv("GENBI_MODE")
        if os.getenv("GENBI_DEEPseek_API_KEY"):
            raw["databases"] = [
                {**db, "password": os.getenv(f"GENBI_DB_{db['id'].upper()}_PASSWORD", db.get("password", ""))}
                for db in raw.get("databases", [])
            ]
        
        return SystemConfig(**raw)
```

### 10.2 配置文件示例

#### 模式一：单数据库配置

```yaml
# config.single.yaml
# 适用场景：单个内部管理系统，如 OA、CRM、ERP 等

mode: single
default_db_id: "oa_prod"

databases:
  - id: "oa_prod"
    display_name: "OA 生产库"
    dialect: "postgresql"
    host: "${OA_DB_HOST}"
    port: 5432
    database: "oa_db"
    username: "${OA_DB_USER}"
    password: "${OA_DB_PASSWORD}"
    pool_size: 10

enable_prediction: false
enable_bigdata: false
enable_llm_analysis: true
```

#### 模式二：同构多库配置（大屏展示模式）

```yaml
# config.aggregate.yaml
# 适用场景：省级/集团级大屏，需要汇总 N 个子系统的同构数据

mode: aggregate
enable_bigdata: false          # 先用轻量模式，后续按需升级 ClickHouse
enable_prediction: true
default_predictor: "auto"      # auto：根据数据量自动选（>100条用Prophet）
forecast_periods: 3

databases:
  # ── 主库（省厅/总部）────────────────────────────────────
  - id: "province_head"
    display_name: "省数据中心（主库）"
    dialect: "postgresql"
    host: "${PROV_HEAD_HOST}"
    port: 5432
    database: "province_head"
    username: "${PROV_HEAD_USER}"
    password: "${PROV_HEAD_PASSWORD}"
    pool_size: 20
    is_aggregation_source: true
    city_code: "PROV"

  # ── 同构子库（各地市/子公司）─────────────────────────────
  - id: "city_hangzhou"
    display_name: "杭州市子系统"
    dialect: "postgresql"
    host: "${HZ_DB_HOST}"
    port: 5432
    database: "city_hangzhou"
    username: "${HZ_DB_USER}"
    password: "${HZ_DB_PASSWORD}"
    pool_size: 10
    siblings_group: "province_cities"    # 同构组标识（关键！）
    is_aggregation_source: true
    city_code: "HZ"

  - id: "city_ningbo"
    display_name: "宁波市子系统"
    dialect: "postgresql"
    host: "${NB_DB_HOST}"
    port: 5432
    database: "city_ningbo"
    username: "${NB_DB_USER}"
    password: "${NB_DB_PASSWORD}"
    pool_size: 10
    siblings_group: "province_cities"
    is_aggregation_source: true
    city_code: "NB"

  - id: "city_wenzhou"
    display_name: "温州市子系统"
    dialect: "postgresql"
    host: "${WZ_DB_HOST}"
    port: 5432
    database: "city_wenzhou"
    username: "${WZ_DB_USER}"
    password: "${WZ_DB_PASSWORD}"
    pool_size: 10
    siblings_group: "province_cities"
    is_aggregation_source: true
    city_code: "WZ"

  - id: "city_shaoxing"
    display_name: "绍兴市子系统"
    dialect: "mysql"
    host: "${SX_DB_HOST}"
    port: 3306
    database: "city_shaoxing"
    username: "${SX_DB_USER}"
    password: "${SX_DB_PASSWORD}"
    pool_size: 5
    siblings_group: "province_cities"
    is_aggregation_source: true
    city_code: "SX"
```

#### 模式三：异构多库配置（复杂大型项目）

```yaml
# config.federated.yaml
# 适用场景：大型项目拆分为多个功能库，需要跨库关联查询

mode: federated
enable_prediction: true
enable_llm_analysis: true

databases:
  # ── 订单业务库 ────────────────────────────────────────
  - id: "orders_db"
    display_name: "订单业务库"
    dialect: "postgresql"
    host: "${ORDERS_DB_HOST}"
    port: 5432
    database: "orders_db"
    username: "${ORDERS_DB_USER}"
    password: "${ORDERS_DB_PASSWORD}"
    pool_size: 15

  # ── 财务库 ──────────────────────────────────────────
  - id: "financial_db"
    display_name: "财务核算库"
    dialect: "postgresql"
    host: "${FIN_DB_HOST}"
    port: 5432
    database: "financial_db"
    username: "${FIN_DB_USER}"
    password: "${FIN_DB_PASSWORD}"
    pool_size: 10

  # ── 物流库 ──────────────────────────────────────────
  - id: "logistics_db"
    display_name: "物流跟踪库"
    dialect: "mysql"
    host: "${LOGISTICS_DB_HOST}"
    port: 3306
    database: "logistics_db"
    username: "${LOGISTICS_DB_USER}"
    password: "${LOGISTICS_DB_PASSWORD}"
    pool_size: 10

  # ── 合同库 ──────────────────────────────────────────
  - id: "contract_db"
    display_name: "合同管理库"
    dialect: "postgresql"
    host: "${CONTRACT_DB_HOST}"
    port: 5432
    database: "contract_db"
    username: "${CONTRACT_DB_USER}"
    password: "${CONTRACT_DB_PASSWORD}"
    pool_size: 5

# ── 跨库关系定义（核心！告诉系统哪些表可以关联）────────────
cross_db_relations:
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

### 10.3 模式感知的前端交互

```vue
<!-- 前端：架构模式选择器（部署配置页面） -->
<template>
  <div class="mode-selector">
    <div class="mode-cards">
      <div
        v-for="mode in modes"
        :key="mode.id"
        class="mode-card"
        :class="{ active: selectedMode === mode.id }"
        @click="selectMode(mode.id)"
      >
        <div class="mode-icon">{{ mode.icon }}</div>
        <h3>{{ mode.title }}</h3>
        <p>{{ mode.description }}</p>
        <ul>
          <li v-for="feature in mode.features" :key="feature">{{ feature }}</li>
        </ul>
        <div class="mode-tag" :class="mode.id">{{ mode.tag }}</div>
      </div>
    </div>

    <!-- 模式二：大屏配置面板 -->
    <div v-if="selectedMode === 'aggregate'" class="config-panel">
      <h3>大屏展示模式配置</h3>
      <div class="db-list">
        <div v-for="db in databases" :key="db.id" class="db-item">
          <input v-model="db.display_name" placeholder="子系统名称（如：杭州市）" />
          <input v-model="db.city_code" placeholder="编码（如：HZ）" />
          <input v-model="db.host" placeholder="数据库地址" />
          <input v-model="db.database" placeholder="数据库名" />
          <input v-model="db.username" placeholder="用户名" />
          <input type="password" v-model="db.password" placeholder="密码" />
          <select v-model="db.dialect">
            <option value="postgresql">PostgreSQL</option>
            <option value="mysql">MySQL</option>
          </select>
        </div>
        <button @click="addDatabase">+ 添加子系统数据库</button>
      </div>

      <div class="prediction-config">
        <h4>预测能力配置</h4>
        <label>
          <input type="checkbox" v-model="config.enable_prediction" />
          启用时序预测（营收/用电量/订单量趋势预测）
        </label>
        <div v-if="config.enable_prediction">
          <label>预测模型：
            <select v-model="config.default_predictor">
              <option value="auto">自动选择（推荐）</option>
              <option value="prophet">Prophet（长期趋势，适合 > 100 条历史数据）</option>
              <option value="statistics">统计模型（快速，< 100 条数据）</option>
            </select>
          </label>
          <label>预测期数：
            <input type="number" v-model="config.forecast_periods" min="1" max="12" />
          </label>
        </div>
      </div>

      <div class="bigdata-config">
        <h4>大数据配置</h4>
        <label>
          <input type="checkbox" v-model="config.enable_bigdata" />
          启用大数据模式（数据量 > 1000 万行）
        </label>
        <div v-if="config.enable_bigdata" class="bigdata-options">
          <label>数据仓库：
            <select v-model="config.warehouse_type">
              <option value="clickhouse">ClickHouse 集群（推荐）</option>
              <option value="pg_fdw">PostgreSQL FDW（无需额外组件）</option>
              <option value="python_parallel">Python 并行拉取（轻量，< 10 个库）</option>
            </select>
          </label>
          <div v-if="config.warehouse_type === 'clickhouse'">
            <label>ClickHouse 集群名：
              <input v-model="config.clickhouse_cluster" placeholder="如：province_cluster" />
            </label>
          </div>
        </div>
      </div>
    </div>

    <!-- 模式三：跨库关联配置面板 -->
    <div v-if="selectedMode === 'federated'" class="config-panel">
      <h3>复杂项目多库配置</h3>
      <p class="hint">为每个功能库创建独立配置，定义好跨库关联关系后，系统自动支持跨库 JOIN 查询。</p>
      <!-- 类似上面的数据库列表 ... -->
    </div>
  </div>
</template>
```

### 10.4 模式驱动的服务初始化

```python
# src/micro_genbi/service/factory.py

from .multi_db_ask_service import MultiDBAskService
from .single_ask_service import SingleAskService
from .config.multi_db_config import SystemConfig, ArchitectureMode, ConfigLoader


class ServiceFactory:
    """
    服务工厂：根据配置模式创建对应的服务实例。
    
    设计原则：模式在启动时确定，运行时不切换。
    不同模式使用不同的服务实现类，但对外接口一致。
    """

    @classmethod
    def create(cls, config_path: str = "config.yaml") -> "MultiDBAskService | SingleAskService":
        config = ConfigLoader.load(config_path)

        if config.mode == ArchitectureMode.SINGLE:
            # 模式一：单数据库，使用轻量服务
            return SingleAskService(
                default_db_id=config.default_db_id,
                enable_llm=config.enable_llm_analysis,
            )

        elif config.mode == ArchitectureMode.AGGREGATE:
            # 模式二：同构多库聚合，启动完整多库服务
            return MultiDBAskService(
                mode="aggregate",
                enable_prediction=config.enable_prediction,
                enable_bigdata=config.enable_bigdata,
                clickhouse_cluster=config.clickhouse_cluster,
                enable_llm=config.enable_llm_analysis,
            )

        elif config.mode == ArchitectureMode.FEDERATED:
            # 模式三：异构多库联邦
            return MultiDBAskService(
                mode="federated",
                enable_prediction=config.enable_prediction,
                enable_llm=config.enable_llm_analysis,
            )

        raise ValueError(f"Unknown mode: {config.mode}")
```

---

## 十一、AI 增强分析（LLM 驱动的深度分析能力）

### 11.1 分析能力矩阵

现有文档中的预测主要依赖**统计/机器学习模型**（Prophet、XGBoost）。但在大数据分析场景下，**AI 大模型**（DeepSeek/Claude）可以提供更强大的分析能力：

| 分析类型 | 使用模型 | 何时调用 | 典型问题 |
|---------|---------|---------|---------|
| **SQL 生成** | DeepSeek Chat | 每次查询 | "统计全省营收" → SQL |
| **结果解读** | DeepSeek Chat | 查询返回后 | "这个数据说明了什么" |
| **异常分析** | DeepSeek Chat | 查询返回后 | "为什么宁波本月营收下降了 20%" |
| **对比分析** | DeepSeek Chat | 查询返回后 | "对比杭州和宁波的用户增长趋势" |
| **预测推理** | DeepSeek Chat | 用户要求时 | "基于这些数据预测下季度走势" |
| **多步推理** | DeepSeekreasoning | 复杂问题时 | "找出所有订单超时但未投诉的用户" |
| **时序预测** | Prophet/XGBoost | 用户要求时 | 量化预测（数学模型，更精确） |
| **异常检测** | Isolation Forest | 用户要求时 | 数据质量监控（无监督 ML） |

**核心设计原则**：AI 大模型负责**语义理解和推理**，统计/ML 模型负责**精确计算和预测**。两者互补，而非替代关系。

### 11.2 LLM 深度分析服务

```python
# src/micro_genbi/llm/analysis_service.py

from dataclasses import dataclass
from typing import Optional, Literal
import json

from .client import LLMClient


class AnalysisType(Literal["interpret", "compare", "anomaly", "forecast_reasoning", "sql_explain"]):
    """LLM 分析类型"""
    pass


@dataclass
class AnalysisResult:
    """分析结果"""
    type: AnalysisType
    conclusion: str          # 自然语言结论
    key_findings: list[str]  # 关键发现（bullet points）
    confidence: float        # 置信度 0~1
    suggestions: list[str]   # 建议
    chart_hints: dict | None # 可视化提示（如：推荐用折线图对比趋势）


class LLMAnalysisService:
    """
    LLM 深度分析服务。
    
    在查询结果返回后，根据分析类型调用 AI 大模型进行深度分析。
    与 PredictionService 的区别：
    - LLMAnalysisService：语义理解、自然语言解读、推理分析
    - PredictionService：数学模型、精确数值预测
    """

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def analyze(
        self,
        analysis_type: AnalysisType,
        user_query: str,
        query_result: list[dict],
        row_count: int,
        metadata: dict | None = None,
    ) -> AnalysisResult:
        """
        主分析入口。
        
        参数：
            analysis_type: 分析类型
            user_query: 原始用户查询
            query_result: 查询结果数据
            row_count: 结果行数
            metadata: 附加元数据（如：查询耗时、SQL、涉及的库）
        """
        prompt = self._build_prompt(analysis_type, user_query, query_result, row_count, metadata)
        response = await self.llm.generate(prompt, schema=AnalysisResult)

        return AnalysisResult(
            type=analysis_type,
            conclusion=response.get("conclusion", ""),
            key_findings=response.get("key_findings", []),
            confidence=response.get("confidence", 0.8),
            suggestions=response.get("suggestions", []),
            chart_hints=response.get("chart_hints"),
        )

    def _build_prompt(
        self, analysis_type: AnalysisType, user_query: str,
        query_result: list[dict], row_count: int, metadata: dict | None
    ) -> str:
        # 截断数据（避免 token 爆炸，只传摘要）
        summary = self._summarize_result(query_result)

        base = f"""你是一个数据分析专家。用户刚刚执行了一个数据查询，请进行深度分析。

## 用户原始问题
{user_query}

## 查询结果摘要（共 {row_count} 行）
{summary}

## 查询元数据
{json.dumps(metadata or {}, ensure_ascii=False, indent=2)}

"""

        prompts = {
            "interpret": base + """## 分析任务：结果解读
请解读这个查询结果，回答：
1. 整体数据反映了什么业务现象？
2. 有哪些关键数据点值得关注？
3. 与常规情况相比是否有异常？
请输出 JSON：
{
  "conclusion": "一句话总结",
  "key_findings": ["发现1", "发现2", "发现3"],
  "confidence": 0.85,
  "suggestions": ["建议1", "建议2"],
  "chart_hints": {"type": "bar", "description": "推荐柱状图展示TOP10"}
}""",

            "compare": base + """## 分析任务：对比分析
请对数据进行横向/纵向对比：
1. 各维度之间的差异有多大？
2. 是否有明显的高/低区域？
3. 差异背后的业务原因是什么？
请输出 JSON（同上格式）。""",

            "anomaly": base + """## 分析任务：异常分析
请识别数据中的异常点：
1. 哪些数据点明显偏离正常范围？
2. 异常的可能原因（给出 2~3 个假设）？
3. 需要进一步调查的方向？
请输出 JSON（同上格式）。""",

            "forecast_reasoning": base + """## 分析任务：预测推理
基于当前数据趋势，推理未来可能的变化：
1. 当前趋势会延续吗？
2. 下一步可能发生什么变化？
3. 需要关注哪些风险或机会？
请输出 JSON（同上格式），chart_hints 推荐折线图展示历史+预测。""",

            "sql_explain": base + """## 分析任务：SQL 解读
请解释这个查询的 SQL 逻辑及其业务含义：
1. 这个查询在计算什么？
2. SQL 的 WHERE 条件过滤了什么数据范围？
3. 有哪些 SQL 优化建议？
请输出 JSON（同上格式）。""",
        }

        return prompts.get(analysis_type, prompts["interpret"])

    def _summarize_result(self, data: list[dict]) -> str:
        """将查询结果压缩为摘要（不超过 500 字）"""
        if not data:
            return "（无数据）"

        if len(data) <= 5:
            return json.dumps(data, ensure_ascii=False, indent=2)

        # 计算统计摘要
        if data and isinstance(data[0], dict):
            # 取前3行 + 后2行作为样本
            sample = data[:3] + data[-2:]
            stats = {}
            for key in data[0]:
                if isinstance(data[0][key], (int, float)):
                    vals = [row.get(key, 0) for row in data if isinstance(row.get(key), (int, float))]
                    if vals:
                        stats[key] = {
                            "min": min(vals), "max": max(vals),
                            "avg": round(sum(vals) / len(vals), 2),
                            "sum": round(sum(vals), 2),
                        }

            return json.dumps({
                "sample_rows": sample,
                "statistics": stats,
                "total_rows": len(data),
            }, ensure_ascii=False, indent=2)
        return str(data[:5])
```

### 11.3 完整分析流程（从查询到解读）

```python
# src/micro_genbi/service/analytics_pipeline.py

"""
完整分析流程示例：

用户问："显示全省各子系统本月营收，并分析哪些城市表现异常"

Step 1: 查询执行
  → MultiDBAskService.execute() 
  → ExecutionEngine 并发查询所有同构库
  → 返回聚合数据

Step 2: 自动触发 LLM 分析（异常检测）
  → LLMAnalysisService.analyze("anomaly", ...)
  → LLM 识别出：宁波营收环比 -23%，杭州同比 +15%

Step 3: 用户追问："为什么宁波下降了"
  → LLMAnalysisService.analyze("interpret", ...)
  → LLM 结合上下文推理可能原因（淡季/人口流出/统计口径）

Step 4: 用户要求预测
  → PredictionService.predict() [数学模型]
  → Prophet 输出量化预测值

Step 5: 生成可视化
  → ChartEngine 根据 chart_hints 生成 ECharts 配置
  → 折线图：历史营收 + 预测值 + 置信区间
"""


class AnalyticsPipeline:
    """
    完整分析流水线。
    
    将查询执行、LLM 分析、预测、可视化串联成完整的数据分析体验。
    """

    def __init__(
        self,
        ask_service: "MultiDBAskService",
        analysis_svc: LLMAnalysisService,
        prediction_svc: "PredictionService",
        chart_svc: "ChartService",
    ):
        self.ask_svc = ask_service
        self.analysis_svc = analysis_svc
        self.prediction_svc = prediction_svc
        self.chart_svc = chart_svc

    async def full_analysis(
        self,
        user_query: str,
        session_id: str | None = None,
        auto_analyze: bool = True,
        enable_forecast: bool = False,
        forecast_periods: int = 3,
    ) -> dict:
        """
        完整分析流水线。
        
        参数：
            auto_analyze: 查询后自动执行 LLM 分析
            enable_forecast: 是否同时执行预测
            forecast_periods: 预测期数
        """
        # ── Step 1: 执行查询 ────────────────────────────────────
        query_result = await self.ask_svc.ask(
            user_query=user_query,
            session_id=session_id,
        )

        metadata = {
            "query_mode": query_result.get("query_mode"),
            "involved_dbs": query_result.get("involved_db_ids", []),
            "elapsed_ms": query_result.get("elapsed_ms"),
            "row_count": query_result.get("row_count"),
            "sql": query_result.get("sql"),
        }

        # ── Step 2: 自动 LLM 分析 ───────────────────────────────
        analysis_results = {}
        if auto_analyze and query_result.get("row_count", 0) > 0:
            # 并行执行多种分析（interpret + compare）
            import asyncio
            analysis_tasks = [
                self.analysis_svc.analyze("interpret", user_query,
                    query_result["data"], query_result["row_count"], metadata),
                self.analysis_svc.analyze("compare", user_query,
                    query_result["data"], query_result["row_count"], metadata),
            ]
            results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
            analysis_results = {
                "interpret": results[0] if not isinstance(results[0], Exception) else None,
                "compare": results[1] if not isinstance(results[1], Exception) else None,
            }

        # ── Step 3: 预测（如需要） ──────────────────────────────
        forecast_result = None
        if enable_forecast and query_result.get("row_count", 0) > 10:
            # 自动推断日期列和数值列
            date_col, value_col = self._infer_columns(query_result["data"])
            if date_col and value_col:
                forecast_result = await self.prediction_svc.predict(
                    data=query_result["data"],
                    date_column=date_col,
                    value_column=value_col,
                    periods=forecast_periods,
                )

        # ── Step 4: 生成可视化 ──────────────────────────────────
        # 优先使用 LLM 推荐的图表类型
        chart_hints = None
        if analysis_results.get("interpret"):
            chart_hints = analysis_results["interpret"].chart_hints
        chart_config = self.chart_svc.generate(
            data=query_result["data"],
            chart_type=chart_hints.get("type") if chart_hints else "auto",
            forecast=forecast_result,
        )

        # ── Step 5: 组装最终响应 ────────────────────────────────
        return {
            "query": {
                "sql": query_result.get("sql"),
                "row_count": query_result.get("row_count"),
                "elapsed_ms": query_result.get("elapsed_ms"),
                "data": query_result["data"][:10],  # 截断
            },
            "analysis": {
                key: {
                    "conclusion": r.conclusion if r else None,
                    "findings": r.key_findings if r else [],
                    "confidence": r.confidence if r else 0,
                    "suggestions": r.suggestions if r else [],
                }
                for key, r in analysis_results.items() if r
            },
            "forecast": {
                "model": forecast_result.model_name if forecast_result else None,
                "values": forecast_result.forecast_values if forecast_result else [],
                "dates": forecast_result.forecast_dates if forecast_result else [],
                "interpretation": forecast_result.interpretation if forecast_result else None,
                "confidence_lower": forecast_result.confidence_lower if forecast_result else [],
                "confidence_upper": forecast_result.confidence_upper if forecast_result else [],
            } if forecast_result else None,
            "chart": chart_config,
        }

    def _infer_columns(self, data: list[dict]) -> tuple[str | None, str | None]:
        """从数据中自动推断日期列和数值列"""
        if not data:
            return None, None
        row = data[0]
        date_col = None
        value_col = None
        for key, val in row.items():
            if isinstance(val, str) and any(x in key.lower() for x in ["date", "time", "month", "year", "day"]):
                date_col = key
            elif isinstance(val, (int, float)) and value_col is None:
                value_col = key
        return date_col, value_col
```

### 11.4 LLM + 大数据的技术边界

需要明确 **AI 大模型能做什么** 和 **不能做什么**：

| 场景 | AI 大模型能做 | AI 大模型不能做 | 正确方案 |
|------|-------------|---------------|---------|
| 异常分析 | 语义推理，找出异常的业务原因 | 精确计算偏离了多少σ | LLM 推理 + 统计检测 |
| 趋势预测 | 解读趋势，给出自然语言预测逻辑 | 精确的数值预测 | LLM 解读 + Prophet 计算 |
| 数据对比 | 找出差异点，推理差异原因 | 精确的百分比计算 | LLM 推理 + SQL 聚合 |
| 实时监控 | 生成告警分析报告 | 实时流式异常检测 | LLM 报告 + 规则引擎 |
| 大规模聚合 | 生成对应 SQL | 直接计算 1 亿行数据 | SQL 执行 + 归并展示 |

**结论**：AI 大模型是"分析大脑"，统计/ML 模型是"计算引擎"，数据库是"数据仓库"。三者各司其职，互补增强。

---

## 十二、部署架构

```
┌──────────────────────────────────────────────────────────────┐
│                      用户请求（Vue 前端）                     │
│               问：“显示全省各子系统本月营收”                  │
└──────────────────────────┬───────────────────────────────────┘
                           │ HTTPS
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                    Nginx / API Gateway                       │
│                  （限流 + SSL 终结 + 路由）                    │
└──────────────────────────┬───────────────────────────────────┘
                           │
           ┌───────────────┼───────────────────┐
           │               │                   │
           ▼               ▼                   ▼
    ┌────────────┐  ┌────────────┐    ┌────────────┐
    │ FastAPI    │  │ FastAPI    │    │ MCP Server │
    │ Worker #1  │  │ Worker #2  │    │ (JSON-RPC) │
    └─────┬──────┘  └─────┬──────┘    └────────────┘
          │               │
          └───────┬───────┘
                  │ asyncio并发
                  ▼
    ┌──────────────────────────────────────────────┐
    │            MultiDatabaseRouter                │
    │  ┌──────────────┐   ┌──────────────┐        │
    │  │ Aggregate    │   │ Federated     │        │
    │  │ Router       │   │ Router        │        │
    │  └──────┬───────┘   └──────┬───────┘        │
    └─────────┼──────────────────┼────────────────┘
              │                  │
     ┌────────┴───────┐  ┌──────┴───────┐
     │  AsyncIO Tasks │  │ AsyncIO Tasks│
     │  (并发拉取)     │  │ (并发拉取)    │
     └────────┬───────┘  └──────┬───────┘
              │                  │
    ┌─────────┼────────┐  ┌─────┼──────────────┐
    │ city_a  │city_b  │  │orders_db│financial_db│
    │  MySQL  │  PG    │  │  PG    │   MySQL     │
    └─────────┴────────┘  └────────┴─────────────┘

    ── 大数据路径（ClickHouse）────────────────────────
              │
    ┌─────────┴─────────────┐
    │  ClickHouse Cluster   │
    │  (集群聚合查询)        │
    │  SELECT cluster(...)   │
    └───────────────────────┘
```

---

## 十一、技术路径与实施计划

### 11.1 实施阶段划分

| 阶段 | 内容 | 优先级 | 依赖 | 工作量 |
|------|------|--------|------|--------|
| **Phase 0** | SchemaRegistry + 单库扩展（同构多库） | P0 | 无 | 1 周 |
| **Phase 1** | AggregateRouter + ExecutionEngine（场景 A） | P0 | Phase 0 | 1 周 |
| **Phase 2** | FederatedRouter + StreamJoin（场景 B） | P1 | Phase 0 | 1.5 周 |
| **Phase 3** | 预测服务（Statistics + Prophet） | P1 | Phase 1 | 1 周 |
| **Phase 4** | HybridRouter + ClickHouse 对接 | P2 | Phase 1+2 | 2 周 |
| **Phase 5** | 大屏展示（ECharts 时序图 + 地图） | P1 | Phase 3 | 1 周 |

### 11.2 与现有架构的融合

当前 `Micro-GenBI-Integration.md` 中已定义的组件，需要按如下方式扩展：

```
现有架构                    扩展后
──────────────────────────────────────────────────────────
AskService             → MultiDBAskService（新增）
schema.yaml            → schema_registry/（目录结构）
SQLAgentExecutor      → ExecutionEngine（新增多库执行）
SingleRouter          → MultiDatabaseRouter（新增）
ChartEngine           → ChartEngine + PredictionService（新增）
FastAPI               → 无变化（接口不变）
```

---

## 十二、配置示例

### 12.1 省系统多库配置示例

```
schema_registry/
├── _global.yaml
│   # 全局字典表（所有库共享）
│   dict_tables:
│     - city_code_mapping  # 城市编码映射表
│     - industry_classification  # 行业分类
│
├── province_headquarters/
│   ├── metadata.yaml       # 主库（省厅）
│   └── tables/
│       ├── kpi_summary.yaml
│       └── system_config.yaml
│
├── city_hangzhou/
│   ├── metadata.yaml
│   │   db_category: "sibling"
│   │   siblings_group: "province_siblings"
│   │   is_aggregation_source: true
│   └── tables/
│       ├── orders.yaml
│       └── users.yaml
│
├── city_ningbo/
│   ├── metadata.yaml
│   │   db_category: "sibling"
│   │   siblings_group: "province_siblings"
│   │   is_aggregation_source: true
│   └── tables/
│       └── orders.yaml
│
└── financial_db/
    ├── metadata.yaml
    │   db_category: "heterogenous"
    │   is_aggregation_source: false
    └── tables/
        └── payments.yaml
            cross_db_relations:
              - target_table: "city_hangzhou.orders"
                join_column: "order_id"
                cardinality: "one_to_one"
                description: "支付记录与杭州订单关联"
```

---

## 十三、总结

### 13.1 核心设计要点

1. **SchemaRegistry** 是多库架构的核心，通过目录化配置实现每个数据库的语义隔离
2. **QueryMode 决策树** 自动区分单库 / 聚合 / 联邦 / 混合 四种模式
3. **ExecutionEngine 并发执行** 是性能关键，`asyncio.gather` 实现无感并行
4. **结果归并策略** 根据数据量和 JOIN 类型选择：UNION ALL / Stream Join / Materialized Join
5. **PredictionService** 作为独立模块，支持 Statistics（轻量）和 Prophet（精确）渐进增强
6. **LLMAnalysisService** 作为 AI 分析大脑，与数学模型互补（LLM 负责语义推理，ML 负责精确计算）
7. **三模式配置系统** 让用户在部署时选择适合的架构（单库 / 同构聚合大屏 / 异构联邦），配置即生效

### 13.2 技术选型建议

| 场景 | 数据规模 | 推荐方案 | 理由 |
|------|---------|---------|------|
| < 10 个同构库 | < 100 万行/库 | Python 并行（现有 ExecutionEngine） | 无额外依赖 |
| 10~50 个同构库 | 百万~千万行 | PostgreSQL FDW | 无需改应用代码 |
| > 50 个同构库 | 亿级数据 | ClickHouse Cluster | 超大数据，亚秒查询 |
| 2~5 个异构库 | 中等 | Python 流式归并 | 灵活，支持任意 JOIN |
| 异构库 + 大数据 | 任意 | ClickHouse + FDW 混合 | 兼顾灵活性与性能 |

### 13.3 待明确事项

在正式实施前需要确认以下业务细节：

1. **具体有多少个子系统数据库？** → 决定采用 Python 并行还是 ClickHouse
2. **表结构是否真的完全相同？** → 决定场景 A（完全同构）还是场景 C（混合）
3. **是否需要实时 CDC 同步？** → 决定是否引入 Kafka + Debezium
4. **预测的精度要求？** → 决定使用 Statistics 还是 Prophet/XGBoost
5. **数据安全要求？** → 决定是否需要库级 ACL 和数据脱敏
6. **是否需要 LLM 深度分析？** → 决定是否启用 LLMAnalysisService（需要额外 token 预算）

---

*本文档为 Micro-GenBI 多库查询架构的完整设计方案，涵盖需求分析、技术架构、核心组件实现、部署方案和实施计划。*
