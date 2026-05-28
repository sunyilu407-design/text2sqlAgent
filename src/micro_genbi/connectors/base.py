"""Abstract base class for big data connectors."""

from abc import ABC, abstractmethod
from typing import Any


class BigDataConnector(ABC):
    """Abstract base class for connectors that handle large-scale data queries.

    This interface defines the common operations needed for querying
    big data systems like ClickHouse clusters, including cluster-aware
    queries and materialized view access.
    """

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the data source."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close all connections and release resources."""
        pass

    @abstractmethod
    def execute(self, sql: str, settings: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        """Execute a query on a single node.

        Args:
            sql: SQL query string.
            settings: Optional query settings.

        Returns:
            List of dictionaries representing query results.
        """
        pass

    @abstractmethod
    def cluster_query(
        self, sql: str, settings: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Execute a query across all nodes in the cluster.

        Args:
            sql: SQL query string.
            settings: Optional query settings.

        Returns:
            List of dictionaries representing aggregated query results.
        """
        pass

    @abstractmethod
    def get_materialized_view(self, view_name: str) -> list[dict[str, Any]]:
        """Query a pre-aggregated materialized view.

        Args:
            view_name: Name of the materialized view.

        Returns:
            List of dictionaries representing view data.
        """
        pass
