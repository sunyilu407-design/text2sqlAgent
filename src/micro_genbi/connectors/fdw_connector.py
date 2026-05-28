"""PostgreSQL Foreign Data Wrapper (FDW) Connector.

Supports mysql_fdw and postgres_fdw for accessing remote databases
as local foreign tables in PostgreSQL.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

import psycopg2
from psycopg2 import sql
from psycopg2.extras import RealDictCursor

from micro_genbi.errors import GenBIError

logger = logging.getLogger(__name__)


class FDWError(GenBIError):
    """FDW operation error."""
    pass


class FDWAlreadyExistsError(FDWError):
    """Foreign server or table already exists."""
    pass


class FDWNotFoundError(FDWError):
    """Foreign server or table not found."""
    pass


@dataclass
class RemoteServerConfig:
    """Configuration for a remote database server."""
    name: str
    fdw_type: str  # "mysql" or "postgres"
    host: str
    port: int
    database: str
    username: str
    password: str
    options: dict[str, str] = field(default_factory=dict)


@dataclass
class FDWConfig:
    """Configuration for FDW connector."""
    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    username: str = "postgres"
    password: str = ""
    remote_servers: dict[str, RemoteServerConfig] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FDWConfig:
        """Create config from dictionary."""
        remote_servers = {}
        for name, server_data in data.get("remote_servers", {}).items():
            remote_servers[name] = RemoteServerConfig(
                name=name,
                fdw_type=server_data.get("fdw_type", "postgres"),
                host=server_data.get("host", "localhost"),
                port=server_data.get("port", 5432),
                database=server_data.get("database", ""),
                username=server_data.get("username", ""),
                password=server_data.get("password", ""),
                options=server_data.get("options", {}),
            )
        return cls(
            host=data.get("host", "localhost"),
            port=data.get("port", 5432),
            database=data.get("database", "postgres"),
            username=data.get("username", "postgres"),
            password=data.get("password", ""),
            remote_servers=remote_servers,
        )


class FDWConnector:
    """
    PostgreSQL Foreign Data Wrapper Connector.

    Manages foreign servers and foreign tables for mysql_fdw and postgres_fdw.
    Enables transparent querying of remote databases through local PostgreSQL.

    Example:
        >>> config = FDWConfig(host="localhost", port=5432, database="localdb")
        >>> connector = FDWConnector(config)
        >>> connector.create_foreign_server(
        ...     remote_host="remote-mysql.example.com",
        ...     foreign_server_name="mysql_remote",
        ...     fdw_type="mysql"
        ... )
        True
    """

    def __init__(self, conn_info: dict[str, Any] | FDWConfig):
        """
        Initialize FDW connector.

        Args:
            conn_info: PostgreSQL connection info dict or FDWConfig object.
        """
        if isinstance(conn_info, dict):
            self.config = FDWConfig.from_dict(conn_info)
        else:
            self.config = conn_info

        self._conn: Optional[psycopg2.extensions.connection] = None
        self._cursor: Optional[psycopg2.extensions.cursor] = None

    def connect(self) -> None:
        """Establish connection to local PostgreSQL."""
        if self._conn is not None and not self._conn.closed:
            return

        try:
            self._conn = psycopg2.connect(
                host=self.config.host,
                port=self.config.port,
                database=self.config.database,
                user=self.config.username,
                password=self.config.password,
            )
            self._conn.autocommit = False
            self._cursor = self._conn.cursor()
            logger.info(
                "Connected to PostgreSQL at %s:%d/%s",
                self.config.host,
                self.config.port,
                self.config.database,
            )
        except psycopg2.Error as e:
            raise FDWError(f"Failed to connect to PostgreSQL: {e}") from e

    def disconnect(self) -> None:
        """Close connection to PostgreSQL."""
        if self._cursor:
            self._cursor.close()
            self._cursor = None
        if self._conn:
            self._conn.close()
            self._conn = None
        logger.info("Disconnected from PostgreSQL")

    def _ensure_connected(self) -> None:
        """Ensure connection is established."""
        if self._conn is None or self._conn.closed:
            self.connect()

    def _execute_ddl(self, sql_stmt: str, params: Optional[dict] = None) -> bool:
        """
        Execute DDL statement on local PostgreSQL.

        Args:
            sql_stmt: SQL DDL statement to execute.
            params: Optional parameters for the statement.

        Returns:
            True if successful.

        Raises:
            FDWAlreadyExistsError: If object already exists.
            FDWNotFoundError: If object does not exist.
            FDWError: For other DDL errors.
        """
        self._ensure_connected()

        try:
            self._cursor.execute(sql_stmt, params or {})
            self._conn.commit()
            logger.debug("Executed DDL: %s", sql_stmt[:100])
            return True
        except psycopg2.Error as e:
            self._conn.rollback()
            error_msg = str(e).lower()

            if "already exists" in error_msg:
                raise FDWAlreadyExistsError(f"Object already exists: {e}") from e
            if "does not exist" in error_msg:
                raise FDWNotFoundError(f"Object not found: {e}") from e
            raise FDWError(f"DDL execution failed: {e}") from e

    def create_foreign_server(
        self,
        remote_host: str,
        foreign_server_name: str,
        fdw_type: str,
        remote_port: Optional[int] = None,
        remote_database: Optional[str] = None,
    ) -> bool:
        """
        Create a foreign server for remote database access.

        Args:
            remote_host: Remote database host address.
            foreign_server_name: Name for the foreign server.
            fdw_type: Type of FDW ("mysql" or "postgres").
            remote_port: Remote database port (default varies by type).
            remote_database: Remote database name.

        Returns:
            True if server created successfully.

        Raises:
            FDWAlreadyExistsError: If server already exists.
            FDWError: For other errors.

        Example:
            >>> connector.create_foreign_server(
            ...     remote_host="mysql.example.com",
            ...     foreign_server_name="mysql_server",
            ...     fdw_type="mysql"
            ... )
        """
        fdw_type = fdw_type.lower()
        if fdw_type not in ("mysql", "postgres"):
            raise FDWError(f"Unsupported FDW type: {fdw_type}. Use 'mysql' or 'postgres'.")

        # Default ports
        default_port = 3306 if fdw_type == "mysql" else 5432
        port = remote_port or default_port

        # Build options for CREATE SERVER
        options = [
            f"host '{remote_host}'",
            f"port '{port}'",
        ]
        if remote_database:
            options.append(f"dbname '{remote_database}'")

        fdw_name = "mysql_fdw" if fdw_type == "mysql" else "postgres_fdw"

        sql_stmt = f"""
            CREATE SERVER IF NOT EXISTS {foreign_server_name}
            FOREIGN DATA WRAPPER {fdw_name}
            OPTIONS ({', '.join(options)})
        """

        try:
            self._execute_ddl(sql_stmt)
            logger.info("Created foreign server '%s' (%s) -> %s:%d",
                       foreign_server_name, fdw_type, remote_host, port)
            return True
        except FDWAlreadyExistsError:
            logger.info("Foreign server '%s' already exists", foreign_server_name)
            return True

    def create_user_mapping(
        self,
        foreign_server_name: str,
        user: str,
        password: str,
    ) -> bool:
        """
        Create user mapping for foreign server authentication.

        Args:
            foreign_server_name: Name of the foreign server.
            user: Remote database username.
            password: Remote database password.

        Returns:
            True if mapping created successfully.
        """
        sql_stmt = f"""
            CREATE USER MAPPING IF NOT EXISTS FOR {user}
            SERVER {foreign_server_name}
            OPTIONS (password '{password}')
        """

        try:
            self._execute_ddl(sql_stmt)
            logger.info("Created user mapping for '%s' on server '%s'", user, foreign_server_name)
            return True
        except FDWAlreadyExistsError:
            logger.info("User mapping for '%s' already exists", user)
            return True

    def create_foreign_table(
        self,
        table_name: str,
        remote_table: str,
        server_name: str,
        columns: list[dict[str, str]],
        remote_schema: Optional[str] = None,
    ) -> bool:
        """
        Create a foreign table mapping to a remote table.

        Args:
            table_name: Name for the local foreign table.
            remote_table: Name of the remote table.
            server_name: Foreign server name.
            columns: List of column definitions as [{"name": "...", "type": "..."}].
            remote_schema: Remote schema name (for postgres_fdw).

        Returns:
            True if table created successfully.

        Raises:
            FDWAlreadyExistsError: If table already exists.
            FDWError: For other errors.

        Example:
            >>> connector.create_foreign_table(
            ...     table_name="orders_fdw",
            ...     remote_table="orders",
            ...     server_name="mysql_server",
            ...     columns=[
            ...         {"name": "id", "type": "integer"},
            ...         {"name": "customer_id", "type": "integer"},
            ...         {"name": "total", "type": "numeric"}
            ...     ]
            ... )
        """
        # Build column definitions
        column_defs = []
        for col in columns:
            col_name = col.get("name", "")
            col_type = col.get("type", "text")
            column_defs.append(f"{col_name} {col_type}")

        columns_str = ", ".join(column_defs)

        # Build OPTIONS clause
        options = [f"table_name '{remote_table}'"]
        if remote_schema:
            options.append(f"schema_name '{remote_schema}'")

        sql_stmt = f"""
            CREATE FOREIGN TABLE IF NOT EXISTS {table_name} (
                {columns_str}
            )
            SERVER {server_name}
            OPTIONS ({', '.join(options)})
        """

        try:
            self._execute_ddl(sql_stmt)
            logger.info(
                "Created foreign table '%s' -> %s.%s on server '%s'",
                table_name, server_name, remote_table, server_name
            )
            return True
        except FDWAlreadyExistsError:
            logger.info("Foreign table '%s' already exists", table_name)
            return True

    def create_union_view(
        self,
        view_name: str,
        table_names: list[str],
        column_mappings: Optional[list[list[str]]] = None,
    ) -> bool:
        """
        Create a view that unions multiple foreign tables.

        Args:
            view_name: Name for the union view.
            table_names: List of foreign table names to union.
            column_mappings: Optional list of column selections per table.
                           Each entry is a list of column names for that table.
                           If None, all columns (*) are selected from each table.

        Returns:
            True if view created successfully.

        Raises:
            FDWAlreadyExistsError: If view already exists.
            FDWError: For other errors.

        Example:
            >>> connector.create_union_view(
            ...     view_name="all_orders",
            ...     table_names=["orders_sh1", "orders_sh2", "orders_sh3"]
            ... )
        """
        if not table_names:
            raise FDWError("At least one table name is required")

        # Build SELECT statements
        select_parts = []
        for i, table in enumerate(table_names):
            if column_mappings and i < len(column_mappings):
                cols = ", ".join(column_mappings[i])
                select_parts.append(f"SELECT {cols} FROM {table}")
            else:
                select_parts.append(f"SELECT * FROM {table}")

        union_sql = "\nUNION ALL\n".join(select_parts)
        sql_stmt = f"CREATE OR REPLACE VIEW {view_name} AS {union_sql}"

        try:
            self._execute_ddl(sql_stmt)
            logger.info(
                "Created union view '%s' with %d tables",
                view_name, len(table_names)
            )
            return True
        except Exception as e:
            raise FDWError(f"Failed to create union view: {e}") from e

    def list_foreign_tables(self, server_name: str) -> list[str]:
        """
        List all foreign tables on a server.

        Args:
            server_name: Foreign server name.

        Returns:
            List of foreign table names.
        """
        self._ensure_connected()

        sql_stmt = """
            SELECT foreign_table_name
            FROM information_schema.foreign_tables
            WHERE foreign_server_name = %s
            ORDER BY foreign_table_name
        """

        try:
            self._cursor.execute(sql_stmt, (server_name,))
            rows = self._cursor.fetchall()
            return [row[0] for row in rows]
        except psycopg2.Error as e:
            raise FDWError(f"Failed to list foreign tables: {e}") from e

    def list_foreign_servers(self) -> list[str]:
        """
        List all foreign servers.

        Returns:
            List of foreign server names.
        """
        self._ensure_connected()

        sql_stmt = """
            SELECT srvname
            FROM pg_catalog.pg_foreign_server
            ORDER BY srvname
        """

        try:
            self._cursor.execute(sql_stmt)
            rows = self._cursor.fetchall()
            return [row[0] for row in rows]
        except psycopg2.Error as e:
            raise FDWError(f"Failed to list foreign servers: {e}") from e

    def drop_foreign_table(self, table_name: str, cascade: bool = False) -> bool:
        """
        Drop a foreign table.

        Args:
            table_name: Name of the foreign table to drop.
            cascade: Whether to cascade drop dependent objects.

        Returns:
            True if table dropped successfully.

        Raises:
            FDWNotFoundError: If table does not exist.
            FDWError: For other errors.
        """
        cascade_sql = " CASCADE" if cascade else ""
        sql_stmt = f"DROP FOREIGN TABLE IF EXISTS {table_name}{cascade_sql}"

        try:
            self._execute_ddl(sql_stmt)
            logger.info("Dropped foreign table '%s'", table_name)
            return True
        except FDWNotFoundError:
            logger.info("Foreign table '%s' does not exist", table_name)
            return True

    def drop_server(self, server_name: str, cascade: bool = False) -> bool:
        """
        Drop a foreign server.

        Args:
            server_name: Name of the foreign server to drop.
            cascade: Whether to cascade drop dependent objects.

        Returns:
            True if server dropped successfully.

        Raises:
            FDWNotFoundError: If server does not exist.
            FDWError: For other errors.
        """
        cascade_sql = " CASCADE" if cascade else ""
        sql_stmt = f"DROP SERVER IF EXISTS {server_name}{cascade_sql}"

        try:
            self._execute_ddl(sql_stmt)
            logger.info("Dropped foreign server '%s'", server_name)
            return True
        except FDWNotFoundError:
            logger.info("Foreign server '%s' does not exist", server_name)
            return True

    def drop_user_mapping(self, server_name: str, user: str) -> bool:
        """
        Drop a user mapping for a foreign server.

        Args:
            server_name: Foreign server name.
            user: Username whose mapping to drop.

        Returns:
            True if mapping dropped successfully.
        """
        sql_stmt = f"DROP USER MAPPING IF EXISTS FOR {user} SERVER {server_name}"

        try:
            self._execute_ddl(sql_stmt)
            logger.info("Dropped user mapping for '%s' on server '%s'", user, server_name)
            return True
        except FDWNotFoundError:
            logger.info("User mapping for '%s' does not exist", user)
            return True

    def get_server_info(self, server_name: str) -> dict[str, Any]:
        """
        Get information about a foreign server.

        Args:
            server_name: Foreign server name.

        Returns:
            Dictionary with server information.
        """
        self._ensure_connected()

        sql_stmt = """
            SELECT
                s.srvname AS server_name,
                f.fdwname AS fdw_name,
                s.srvoptions AS options
            FROM pg_catalog.pg_foreign_server s
            JOIN pg_catalog.pg_foreign_data_wrapper f ON s.srvfdw = f.oid
            WHERE s.srvname = %s
        """

        try:
            self._cursor.execute(sql_stmt, (server_name,))
            row = self._cursor.fetchone()
            if row is None:
                raise FDWNotFoundError(f"Foreign server '{server_name}' not found")

            return {
                "server_name": row[0],
                "fdw_name": row[1],
                "options": row[2],
            }
        except psycopg2.Error as e:
            raise FDWError(f"Failed to get server info: {e}") from e

    def enable_fdw_extension(self, fdw_type: str) -> bool:
        """
        Enable FDW extension (requires superuser).

        Args:
            fdw_type: FDW type ("mysql" or "postgres").

        Returns:
            True if extension enabled.
        """
        fdw_type = fdw_type.lower()
        if fdw_type == "mysql":
            ext_name = "mysql_fdw"
        elif fdw_type == "postgres":
            ext_name = "postgres_fdw"
        else:
            raise FDWError(f"Unsupported FDW type: {fdw_type}")

        sql_stmt = f"CREATE EXTENSION IF NOT EXISTS {ext_name}"

        try:
            self._execute_ddl(sql_stmt)
            logger.info("Enabled %s extension", ext_name)
            return True
        except FDWAlreadyExistsError:
            logger.info("Extension '%s' already exists", ext_name)
            return True

    def setup_remote_database(
        self,
        remote_config: RemoteServerConfig,
        table_name: str,
        remote_table: str,
        columns: list[dict[str, str]],
        remote_schema: Optional[str] = None,
    ) -> bool:
        """
        Convenience method to set up a complete foreign table setup.

        This enables the extension, creates server, user mapping,
        and foreign table in one call.

        Args:
            remote_config: Remote server configuration.
            table_name: Local foreign table name.
            remote_table: Remote table name.
            columns: Column definitions.
            remote_schema: Remote schema (for postgres_fdw).

        Returns:
            True if setup completed successfully.
        """
        # Enable extension
        self.enable_fdw_extension(remote_config.fdw_type)

        # Create server
        self.create_foreign_server(
            remote_host=remote_config.host,
            foreign_server_name=remote_config.name,
            fdw_type=remote_config.fdw_type,
            remote_port=remote_config.port,
            remote_database=remote_config.database,
        )

        # Create user mapping for current user
        current_user = self.config.username
        self.create_user_mapping(
            foreign_server_name=remote_config.name,
            user=current_user,
            password=remote_config.password,
        )

        # Create foreign table
        self.create_foreign_table(
            table_name=table_name,
            remote_table=remote_table,
            server_name=remote_config.name,
            columns=columns,
            remote_schema=remote_schema,
        )

        logger.info(
            "Completed setup: server='%s', table='%s' -> remote='%s'",
            remote_config.name, table_name, remote_table
        )
        return True

    def __enter__(self) -> FDWConnector:
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.disconnect()
