"""Big Data Connectors Module.

Provides connectors for handling large-scale data queries across
multiple databases with automatic route selection.

Connectors:
    - BigDataConnector: Abstract base class for big data connectors.
    - ClickHouseConnector: ClickHouse cluster connector for analytics.
    - FDWConnector: PostgreSQL Foreign Data Wrapper (mysql_fdw / postgres_fdw).
    - BigDataRouter: Automatic route selection based on query scale.

Example:
    >>> from micro_genbi.connectors import FDWConnector, BigDataRouter
    >>>
    >>> # Use FDW directly
    >>> fdw = FDWConnector({"host": "localhost", "port": 5432, "database": "local"})
    >>> with fdw:
    ...     fdw.create_foreign_server("mysql.example.com", "mysql_remote", "mysql")
    >>>
    >>> # Or use router for automatic selection
    >>> router = BigDataRouter()
    >>> decision = router.route("SELECT COUNT(*) FROM orders", db_count=25)
    >>> print(f"Using: {decision.connector_type}")
"""

from micro_genbi.connectors.base import BigDataConnector
from micro_genbi.connectors.fdw_connector import (
    FDWConnector,
    FDWConfig,
    FDWError,
    FDWAlreadyExistsError,
    FDWNotFoundError,
    RemoteServerConfig,
)
from micro_genbi.connectors.bigdata_router import (
    BigDataRouter,
    BigDataRouterError,
    ConnectorType,
    QueryScale,
    QueryPlan,
    RouteDecision,
    RouterConfig,
)

# Conditional ClickHouse exports - only available if clickhouse_driver is installed
try:
    from micro_genbi.connectors.clickhouse_connector import (
        ClickHouseConnector,
        ClickHouseConfig,
        ClickHouseError,
        CLICKHOUSE_AVAILABLE,
    )
except ImportError:
    CLICKHOUSE_AVAILABLE = False

__all__ = [
    # Base
    "BigDataConnector",
    # ClickHouse (optional - requires clickhouse_driver)
    "ClickHouseConnector",
    "ClickHouseConfig",
    "ClickHouseError",
    "CLICKHOUSE_AVAILABLE",
    # FDW
    "FDWConnector",
    "FDWConfig",
    "FDWError",
    "FDWAlreadyExistsError",
    "FDWNotFoundError",
    "RemoteServerConfig",
    # Router
    "BigDataRouter",
    "BigDataRouterError",
    "ConnectorType",
    "QueryScale",
    "QueryPlan",
    "RouteDecision",
    "RouterConfig",
]
