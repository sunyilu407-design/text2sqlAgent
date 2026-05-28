"""Big Data Router for automatic connector selection based on query scale.

Routes queries to appropriate connectors based on database count,
estimated rows, and complexity to optimize performance and resource usage.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from micro_genbi.errors import GenBIError

logger = logging.getLogger(__name__)


class ConnectorType(str, Enum):
    """Supported connector types for big data operations."""
    ASYNC_PARALLEL = "async_parallel"    # Python asyncio (small scale)
    FDW = "fdw"                          # PostgreSQL FDW (medium scale)
    FDW_PARTITIONED = "fdw_partitioned"  # FDW with partitioning (large scale)
    CLICKHOUSE = "clickhouse"            # ClickHouse cluster (xlarge scale)


class QueryScale(str, Enum):
    """Query scale classification."""
    SMALL = "small"      # < 10 databases
    MEDIUM = "medium"    # 10-50 databases
    LARGE = "large"      # 50-200 databases
    XLARGE = "xlarge"    # > 200 databases or > 100M rows


@dataclass
class QueryPlan:
    """
    Query execution plan for a specific connector.

    Attributes:
        strategy: Execution strategy name.
        sql_templates: List of SQL templates to execute.
        execution_order: Ordered list of execution steps.
        merge_strategy: How to merge results ("union", "join", "aggregate").
        partition_info: Optional partitioning details.
        estimated_nodes: Number of nodes to involve.
    """
    strategy: str
    sql_templates: list[str] = field(default_factory=list)
    execution_order: list[str] = field(default_factory=list)
    merge_strategy: str = "union"
    partition_info: Optional[dict[str, Any]] = None
    estimated_nodes: int = 1


@dataclass
class RouteDecision:
    """
    Decision made by the router for query execution.

    Attributes:
        connector_type: Selected connector type.
        scale: Classified query scale.
        query_plan: Generated execution plan.
        reason: Human-readable explanation of the routing decision.
        estimated_duration_ms: Estimated execution time in milliseconds.
        fallback_available: Whether a fallback to smaller scale exists.
    """
    connector_type: ConnectorType
    scale: QueryScale
    query_plan: QueryPlan
    reason: str
    estimated_duration_ms: int
    fallback_available: bool = True


class BigDataRouterError(GenBIError):
    """Big Data Router error."""
    pass


@dataclass
class RouterConfig:
    """Configuration for Big Data Router."""
    # Scale thresholds
    small_threshold: int = 10           # Max databases for async_parallel
    medium_threshold: int = 50            # Max databases for FDW
    large_threshold: int = 200           # Max databases for FDW with partitioning
    row_count_threshold: int = 100_000_000  # 100M rows threshold for ClickHouse

    # Timeout settings (ms)
    async_timeout: int = 30_000         # 30 seconds
    fdw_timeout: int = 120_000          # 2 minutes
    partitioned_timeout: int = 300_000   # 5 minutes
    clickhouse_timeout: int = 600_000   # 10 minutes

    # Feature flags
    enable_clickhouse: bool = True
    enable_fdw_partitioning: bool = True
    auto_fallback: bool = True


class BigDataRouter:
    """
    Automatic route selection for big data queries.

    Analyzes query characteristics and infrastructure scale to select
    the optimal connector and execution strategy.

    Scale Thresholds:
        - small:   < 10 databases  → async_parallel (Python asyncio)
        - medium:  10-50 databases → FDW (PostgreSQL Foreign Data Wrapper)
        - large:   50-200 databases → FDW + Partitioning
        - xlarge:  > 200 databases OR > 100M rows → ClickHouse

    Example:
        >>> router = BigDataRouter({"small_threshold": 5, "enable_clickhouse": True})
        >>> decision = router.route(
        ...     query="SELECT COUNT(*) FROM orders",
        ...     db_count=25,
        ...     estimated_rows=500_000
        ... )
        >>> print(f"Selected: {decision.connector_type}")
    """

    def __init__(self, config: Optional[dict[str, Any]] = None):
        """
        Initialize Big Data Router.

        Args:
            config: Optional configuration dict. Defaults to RouterConfig values.
        """
        self.config = RouterConfig()

        if config:
            # Apply custom config
            for key, value in config.items():
                if hasattr(self.config, key):
                    setattr(self.config, key, value)

        # Initialize connector registry
        self._connectors: dict[ConnectorType, Any] = {}

        # Estimated durations per scale (ms)
        self._duration_estimates = {
            QueryScale.SMALL: 1000,      # ~1s per db
            QueryScale.MEDIUM: 5000,     # ~200ms per db
            QueryScale.LARGE: 15000,    # ~75ms per db
            QueryScale.XLARGE: 30000,   # ClickHouse optimized
        }

    def register_connector(
        self,
        connector_type: ConnectorType,
        connector: Any,
    ) -> None:
        """
        Register a connector instance for a type.

        Args:
            connector_type: Type to register.
            connector: Connector instance implementing BigDataConnector.
        """
        self._connectors[connector_type] = connector
        logger.debug("Registered connector: %s", connector_type.value)

    def _estimate_scale(
        self,
        db_count: int,
        estimated_rows: int,
    ) -> QueryScale:
        """
        Estimate query scale based on database count and row estimate.

        Args:
            db_count: Number of databases involved.
            estimated_rows: Estimated result rows.

        Returns:
            Classified query scale.
        """
        # Check row count threshold first (always triggers xlarge)
        if estimated_rows >= self.config.row_count_threshold:
            return QueryScale.XLARGE

        # Check database count thresholds
        if db_count < self.config.small_threshold:
            return QueryScale.SMALL
        elif db_count < self.config.medium_threshold:
            return QueryScale.MEDIUM
        elif db_count < self.config.large_threshold:
            return QueryScale.LARGE
        else:
            return QueryScale.XLARGE

    def _select_connector(self, scale: QueryScale) -> ConnectorType:
        """
        Select appropriate connector type for the scale.

        Args:
            scale: Query scale classification.

        Returns:
            Connector type to use.
        """
        connector_mapping = {
            QueryScale.SMALL: ConnectorType.ASYNC_PARALLEL,
            QueryScale.MEDIUM: ConnectorType.FDW,
            QueryScale.LARGE: ConnectorType.FDW_PARTITIONED,
            QueryScale.XLARGE: ConnectorType.CLICKHOUSE,
        }

        connector = connector_mapping.get(scale, ConnectorType.ASYNC_PARALLEL)

        # Check if connector is available and enabled
        if connector == ConnectorType.CLICKHOUSE and not self.config.enable_clickhouse:
            logger.warning("ClickHouse disabled, falling back to FDW_PARTITIONED")
            connector = ConnectorType.FDW_PARTITIONED

        if connector == ConnectorType.FDW_PARTITIONED and not self.config.enable_fdw_partitioning:
            logger.warning("FDW partitioning disabled, falling back to FDW")
            connector = ConnectorType.FDW

        return connector

    def _build_query_plan(
        self,
        query: str,
        connector_type: ConnectorType,
        db_count: int,
        estimated_rows: int = 0,
    ) -> QueryPlan:
        """
        Build execution plan for the selected connector.

        Args:
            query: Original SQL query.
            connector_type: Selected connector type.
            db_count: Number of databases.
            estimated_rows: Estimated result rows.

        Returns:
            Query execution plan.
        """
        if connector_type == ConnectorType.ASYNC_PARALLEL:
            return self._build_async_plan(query, db_count)

        elif connector_type == ConnectorType.FDW:
            return self._build_fdw_plan(query, db_count)

        elif connector_type == ConnectorType.FDW_PARTITIONED:
            return self._build_partitioned_plan(query, db_count)

        elif connector_type == ConnectorType.CLICKHOUSE:
            return self._build_clickhouse_plan(query, db_count, estimated_rows)

        # Default fallback
        return QueryPlan(
            strategy="fallback_async",
            sql_templates=[query],
            execution_order=["execute"],
            merge_strategy="union",
        )

    def _build_async_plan(
        self,
        query: str,
        db_count: int,
    ) -> QueryPlan:
        """Build plan for async parallel execution."""
        return QueryPlan(
            strategy="async_parallel",
            sql_templates=[query],
            execution_order=[
                "create_tasks",
                "execute_parallel",
                "collect_results",
                "merge_union",
            ],
            merge_strategy="union",
            estimated_nodes=db_count,
        )

    def _build_fdw_plan(
        self,
        query: str,
        db_count: int,
    ) -> QueryPlan:
        """Build plan for FDW execution."""
        return QueryPlan(
            strategy="foreign_data_wrapper",
            sql_templates=[query],
            execution_order=[
                "setup_servers",
                "create_foreign_tables",
                "create_union_view",
                "execute_query",
                "cleanup_view",
            ],
            merge_strategy="union",
            partition_info={
                "method": "by_database",
                "partition_count": db_count,
            },
            estimated_nodes=db_count,
        )

    def _build_partitioned_plan(
        self,
        query: str,
        db_count: int,
    ) -> QueryPlan:
        """Build plan for FDW with partitioning."""
        # Calculate partition size based on db_count
        # Group databases into batches for better performance
        batch_size = max(10, db_count // 20)  # ~5% batches
        partition_count = (db_count + batch_size - 1) // batch_size

        return QueryPlan(
            strategy="fdw_partitioned",
            sql_templates=[query],
            execution_order=[
                "analyze_query",
                "create_partition_views",
                "execute_partition_batch",
                "merge_partition_results",
                "cleanup_partitions",
            ],
            merge_strategy="aggregate",
            partition_info={
                "method": "by_database_group",
                "batch_size": batch_size,
                "partition_count": partition_count,
            },
            estimated_nodes=db_count,
        )

    def _build_clickhouse_plan(
        self,
        query: str,
        db_count: int,
        estimated_rows: int,
    ) -> QueryPlan:
        """Build plan for ClickHouse execution."""
        return QueryPlan(
            strategy="clickhouse_cluster",
            sql_templates=[query],
            execution_order=[
                "route_to_coordinator",
                "execute_distributed",
                "merge_results",
            ],
            merge_strategy="aggregate",
            partition_info={
                "method": "distributed_table",
                "source_db_count": db_count,
                "estimated_rows": estimated_rows,
            },
            estimated_nodes=max(1, db_count // 10),  # Sample nodes
        )

    def route(
        self,
        query: str,
        db_count: int,
        estimated_rows: int = 0,
        force_connector: Optional[ConnectorType] = None,
    ) -> RouteDecision:
        """
        Route a query to the appropriate connector.

        Args:
            query: SQL query to route.
            db_count: Number of databases involved.
            estimated_rows: Estimated result rows (for scale estimation).
            force_connector: Optional connector override.

        Returns:
            RouteDecision with selected connector and execution plan.

        Raises:
            BigDataRouterError: If routing fails.

        Example:
            >>> decision = router.route(
            ...     query="SELECT * FROM orders WHERE date > '2024-01-01'",
            ...     db_count=30,
            ...     estimated_rows=1_000_000
            ... )
            >>> if decision.connector_type == ConnectorType.FDW:
            ...     # Execute using FDW
        """
        if db_count <= 0:
            raise BigDataRouterError("db_count must be positive")

        try:
            # Estimate scale
            scale = self._estimate_scale(db_count, estimated_rows)
            logger.debug(
                "Scale estimation: db_count=%d, rows=%d -> %s",
                db_count, estimated_rows, scale.value
            )

            # Select connector
            connector_type = force_connector or self._select_connector(scale)
            logger.debug("Selected connector: %s", connector_type.value)

            # Build execution plan
            query_plan = self._build_query_plan(
                query, connector_type, db_count, estimated_rows
            )

            # Estimate duration
            base_duration = self._duration_estimates.get(
                scale, self._duration_estimates[QueryScale.MEDIUM]
            )
            # Adjust for actual connector
            if connector_type == ConnectorType.ASYNC_PARALLEL:
                duration = base_duration * db_count
            elif connector_type == ConnectorType.FDW:
                duration = base_duration
            elif connector_type == ConnectorType.FDW_PARTITIONED:
                duration = base_duration * 2
            else:  # ClickHouse
                duration = base_duration

            # Determine fallback availability
            fallback_available = scale != QueryScale.SMALL or self.config.auto_fallback

            # Build reason string
            reason = self._build_reason_string(
                scale, connector_type, db_count, estimated_rows
            )

            return RouteDecision(
                connector_type=connector_type,
                scale=scale,
                query_plan=query_plan,
                reason=reason,
                estimated_duration_ms=duration,
                fallback_available=fallback_available,
            )

        except Exception as e:
            raise BigDataRouterError(f"Routing failed: {e}") from e

    def _build_reason_string(
        self,
        scale: QueryScale,
        connector_type: ConnectorType,
        db_count: int,
        estimated_rows: int,
    ) -> str:
        """Build human-readable reason for routing decision."""
        reasons = []

        if scale == QueryScale.SMALL:
            reasons.append(
                f"Small scale: {db_count} database(s) is below threshold "
                f"({self.config.small_threshold})"
            )
            reasons.append("Using async parallel execution for lowest latency")
        elif scale == QueryScale.MEDIUM:
            reasons.append(
                f"Medium scale: {db_count} databases in range "
                f"({self.config.small_threshold}-{self.config.medium_threshold})"
            )
            reasons.append("Using PostgreSQL FDW for server-side aggregation")
        elif scale == QueryScale.LARGE:
            reasons.append(
                f"Large scale: {db_count} databases exceeds FDW threshold"
            )
            reasons.append("Using FDW with partitioning for batched execution")
        else:  # XLARGE
            if estimated_rows >= self.config.row_count_threshold:
                reasons.append(
                    f"Very large result set: {estimated_rows:,} rows exceeds "
                    f"{self.config.row_count_threshold:,} threshold"
                )
            else:
                reasons.append(
                    f"Very large scale: {db_count} databases exceeds "
                    f"{self.config.large_threshold} threshold"
                )
            reasons.append("Using ClickHouse for high-performance analytics")

        return ". ".join(reasons)

    def get_recommended_config(self, scale: QueryScale) -> dict[str, Any]:
        """
        Get recommended configuration for a scale.

        Args:
            scale: Query scale.

        Returns:
            Dictionary with recommended settings.
        """
        configs = {
            QueryScale.SMALL: {
                "connector": "async_parallel",
                "pool_size": min(20, self.config.small_threshold * 2),
                "timeout_ms": self.config.async_timeout,
                "batch_size": 5,
                "retry_count": 3,
            },
            QueryScale.MEDIUM: {
                "connector": "fdw",
                "pool_size": min(50, self.config.medium_threshold),
                "timeout_ms": self.config.fdw_timeout,
                "use_connection_pool": True,
                "retry_count": 2,
            },
            QueryScale.LARGE: {
                "connector": "fdw_partitioned",
                "pool_size": self.config.large_threshold,
                "timeout_ms": self.config.partitioned_timeout,
                "partition_batch_size": 10,
                "retry_count": 1,
            },
            QueryScale.XLARGE: {
                "connector": "clickhouse",
                "pool_size": 10,
                "timeout_ms": self.config.clickhouse_timeout,
                "use_materialized_views": True,
                "retry_count": 0,  # ClickHouse handles retries
            },
        }

        return configs.get(scale, configs[QueryScale.MEDIUM])

    def compare_connectors(
        self,
        db_count: int,
        estimated_rows: int,
    ) -> list[dict[str, Any]]:
        """
        Compare all connector options for given parameters.

        Args:
            db_count: Number of databases.
            estimated_rows: Estimated result rows.

        Returns:
            List of comparison results for each connector.
        """
        scale = self._estimate_scale(db_count, estimated_rows)
        results = []

        for connector_type in ConnectorType:
            # Skip disabled connectors
            if connector_type == ConnectorType.CLICKHOUSE and not self.config.enable_clickhouse:
                continue
            if connector_type == ConnectorType.FDW_PARTITIONED and not self.config.enable_fdw_partitioning:
                continue

            plan = self._build_query_plan("", connector_type, db_count, estimated_rows)
            recommended = self.get_recommended_config(scale)

            results.append({
                "connector_type": connector_type.value,
                "scale_match": connector_type == self._select_connector(scale),
                "recommended": recommended.get("connector") == connector_type.value,
                "estimated_duration_ms": self._duration_estimates.get(scale, 5000),
                "query_plan": plan,
            })

        return results

    def explain_routing(
        self,
        query: str,
        db_count: int,
        estimated_rows: int = 0,
    ) -> str:
        """
        Get detailed explanation of routing decision.

        Args:
            query: SQL query.
            db_count: Number of databases.
            estimated_rows: Estimated result rows.

        Returns:
            Formatted explanation string.
        """
        decision = self.route(query, db_count, estimated_rows)

        lines = [
            "=" * 60,
            "BIG DATA ROUTER EXPLANATION",
            "=" * 60,
            "",
            f"Query: {query[:100]}{'...' if len(query) > 100 else ''}",
            f"Database Count: {db_count}",
            f"Estimated Rows: {estimated_rows:,}",
            "",
            "-" * 40,
            "DECISION",
            "-" * 40,
            f"Scale Classification: {decision.scale.value.upper()}",
            f"Selected Connector: {decision.connector_type.value}",
            f"Estimated Duration: {decision.estimated_duration_ms:,}ms",
            f"Fallback Available: {decision.fallback_available}",
            "",
            "-" * 40,
            "REASON",
            "-" * 40,
            decision.reason,
            "",
            "-" * 40,
            "EXECUTION PLAN",
            "-" * 40,
            f"Strategy: {decision.query_plan.strategy}",
            f"Merge Strategy: {decision.query_plan.merge_strategy}",
            f"Execution Order: {' → '.join(decision.query_plan.execution_order)}",
        ]

        if decision.query_plan.partition_info:
            lines.append("")
            lines.append("Partition Info:")
            for key, value in decision.query_plan.partition_info.items():
                lines.append(f"  {key}: {value}")

        lines.append("")
        lines.append("=" * 60)

        return "\n".join(lines)
