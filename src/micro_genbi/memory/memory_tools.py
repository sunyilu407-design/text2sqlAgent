"""
Memory Tools for AI Agent Integration

This module provides Pydantic-style tools that can be called by AI agents
to interact with the semantic memory system. Each tool follows a consistent
interface pattern and returns structured results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypedDict

from .memory_api import MemoryAPI, MemoryConfig, QueryMemory


class ToolResult(TypedDict):
    """Standard result format for all memory tools."""
    success: bool
    data: Any
    error: str


@dataclass
class ToolResponse:
    """
    Structured response from a memory tool.
    
    Attributes:
        success: Whether the tool operation succeeded.
        data: The result data from the operation.
        error: Error message if the operation failed.
    """
    success: bool
    data: Any = None
    error: str = ""


def _create_result(
    success: bool,
    data: Any = None,
    error: str = "",
) -> ToolResult:
    """
    Create a standardized tool result dictionary.
    
    Args:
        success: Whether the operation succeeded.
        data: Result data to return.
        error: Error message if operation failed.
        
    Returns:
        A ToolResult TypedDict with the structured response.
    """
    return ToolResult(success=success, data=data, error=error)


class MemoryTools:
    """
    Collection of memory tools for AI agent integration.
    
    These tools provide a clean interface for AI agents to interact
    with the semantic memory system without needing to understand
    the underlying implementation details.
    
    Attributes:
        api: The MemoryAPI instance used for memory operations.
    """

    def __init__(
        self,
        config: MemoryConfig | None = None,
        api: MemoryAPI | None = None,
    ) -> None:
        """
        Initialize MemoryTools with an optional API instance.
        
        Args:
            config: Optional MemoryConfig for API configuration.
            api: Optional pre-configured MemoryAPI instance.
        """
        if api is not None:
            self._api = api
        else:
            self._api = MemoryAPI(config=config)

    @property
    def api(self) -> MemoryAPI:
        """Get the underlying MemoryAPI instance."""
        return self._api

    def get_schema_context_tool(
        self,
        table_names: list[str],
    ) -> ToolResult:
        """
        Get semantic context information for specified tables.
        
        This tool retrieves stored semantic descriptions and metadata
        for the requested tables and their columns. Context includes
        business meanings, relationships, and usage patterns.
        
        Args:
            table_names: List of table names to get context for.
            
        Returns:
            ToolResult with schema context data or error information.
            
        Example:
            >>> result = tools.get_schema_context_tool(["users", "orders"])
            >>> if result["success"]:
            ...     for ctx in result["data"]:
            ...         print(ctx["table_name"], ctx["description"])
        """
        try:
            if not table_names:
                return _create_result(
                    success=False,
                    error="table_names cannot be empty",
                )

            context = self._api.get_schema_context(table_names)

            formatted_context = []
            for item in context:
                formatted_context.append({
                    "table_name": item.get("table_name", ""),
                    "column_name": item.get("column_name"),
                    "description": item.get("description", ""),
                    "updated_at": (
                        item.get("updated_at").isoformat()
                        if isinstance(item.get("updated_at"), datetime)
                        else str(item.get("updated_at", ""))
                    ),
                })

            return _create_result(
                success=True,
                data=formatted_context,
            )

        except Exception as e:
            return _create_result(
                success=False,
                error=f"Failed to retrieve schema context: {str(e)}",
            )

    def get_query_history_tool(
        self,
        user_id: str = "default",
        limit: int = 10,
    ) -> ToolResult:
        """
        Get recent query history for a user.
        
        Retrieves the most recent natural language queries and their
        generated SQL counterparts for the specified user.
        
        Args:
            user_id: User identifier to get history for.
            limit: Maximum number of history items to return.
            
        Returns:
            ToolResult with query history data or error information.
            
        Example:
            >>> result = tools.get_query_history_tool(user_id="alice", limit=5)
            >>> if result["success"]:
            ...     for item in result["data"]:
            ...         print(item["query"], "->", item["sql"])
        """
        try:
            if limit <= 0 or limit > 100:
                return _create_result(
                    success=False,
                    error="limit must be between 1 and 100",
                )

            if self._api._store is None:
                return _create_result(
                    success=False,
                    error="Memory store not available",
                )

            try:
                results = self._api._store._queries_table.search(
                    "",
                    query_type="fts",
                ).limit(limit).to_list()

                history = []
                for item in results:
                    if item.get("user_id") == user_id:
                        history.append({
                            "id": item.get("id", ""),
                            "query": item.get("natural_query", ""),
                            "sql": item.get("generated_sql", ""),
                            "tables": item.get("tables_used", []),
                            "timestamp": (
                                item.get("timestamp").isoformat()
                                if isinstance(item.get("timestamp"), datetime)
                                else str(item.get("timestamp", ""))
                            ),
                        })

                history.sort(
                    key=lambda x: x.get("timestamp", ""),
                    reverse=True,
                )

                return _create_result(
                    success=True,
                    data=history[:limit],
                )

            except Exception as e:
                return _create_result(
                    success=False,
                    error=f"Failed to query history: {str(e)}",
                )

        except Exception as e:
            return _create_result(
                success=False,
                error=f"Unexpected error: {str(e)}",
            )

    def recall_similar_queries_tool(
        self,
        nl_query: str,
        top_k: int = 5,
    ) -> ToolResult:
        """
        Find semantically similar historical queries.
        
        Performs semantic similarity search to find historical queries
        that are similar to the provided natural language query. Results
        are sorted by similarity score in descending order.
        
        Args:
            nl_query: The natural language query to search for.
            top_k: Maximum number of similar queries to return.
            
        Returns:
            ToolResult with similar queries or error information.
            
        Example:
            >>> result = tools.recall_similar_queries_tool(
            ...     nl_query="show monthly sales trends",
            ...     top_k=3
            ... )
            >>> if result["success"]:
            ...     for match in result["data"]:
            ...         print(f"Similarity: {match['similarity']:.2%}")
            ...         print(f"Query: {match['query']}")
            ...         print(f"SQL: {match['sql'][:50]}...")
        """
        try:
            if not nl_query or not nl_query.strip():
                return _create_result(
                    success=False,
                    error="nl_query cannot be empty",
                )

            if top_k <= 0 or top_k > 50:
                return _create_result(
                    success=False,
                    error="top_k must be between 1 and 50",
                )

            memories = self._api.fetch(query=nl_query, top_k=top_k)

            if not memories:
                return _create_result(
                    success=True,
                    data=[],
                    error="No similar queries found",
                )

            similar_queries = [
                {
                    "id": memory.id,
                    "query": memory.query,
                    "sql": memory.sql,
                    "tables": memory.tables,
                    "similarity": round(memory.similarity, 4),
                    "timestamp": memory.timestamp.isoformat(),
                }
                for memory in memories
            ]

            return _create_result(
                success=True,
                data=similar_queries,
            )

        except Exception as e:
            return _create_result(
                success=False,
                error=f"Failed to recall similar queries: {str(e)}",
            )

    def store_query_tool(
        self,
        nl_query: str,
        sql: str,
        tables: list[str],
        user_id: str = "default",
    ) -> ToolResult:
        """
        Store a new query in memory.
        
        Saves a natural language query and its generated SQL counterpart
        to the semantic memory store for future recall.
        
        Args:
            nl_query: The natural language query.
            sql: The generated SQL query.
            tables: List of database tables used in the query.
            user_id: User identifier for the query.
            
        Returns:
            ToolResult with storage status or error information.
            
        Example:
            >>> result = tools.store_query_tool(
            ...     nl_query="Count users by country",
            ...     sql="SELECT country, COUNT(*) FROM users GROUP BY country",
            ...     tables=["users"],
            ...     user_id="alice"
            ... )
            >>> if result["success"]:
            ...     print(f"Stored with ID: {result['data']['id']}")
        """
        try:
            if not nl_query or not nl_query.strip():
                return _create_result(
                    success=False,
                    error="nl_query cannot be empty",
                )

            if not sql or not sql.strip():
                return _create_result(
                    success=False,
                    error="sql cannot be empty",
                )

            if not tables:
                return _create_result(
                    success=False,
                    error="tables list cannot be empty",
                )

            success = self._api.store(
                query=nl_query,
                sql=sql,
                tables=tables,
                user_id=user_id,
            )

            if success:
                return _create_result(
                    success=True,
                    data={"stored": True, "query": nl_query},
                )
            else:
                return _create_result(
                    success=False,
                    error="Failed to store query in memory",
                )

        except Exception as e:
            return _create_result(
                success=False,
                error=f"Unexpected error while storing: {str(e)}",
            )

    def recall_table_history_tool(
        self,
        table_name: str,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> ToolResult:
        """
        Recall historical queries that used a specific table.
        
        Retrieves queries from memory that referenced the specified table,
        useful for understanding how a table has been queried before.
        
        Args:
            table_name: Name of the table to recall history for.
            top_k: Maximum number of queries to return.
            user_id: Optional user ID to filter results.
            
        Returns:
            ToolResult with table-related queries or error information.
        """
        try:
            if not table_name or not table_name.strip():
                return _create_result(
                    success=False,
                    error="table_name cannot be empty",
                )

            if top_k <= 0 or top_k > 50:
                return _create_result(
                    success=False,
                    error="top_k must be between 1 and 50",
                )

            memories = self._api.recall(
                table_name=table_name,
                top_k=top_k,
                user_id=user_id,
            )

            history = [
                {
                    "id": memory.id,
                    "query": memory.query,
                    "sql": memory.sql,
                    "tables": memory.tables,
                    "similarity": round(memory.similarity, 4),
                    "timestamp": memory.timestamp.isoformat(),
                }
                for memory in memories
            ]

            return _create_result(
                success=True,
                data=history,
            )

        except Exception as e:
            return _create_result(
                success=False,
                error=f"Failed to recall table history: {str(e)}",
            )

    def build_llm_context_tool(
        self,
        nl_query: str,
        top_k: int = 3,
        include_sql: bool = True,
    ) -> ToolResult:
        """
        Build a formatted context string for LLM prompts.
        
        Retrieves similar memories and formats them as a context string
        that can be injected into LLM prompts to provide relevant
        historical examples.
        
        Args:
            nl_query: The current natural language query.
            top_k: Maximum number of similar memories to include.
            include_sql: Whether to include SQL in the context.
            
        Returns:
            ToolResult with formatted context string.
        """
        try:
            context = self._api.get_context_for_llm(
                query=nl_query,
                top_k=top_k,
                include_sql=include_sql,
            )

            return _create_result(
                success=True,
                data={"context": context},
            )

        except Exception as e:
            return _create_result(
                success=False,
                error=f"Failed to build LLM context: {str(e)}",
            )

    def close(self) -> None:
        """Close the underlying MemoryAPI and release resources."""
        self._api.close()

    def __enter__(self) -> "MemoryTools":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
