"""
Memory API for Semantic Memory Operations

This module provides a high-level API for storing, retrieving, and utilizing
semantic memories in the Text2SQL pipeline. It wraps LanceDBMemoryStore with
caching, error handling, and context building capabilities.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .lancedb_store import LanceDBMemoryStore

if True:
    from .lancedb_store import LANCEDB_AVAILABLE


@dataclass
class QueryMemory:
    """
    A stored query memory with semantic metadata.
    
    Attributes:
        id: Unique identifier for this memory record.
        query: The natural language query.
        sql: The generated SQL query.
        tables: List of database tables used.
        similarity: Similarity score when returned from search (0-1).
        timestamp: When this memory was stored.
    """
    id: str
    query: str
    sql: str
    tables: list[str]
    similarity: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class MemoryConfig:
    """Configuration for MemoryAPI behavior."""
    cache_ttl_seconds: int = 300
    default_top_k: int = 5
    db_path: str = "~/.micro_genbi/memory"
    embedding_dimension: int = 384
    fallback_to_memory: bool = True


class MemoryAPI:
    """
    High-level API for semantic memory operations.
    
    Provides caching, error handling, and convenient methods for:
    - Semantic search of historical queries
    - Table-based query recall
    - Context building for LLM prompts
    
    The API uses an internal cache to avoid redundant LanceDB lookups
    for the same query within a configurable time window.
    
    Attributes:
        config: Configuration for cache TTL, default top_k, etc.
        _store: The underlying LanceDBMemoryStore instance.
        _cache: In-memory cache for query results.
    """

    def __init__(self, config: MemoryConfig | None = None) -> None:
        """
        Initialize the MemoryAPI.
        
        Args:
            config: Optional configuration object. Uses defaults if not provided.
        """
        self.config = config or MemoryConfig()
        self._store: LanceDBMemoryStore | None = None
        self._cache: dict[str, tuple[list[QueryMemory], float]] = {}
        self._initialize_store()

    def _initialize_store(self) -> None:
        """Initialize the underlying storage backend."""
        try:
            self._store = LanceDBMemoryStore(
                db_path=self.config.db_path,
                embedding_dimension=self.config.embedding_dimension,
            )
        except ImportError:
            if not self.config.fallback_to_memory:
                raise
            self._store = None

    def _get_cache_key(self, query: str, operation: str) -> str:
        """Generate a cache key for the given query and operation."""
        return f"{operation}:{query.strip().lower()}"

    def _is_cache_valid(self, cache_entry: tuple[list[QueryMemory], float]) -> bool:
        """Check if a cache entry is still valid based on TTL."""
        _, cached_time = cache_entry
        return (time.time() - cached_time) < self.config.cache_ttl_seconds

    def fetch(
        self,
        query: str,
        top_k: int | None = None,
        use_cache: bool = True,
    ) -> list[QueryMemory]:
        """
        Perform semantic search for similar historical queries.
        
        Args:
            query: The natural language query to search for.
            top_k: Maximum number of results to return.
            use_cache: Whether to use cached results if available.
            
        Returns:
            List of QueryMemory objects sorted by similarity (highest first).
        """
        top_k = top_k or self.config.default_top_k
        cache_key = self._get_cache_key(query, "fetch")

        if use_cache and cache_key in self._cache:
            cached_result, cached_time = self._cache[cache_key]
            if self._is_cache_valid((cached_result, cached_time)):
                return cached_result[:top_k]

        if self._store is None:
            return []

        try:
            results = self._store.fetch_similar(query, top_k=top_k)

            memories = [
                QueryMemory(
                    id=r.get("id", ""),
                    query=r.get("natural_query", ""),
                    sql=r.get("generated_sql", ""),
                    tables=r.get("tables_used", []),
                    similarity=r.get("similarity", 0.0),
                    timestamp=r.get("timestamp", datetime.now()),
                )
                for r in results
            ]

            self._cache[cache_key] = (memories, time.time())

            return memories

        except Exception:
            return []

    def recall(
        self,
        table_name: str,
        top_k: int | None = None,
        user_id: str | None = None,
    ) -> list[QueryMemory]:
        """
        Recall historical queries that used a specific table.
        
        Args:
            table_name: Name of the table to recall queries for.
            top_k: Maximum number of results to return.
            user_id: Optional user ID to filter results.
            
        Returns:
            List of QueryMemory objects related to the table.
        """
        top_k = top_k or self.config.default_top_k
        cache_key = self._get_cache_key(table_name, f"recall:{user_id or 'all'}")

        if cache_key in self._cache:
            cached_result, cached_time = self._cache[cache_key]
            if self._is_cache_valid((cached_result, cached_time)):
                return cached_result[:top_k]

        if self._store is None:
            return []

        try:
            results = self._store.recall_table(
                table_name,
                top_k=top_k,
                user_id=user_id,
            )

            memories = [
                QueryMemory(
                    id=r.get("id", ""),
                    query=r.get("natural_query", ""),
                    sql=r.get("generated_sql", ""),
                    tables=r.get("tables_used", []),
                    similarity=r.get("similarity", 0.0),
                    timestamp=r.get("timestamp", datetime.now()),
                )
                for r in results
            ]

            self._cache[cache_key] = (memories, time.time())

            return memories

        except Exception:
            return []

    def store(
        self,
        query: str,
        sql: str,
        tables: list[str],
        user_id: str = "default",
    ) -> bool:
        """
        Store a natural language to SQL query mapping.
        
        Args:
            query: The natural language query.
            sql: The generated SQL query.
            tables: List of tables used in the query.
            user_id: User identifier for the query.
            
        Returns:
            True if storage was successful, False otherwise.
        """
        if self._store is None:
            return False

        try:
            self._store.store_query(
                nl_query=query,
                sql=sql,
                tables=tables,
                user_id=user_id,
            )

            self._invalidate_cache_for_query(query)
            self._invalidate_cache_for_tables(tables)

            return True

        except Exception:
            return False

    def get_schema_context(
        self,
        tables: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get semantic context information for specified tables.
        
        Args:
            tables: List of table names to get context for.
            
        Returns:
            List of context dictionaries with table/column descriptions.
        """
        if self._store is None:
            return []

        try:
            return self._store.get_schema_context(tables)
        except Exception:
            return []

    def store_schema_context(
        self,
        table_name: str,
        column_name: str | None,
        description: str,
    ) -> bool:
        """
        Store semantic description for a schema element.
        
        Args:
            table_name: Name of the table.
            column_name: Name of the column (None for table-level).
            description: Semantic description to store.
            
        Returns:
            True if storage was successful, False otherwise.
        """
        if self._store is None:
            return False

        try:
            self._store.store_schema_context(
                table_name=table_name,
                column_name=column_name,
                description=description,
            )
            return True
        except Exception:
            return False

    def _build_context_from_memories(
        self,
        memories: list[QueryMemory],
        include_sql: bool = True,
    ) -> str:
        """
        Build a context string from query memories for LLM prompts.
        
        Args:
            memories: List of QueryMemory objects to include.
            include_sql: Whether to include the SQL queries in the context.
            
        Returns:
            A formatted string containing the memory context.
        """
        if not memories:
            return ""

        lines = [
            "## Relevant Historical Queries",
            "",
        ]

        for i, memory in enumerate(memories, 1):
            lines.append(f"### Query {i} (similarity: {memory.similarity:.2%})")
            lines.append(f"**Question:** {memory.query}")
            lines.append(f"**Tables used:** {', '.join(memory.tables)}")

            if include_sql:
                lines.append(f"**SQL:**\n```sql\n{memory.sql}\n```")

            lines.append("")

        return "\n".join(lines)

    def get_context_for_llm(
        self,
        query: str,
        top_k: int | None = None,
        include_sql: bool = True,
    ) -> str:
        """
        Get formatted context string for LLM prompt injection.
        
        This is a convenience method that fetches similar memories
        and formats them for direct use in LLM prompts.
        
        Args:
            query: The current natural language query.
            top_k: Maximum number of similar memories to include.
            include_sql: Whether to include SQL in the context.
            
        Returns:
            Formatted context string ready for prompt injection.
        """
        memories = self.fetch(query, top_k=top_k)
        return self._build_context_from_memories(memories, include_sql)

    def _invalidate_cache_for_query(self, query: str) -> None:
        """Invalidate cache entries related to a query."""
        query_lower = query.strip().lower()
        keys_to_remove = [
            k for k in self._cache
            if query_lower in k.lower()
        ]
        for key in keys_to_remove:
            del self._cache[key]

    def _invalidate_cache_for_tables(self, tables: list[str]) -> None:
        """Invalidate cache entries related to tables."""
        for table in tables:
            table_lower = table.lower()
            keys_to_remove = [
                k for k in self._cache
                if table_lower in k.lower()
            ]
            for key in keys_to_remove:
                del self._cache[key]

    def clear_cache(self) -> None:
        """Clear all cached query results."""
        self._cache.clear()

    def close(self) -> None:
        """
        Close the underlying storage and release resources.
        """
        if self._store is not None:
            self._store.close()
            self._store = None

    def __enter__(self) -> "MemoryAPI":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()
