"""多数据库路由器

根据 SchemaRegistry 和跨库关联配置，自动判断查询类型并生成执行计划。

核心策略：「必须配置才能查询」
- 单库查询：无需配置，直接路由到指定数据库
- 同构多库聚合：需要 ConnectionGroup 配置（siblings_group 标记同构库）
- 异构多库联邦：需要 CrossDBRelation 配置（手动建立 DB 间 JOIN 关系）

未配置的跨库查询 → 直接拒绝，避免 LLM 幻觉生成错误的 JOIN 条件。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import logging

from micro_genbi.database import DatabaseConnectionService, CrossDBRelationService, ConnectionGroupService

logger = logging.getLogger(__name__)


class QueryMode(str, Enum):
    """查询模式"""
    SINGLE = "single"        # 单库查询
    AGGREGATE = "aggregate"  # 同构多库聚合
    FEDERATED = "federated"  # 异构多库联邦


@dataclass
class SubQueryPlan:
    """单个数据库的子查询计划"""
    connection_id: str          # DatabaseConnection UUID
    connection_name: str       # 连接名称（用于显示）
    connection_type: str        # 数据库类型（postgresql/mysql/sqlite）
    sql: str                   # 生成的 SQL（LLM 输出）
    source_table: str           # 涉及的源表
    merge_column: str          # 归并列（如 city_code）
    description: str = ""       # 描述


@dataclass
class QueryPlan:
    """
    完整的多库查询执行计划。

    示例（单库）：
        mode = SINGLE
        sub_plans = [{connection_id, sql}]
        final_sql = sql

    示例（同构聚合）：
        mode = AGGREGATE
        sub_plans = [
            {conn_id=A, sql="SELECT city_code, SUM(amount) AS total FROM orders GROUP BY city_code WHERE ..."},
            {conn_id=B, sql="SELECT city_code, SUM(amount) AS total FROM orders GROUP BY city_code WHERE ..."},
        ]
        final_sql = "SELECT city_code, SUM(total) FROM (sub1 UNION ALL sub2) GROUP BY city_code"
        merge_strategy = "union_all"

    示例（异构联邦）：
        mode = FEDERATED
        sub_plans = [
            {conn_id=orders, sql="SELECT order_id, amount FROM orders WHERE ..."},
            {conn_id=payments, sql="SELECT order_id, status FROM payments WHERE ..."},
        ]
        final_sql = None（Python 层归并）
        merge_strategy = "stream_join"
    """
    mode: QueryMode
    is_multi_db: bool
    sub_plans: list[SubQueryPlan] = field(default_factory=list)
    final_sql: str | None = None
    merge_strategy: str = "none"   # none | union_all | stream_join
    involved_connection_ids: list[str] = field(default_factory=list)
    description: str = ""           # 自然语言描述（调试用）

    @property
    def single_connection_id(self) -> str | None:
        """单库模式时返回 connection_id"""
        if self.mode == QueryMode.SINGLE and self.sub_plans:
            return self.sub_plans[0].connection_id
        return None


class MultiDatabaseRouter:
    """
    多数据库路由器主入口。

    核心职责：
    1. 根据查询涉及的表，自动判断查询模式（SINGLE / AGGREGATE / FEDERATED）
    2. 验证跨库关联是否已配置（未配置则拒绝，防止 LLM 幻觉）
    3. 生成 SubQueryPlan 列表（每个数据库一条 SQL）

    「必须配置才能查询」策略：
    - 同构多库：必须有 ConnectionGroup 配置
    - 异构跨库：必须有 CrossDBRelation 配置
    """

    def __init__(
        self,
        session,                    # AsyncSession from FastAPI dependency
        default_connection_id: str | None = None,
    ):
        self.session = session
        self.default_connection_id = default_connection_id
        self._db_service = DatabaseConnectionService(session)
        self._rel_service = CrossDBRelationService(session)
        self._grp_service = ConnectionGroupService(session)
        self._connections_cache: dict[str, dict] = {}
        self._relations_cache: list[dict] = []
        self._groups_cache: list[dict] = []

    async def _ensure_cache(self, tenant_id: str):
        """延迟加载数据到缓存"""
        if not self._connections_cache:
            connections = await self._db_service.get_by_tenant(tenant_id)
            self._connections_cache = {c.id: c for c in connections}

            rels = await self._rel_service.list_relations(tenant_id)
            self._relations_cache = [dict(
                source_connection_id=r.source_connection_id,
                source_table=r.source_table,
                source_column=r.source_column,
                target_connection_id=r.target_connection_id,
                target_table=r.target_table,
                target_column=r.target_column,
                cardinality=r.cardinality,
                name=r.name,
            ) for r in rels]

            groups = await self._grp_service.list_groups(tenant_id)
            self._groups_cache = []
            for g in groups:
                members = await self._grp_service.get_group_members(g.id)
                self._groups_cache.append(dict(
                    id=g.id,
                    name=g.name,
                    display_name=g.display_name,
                    mode=g.mode,
                    members=[dict(id=m.connection_id, city_code=m.city_code) for m in members],
                ))

    def _get_connection(self, conn_id: str) -> Optional[dict]:
        """根据 ID 获取连接信息"""
        conn = self._connections_cache.get(conn_id)
        if conn:
            return dict(
                id=conn.id,
                name=conn.name,
                db_type=conn.db_type,
                host=conn.host,
                port=conn.port,
                database_name=conn.database_name,
            )
        return None

    def _get_connections_by_ids(self, conn_ids: list[str]) -> list[dict]:
        """根据 ID 列表批量获取连接"""
        return [
            self._get_connection(cid) for cid in conn_ids
            if self._get_connection(cid)
        ]

    def _get_relations_between(self, conn_a: str, conn_b: str) -> list[dict]:
        """获取两个数据库之间的所有跨库关联"""
        return [
            r for r in self._relations_cache
            if (r["source_connection_id"] == conn_a and r["target_connection_id"] == conn_b)
            or (r["source_connection_id"] == conn_b and r["target_connection_id"] == conn_a)
        ]

    def _get_relations_for_connection(self, conn_id: str) -> list[dict]:
        """获取涉及某连接的所有跨库关联"""
        return [
            r for r in self._relations_cache
            if r["source_connection_id"] == conn_id or r["target_connection_id"] == conn_id
        ]

    def _get_groups_for_connection(self, conn_id: str) -> list[dict]:
        """获取某连接所属的所有分组"""
        return [
            g for g in self._groups_cache
            if any(m["id"] == conn_id for m in g.get("members", []))
        ]

    async def route(
        self,
        user_query: str,
        tables: list[str],
        tenant_id: str,
        requested_connection_id: str | None = None,
    ) -> QueryPlan:
        """
        主路由入口。

        Args:
            user_query: 用户自然语言查询
            tables: 涉及的表名列表（逻辑名）
            tenant_id: 租户 ID（用于加载配置）
            requested_connection_id: 用户在界面上选择的数据源 ID（可空）

        Returns:
            QueryPlan: 完整的执行计划

        路由决策树：
        1. requested_connection_id 明确 → SINGLE（单库）
        2. tables 涉及的表分布在多个 connection →
           a. 全部属于同一 siblings_group → AGGREGATE（同构聚合）
           b. 涉及跨 DB 的表对但无 CrossDBRelation 配置 → 拒绝
           c. 涉及跨 DB 的表对且有 CrossDBRelation 配置 → FEDERATED
        3. 无 tables 信息，requested_connection_id 明确 → SINGLE
        4. 无任何信息 → 使用 default_connection_id → SINGLE
        """
        await self._ensure_cache(tenant_id)

        query_lower = user_query.lower()

        # ── 策略 1: 明确指定了数据源 → 单库查询 ───────────────
        if requested_connection_id:
            conn = self._get_connection(requested_connection_id)
            if not conn:
                return QueryPlan(
                    mode=QueryMode.SINGLE,
                    is_multi_db=False,
                    description=f"数据源 {requested_connection_id} 不存在",
                )
            return QueryPlan(
                mode=QueryMode.SINGLE,
                is_multi_db=False,
                sub_plans=[SubQueryPlan(
                    connection_id=conn["id"],
                    connection_name=conn["name"],
                    connection_type=conn["db_type"],
                    sql="",    # SQL 由 LLM 生成
                    source_table="",
                    merge_column="",
                    description=f"单库查询（{conn['name']}）",
                )],
                involved_connection_ids=[requested_connection_id],
                description=f"单库查询：{conn['name']}",
            )

        # ── 策略 2: 根据表名推断涉及的连接 ─────────────────
        if tables:
            # 简化实现：按表名中的约定前缀推断
            # 实际应由 SemanticRetriever 从 SchemaRegistry 获取
            conn_ids = self._infer_connections_from_tables(tables)
            if not conn_ids:
                # 无法推断，退到默认连接
                return await self._route_to_default()

            if len(conn_ids) == 1:
                # 单库
                conn = self._get_connection(conn_ids[0])
                return QueryPlan(
                    mode=QueryMode.SINGLE,
                    is_multi_db=False,
                    sub_plans=[SubQueryPlan(
                        connection_id=conn["id"],
                        connection_name=conn["name"],
                        connection_type=conn["db_type"],
                        sql="",
                        source_table="",
                        merge_column="",
                        description=f"单库查询（{conn['name']}）",
                    )],
                    involved_connection_ids=conn_ids,
                    description=f"单库查询：{conn['name']}",
                )

            # 多库：检查是否为同构聚合
            groups = self._get_groups_for_connection(conn_ids[0])
            same_group = [
                g for g in groups
                if all(cid in [m["id"] for m in g.get("members", [])] for cid in conn_ids)
                and len(conn_ids) > 1
            ]
            if same_group and same_group[0]["mode"] == "aggregate":
                # 同构多库聚合
                group = same_group[0]
                sub_plans = []
                for member in group.get("members", []):
                    conn = self._get_connection(member["id"])
                    if conn:
                        sub_plans.append(SubQueryPlan(
                            connection_id=conn["id"],
                            connection_name=conn["name"],
                            connection_type=conn["db_type"],
                            sql="",
                            source_table=tables[0] if tables else "",
                            merge_column=member.get("city_code", ""),
                            description=f"同构聚合（{conn['name']}）",
                        ))
                return QueryPlan(
                    mode=QueryMode.AGGREGATE,
                    is_multi_db=True,
                    sub_plans=sub_plans,
                    merge_strategy="union_all",
                    involved_connection_ids=conn_ids,
                    description=f"同构多库聚合：{group['display_name']}（{len(sub_plans)} 个库）",
                )

            # 异构跨库：检查关联配置
            all_rels = []
            for cid_a in conn_ids:
                for cid_b in conn_ids:
                    if cid_a < cid_b:
                        rels = self._get_relations_between(cid_a, cid_b)
                        all_rels.extend(rels)

            if len(conn_ids) > 1 and not all_rels:
                # 核心策略：未配置跨库关联 → 直接拒绝
                conn_names = [self._get_connection(c).get("name", c) for c in conn_ids]
                logger.warning(
                    f"跨库查询被拒绝（未配置 CrossDBRelation）："
                    f"{conn_names}，tables={tables}"
                )
                return QueryPlan(
                    mode=QueryMode.FEDERATED,
                    is_multi_db=True,
                    description=(
                        f"查询涉及多个数据库（{', '.join(conn_names)}），"
                        f"但尚未配置跨库关联关系。请在「跨库关联」页面配置关联后重试。"
                    ),
                    involved_connection_ids=conn_ids,
                )

            # 异构联邦（有配置）
            sub_plans = []
            for cid in conn_ids:
                conn = self._get_connection(cid)
                if conn:
                    sub_plans.append(SubQueryPlan(
                        connection_id=conn["id"],
                        connection_name=conn["name"],
                        connection_type=conn["db_type"],
                        sql="",
                        source_table="",
                        merge_column="",
                        description=f"异构联邦（{conn['name']}）",
                    ))
            return QueryPlan(
                mode=QueryMode.FEDERATED,
                is_multi_db=True,
                sub_plans=sub_plans,
                merge_strategy="stream_join",
                involved_connection_ids=conn_ids,
                description=f"异构多库联邦：{len(sub_plans)} 个库",
            )

        # ── 策略 3: 退到默认连接 ──────────────────────────
        return await self._route_to_default()

    async def _route_to_default(self) -> QueryPlan:
        """路由到默认连接"""
        if self.default_connection_id:
            conn = self._get_connection(self.default_connection_id)
            if conn:
                return QueryPlan(
                    mode=QueryMode.SINGLE,
                    is_multi_db=False,
                    sub_plans=[SubQueryPlan(
                        connection_id=conn["id"],
                        connection_name=conn["name"],
                        connection_type=conn["db_type"],
                        sql="",
                        source_table="",
                        merge_column="",
                        description=f"默认数据库（{conn['name']}）",
                    )],
                    involved_connection_ids=[self.default_connection_id],
                    description=f"单库查询（默认）：{conn['name']}",
                )

        return QueryPlan(
            mode=QueryMode.SINGLE,
            is_multi_db=False,
            description="未配置数据源",
        )

    def _infer_connections_from_tables(self, tables: list[str]) -> list[str]:
        """
        从表名推断涉及的连接 ID。

        简化策略（后续由 SemanticRetriever 替换）：
        - 表名格式约定：`conn_prefix__table_name`（例如：`orders__order_detail`）
        - 或通过 SchemaRegistry 的表名 → connection_id 映射推断
        """
        # 如果只有一个表，返回所有连接的交集
        if len(tables) <= 1:
            return list(self._connections_cache.keys())[:1] if self._connections_cache else []

        # 多表：检查是否有任何跨库关联可以连接它们
        # 简化为：所有涉及的连接
        all_conn_ids = set()
        for table in tables:
            table_lower = table.lower()
            # 检查表名中的前缀约定
            for conn_id, conn in self._connections_cache.items():
                if table_lower.startswith(conn_id.lower()[:8]):
                    all_conn_ids.add(conn_id)
                    break

        # 如果前缀推断没有结果，尝试关联推断
        if not all_conn_ids and len(tables) > 1:
            # 检查这些表是否通过跨库关联连接
            connected = set()
            for rel in self._relations_cache:
                # 如果两个表都涉及关联的两端，则它们需要同一个连接
                pass  # 简化：返回所有连接
            all_conn_ids = set(self._connections_cache.keys())

        return list(all_conn_ids) if all_conn_ids else []

    def get_query_mode_for_display(self, plan: QueryPlan) -> tuple[str, str, str]:
        """
        获取用于 UI 显示的查询模式信息。

        Returns:
            (emoji, title, color)
        """
        if plan.mode == QueryMode.SINGLE:
            return "1️⃣", "单库查询", "#3E6AE1"
        elif plan.mode == QueryMode.AGGREGATE:
            return "N️⃣", "同构多库聚合", "#10B981"
        elif plan.mode == QueryMode.FEDERATED:
            return "🔗", "异构多库联邦", "#F59E0B"
        return "❓", "未知模式", "#8E8E8E"
