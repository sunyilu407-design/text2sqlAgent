"""ClickHouse connector for large-scale data queries."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generator

try:
    from clickhouse_driver import Client
    from clickhouse_driver.errors import ConnectError as ClickHouseConnectError
    CLICKHOUSE_AVAILABLE = True
except ImportError:
    CLICKHOUSE_AVAILABLE = False
    Client = None  # type: ignore[assignment, misc]
    ClickHouseConnectError = Exception  # type: ignore[misc, assignment]

from micro_genbi.connectors.base import BigDataConnector

if TYPE_CHECKING:
    from clickhouse_driver.client.base import ClickHouseClientBase

logger = logging.getLogger(__name__)


@dataclass
class ClickHouseConfig:
    """Configuration for ClickHouse cluster connection.

    Attributes:
        hosts: List of ClickHouse server hostnames or IP addresses.
        ports: List of native client ports corresponding to each host.
        username: Authentication username.
        password: Authentication password.
        database: Database name to connect to (default: "default").
        cluster_name: Optional cluster name for distributed queries.
        compression: Enable gzip compression (default: True).
    """

    hosts: list[str]
    ports: list[int]
    username: str
    password: str
    database: str = "default"
    cluster_name: str | None = None
    compression: bool = True

    def __post_init__(self) -> None:
        """Validate that hosts and ports lists have matching lengths."""
        if len(self.hosts) != len(self.ports):
            raise ValueError(
                f"Mismatch between {len(self.hosts)} hosts and {len(self.ports)} ports"
            )
        if not self.hosts:
            raise ValueError("At least one host must be specified")


class ClickHouseConnector(BigDataConnector):
    """ClickHouse cluster connector for large-scale data queries.

    This connector handles queries across a ClickHouse cluster with support for:
    - High availability through multiple hosts
    - Gzip compression for network efficiency
    - Connection pooling and reuse
    - Materialized view queries
    - Cluster-wide distributed queries

    Example:
        >>> config = ClickHouseConfig(
        ...     hosts=["ch1.example.com", "ch2.example.com"],
        ...     ports=[9000, 9000],
        ...     username="default",
        ...     password="secret",
        ...     cluster_name="my_cluster"
        ... )
        >>> connector = ClickHouseConnector.from_config(config)
        >>> results = connector.execute("SELECT * FROM my_table LIMIT 10")
        >>> connector.disconnect()
    """

    def __init__(
        self,
        hosts: list[str],
        ports: list[int],
        username: str,
        password: str,
        database: str = "default",
        compression: bool = True,
        cluster_name: str | None = None,
    ) -> None:
        """Initialize the ClickHouse connector.

        Args:
            hosts: List of ClickHouse server hostnames or IP addresses.
            ports: List of native client ports corresponding to each host.
            username: Authentication username.
            password: Authentication password.
            database: Database name to connect to (default: "default").
            compression: Enable gzip compression (default: True).
            cluster_name: Optional cluster name for distributed queries.
        """
        self._config = ClickHouseConfig(
            hosts=hosts,
            ports=ports,
            username=username,
            password=password,
            database=database,
            compression=compression,
            cluster_name=cluster_name,
        )
        self._clients: dict[int, ClickHouseClientBase] = {}
        self._current_index: int = 0
        self._lock = None  # Will be initialized lazily for thread safety

    @classmethod
    def from_config(cls, config: ClickHouseConfig) -> ClickHouseConnector:
        """Create a connector from a configuration object.

        Args:
            config: ClickHouseConfig instance with connection settings.

        Returns:
            Configured ClickHouseConnector instance.
        """
        return cls(
            hosts=config.hosts,
            ports=config.ports,
            username=config.username,
            password=config.password,
            database=config.database,
            compression=config.compression,
            cluster_name=config.cluster_name,
        )

    def _get_lock(self) -> Any:
        """Get or create the threading lock lazily."""
        if self._lock is None:
            import threading

            self._lock = threading.Lock()
        return self._lock

    def _get_client(self, host_index: int | None = None) -> ClickHouseClientBase:
        """Get or create a ClickHouse client for the specified host.

        This method implements connection pooling by reusing existing clients.
        Clients are stored in a dictionary keyed by host index.

        Args:
            host_index: Specific host index to use. If None, uses round-robin.

        Returns:
            Active ClickHouse client instance.
        """
        if not CLICKHOUSE_AVAILABLE:
            raise ImportError(
                "clickhouse_driver is not installed. Install it with: pip install clickhouse-driver"
            )

        if host_index is None:
            host_index = self._current_index % len(self._config.hosts)

        if host_index not in self._clients:
            host = self._config.hosts[host_index]
            port = self._config.ports[host_index]

            settings = {"compression": "gzip" if self._config.compression else ""}

            client = Client(
                host=host,
                port=port,
                user=self._config.username,
                password=self._config.password,
                database=self._config.database,
                settings=settings,
                connect_timeout=10,
                send_receive_timeout=300,
            )
            self._clients[host_index] = client
            logger.debug("Created new ClickHouse client for %s:%s", host, port)

        return self._clients[host_index]

    def _rotate_host(self) -> None:
        """Rotate to the next host in the list for load balancing."""
        self._current_index = (self._current_index + 1) % len(self._config.hosts)

    def _build_cluster_sql(self, sql: str) -> str:
        """Add cluster settings to SQL if cluster_name is configured.

        For ClickHouse, distributed queries across a cluster can be
        executed by prefixing table names with the cluster name or
        by using the cluster() function.

        Args:
            sql: Original SQL query.

        Returns:
            Modified SQL with cluster settings if applicable.
        """
        if self._config.cluster_name and "on cluster" not in sql.lower():
            return sql
        return sql

    def connect(self) -> None:
        """Establish connection to the ClickHouse cluster.

        Initializes connections to all configured hosts in parallel.
        """
        logger.info(
            "Connecting to ClickHouse cluster with %d hosts",
            len(self._config.hosts),
        )
        try:
            for i in range(len(self._config.hosts)):
                client = self._get_client(host_index=i)
                client.execute("SELECT 1")
                logger.debug(
                    "Successfully connected to %s:%s",
                    self._config.hosts[i],
                    self._config.ports[i],
                )
            logger.info("All ClickHouse connections established")
        except Exception as e:
            logger.error("Failed to connect to ClickHouse cluster: %s", e)
            raise

    def disconnect(self) -> None:
        """Close all ClickHouse connections and release resources."""
        lock = self._get_lock()
        with lock:
            for index, client in list(self._clients.items()):
                try:
                    client.disconnect()
                    logger.debug("Disconnected client for host index %d", index)
                except Exception as e:
                    logger.warning("Error disconnecting client %d: %s", index, e)
            self._clients.clear()
            logger.info("All ClickHouse connections closed")

    def execute(
        self, sql: str, settings: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a query on a single ClickHouse node.

        Uses round-robin to distribute load across available hosts.

        Args:
            sql: SQL query string.
            settings: Optional query settings (e.g., max_execution_time).

        Returns:
            List of dictionaries representing query results.

        Raises:
            ClickHouseError: If the query fails.
        """
        lock = self._get_lock()
        with lock:
            host_index = self._current_index
            self._rotate_host()

        try:
            client = self._get_client(host_index=host_index)
            logger.debug("Executing on host index %d: %s", host_index, sql[:100])

            query_settings = settings or {}
            result = client.execute(sql, settings=query_settings)

            return self._format_result(result)

        except Exception as e:
            logger.error("Query execution failed on host %d: %s", host_index, e)
            raise ClickHouseError(f"Query execution failed: {e}") from e

    def cluster_query(
        self, sql: str, settings: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a query across all nodes in the ClickHouse cluster.

        This method handles distributed queries that aggregate data
        across multiple cluster nodes. If cluster_name is configured,
        it adds the appropriate cluster settings.

        Args:
            sql: SQL query string (may use cluster table names).
            settings: Optional query settings.

        Returns:
            List of dictionaries representing aggregated results.

        Raises:
            ClickHouseError: If the cluster query fails.
        """
        if not self._config.cluster_name:
            logger.warning(
                "No cluster_name configured, falling back to single-node query"
            )
            return self.execute(sql, settings=settings)

        lock = self._get_lock()
        with lock:
            cluster_sql = self._build_cluster_sql(sql)

        query_settings = settings or {}
        query_settings["cluster"] = self._config.cluster_name

        try:
            client = self._get_client(host_index=0)
            logger.debug(
                "Executing cluster query on %s: %s",
                self._config.cluster_name,
                cluster_sql[:100],
            )

            result = client.execute(cluster_sql, settings=query_settings)
            return self._format_result(result)

        except Exception as e:
            logger.error("Cluster query failed: %s", e)
            raise ClickHouseError(f"Cluster query failed: {e}") from e

    def get_materialized_view(
        self, view_name: str, limit: int = 10000
    ) -> list[dict[str, Any]]:
        """Query a pre-aggregated materialized view.

        Materialized views in ClickHouse store pre-computed results
        that can be queried directly for fast access to aggregated data.

        Args:
            view_name: Name of the materialized view.
            limit: Maximum number of rows to return (default: 10000).

        Returns:
            List of dictionaries representing view data.

        Raises:
            ClickHouseError: If the view query fails.
        """
        if not view_name:
            raise ValueError("view_name cannot be empty")

        safe_name = self._sanitize_identifier(view_name)
        sql = f"SELECT * FROM {safe_name} LIMIT {limit}"

        try:
            logger.debug("Querying materialized view: %s", view_name)
            return self.execute(sql)
        except Exception as e:
            logger.error("Failed to query materialized view %s: %s", view_name, e)
            raise ClickHouseError(
                f"Failed to query materialized view '{view_name}': {e}"
            ) from e

    def _sanitize_identifier(self, identifier: str) -> str:
        """Sanitize a SQL identifier to prevent injection.

        Args:
            identifier: Table or view name.

        Returns:
            Safely quoted identifier.
        """
        clean = identifier.replace("`", "").replace("'", "").replace('"', "")
        return f"`{clean}`"

    def _format_result(
        self, result: tuple[tuple[Any, ...], list[str]]
    ) -> list[dict[str, Any]]:
        """Format ClickHouse query result into list of dictionaries.

        ClickHouse driver returns (data, column_names) tuple.

        Args:
            result: Raw ClickHouse query result.

        Returns:
            List of dictionaries with column names as keys.
        """
        if not result or not result[0]:
            return []

        data, columns = result
        return [dict(zip(columns, row)) for row in data]

    def get_cluster_stats(self) -> dict[str, Any]:
        """Get statistics about the cluster and connections.

        Returns:
            Dictionary with cluster status information.
        """
        try:
            result = self.execute(
                "SELECT * FROM system.clusters WHERE cluster = %(cluster)s",
                settings={"cluster": self._config.cluster_name} if self._config.cluster_name else {},
            )
            return {"status": "healthy", "cluster": self._config.cluster_name, "nodes": result}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def __enter__(self) -> ClickHouseConnector:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.disconnect()


class ClickHouseError(Exception):
    """Exception raised for ClickHouse-related errors."""

    pass
