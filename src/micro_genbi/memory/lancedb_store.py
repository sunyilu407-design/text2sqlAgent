"""
LanceDB Memory Store for Semantic Memory Storage

This module provides vector-based storage for natural language queries and SQL pairs,
enabling semantic similarity search for query recall and context enrichment.
"""

from __future__ import annotations

import hashlib
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

try:
    import lancedb
    from lancedb.embeddings import EmbeddingFunction

    LANCEDB_AVAILABLE = True
except ImportError:
    LANCEDB_AVAILABLE = False
    lancedb = None
    EmbeddingFunction = None


@dataclass
class QueryRecord:
    """Record for storing NL→SQL query pairs."""
    id: str
    natural_query: str
    generated_sql: str
    tables_used: list[str]
    semantic_vector: list[float]
    timestamp: datetime
    user_id: str


@dataclass
class SchemaContextRecord:
    """Record for storing schema semantic context."""
    id: str
    table_name: str
    column_name: str | None
    description: str
    semantic_vector: list[float]
    updated_at: datetime


class LanceDBMemoryStore:
    """
    LanceDB-based semantic memory store for query and schema context storage.
    
    Provides vector storage and similarity search capabilities for:
    - Storing natural language to SQL query mappings
    - Recalling similar historical queries
    - Storing schema semantic descriptions for context enrichment
    
    The store uses lazy initialization to defer database opening until first use.
    
    Attributes:
        db_path: Path to the LanceDB database directory.
        _db: Internal LanceDB database instance (initialized lazily).
        _embedding_function: Embedding function for vector generation.
    """

    def __init__(
        self,
        db_path: str = "~/.micro_genbi/memory",
        embedding_dimension: int = 384,
    ) -> None:
        """
        Initialize the LanceDB memory store.
        
        Args:
            db_path: Path to store the LanceDB database files.
            embedding_dimension: Dimension of embedding vectors (default: 384).
        """
        self._db_path = os.path.expanduser(db_path)
        self._embedding_dimension = embedding_dimension
        self._db: Any = None
        self._embedding_function: Any = None
        self._context_table: Any = None
        self._queries_table: Any = None
        self._is_open: bool = False

    def _lazy_open(self) -> None:
        """
        Lazily open the LanceDB connection and create tables if needed.
        
        This method is called on first use to defer database initialization.
        Creates the database directory and opens the connection.
        """
        if self._is_open:
            return

        if not LANCEDB_AVAILABLE:
            raise ImportError(
                "LanceDB is not installed. Install it with: pip install lancedb"
            )

        os.makedirs(self._db_path, exist_ok=True)

        self._db = lancedb.connect(self._db_path)
        self._embedding_function = _HashEmbeddingFunction(
            dim=self._embedding_dimension
        )
        self._create_tables()
        self._is_open = True

    def _create_tables(self) -> None:
        """
        Create the LanceDB tables for context and queries storage.
        
        Creates two tables:
        - context_table: Stores schema semantic context (tables, columns, descriptions)
        - queries_table: Stores natural language to SQL query pairs
        """
        context_schema = {
            "id": "string",
            "table_name": "string",
            "column_name": "string",
            "description": "string",
            "semantic_vector": f"fixed-size-list(float, {self._embedding_dimension})",
            "updated_at": "timestamp",
        }

        queries_schema = {
            "id": "string",
            "natural_query": "string",
            "generated_sql": "string",
            "tables_used": "list<string>",
            "semantic_vector": f"fixed-size-list(float, {self._embedding_dimension})",
            "timestamp": "timestamp",
            "user_id": "string",
        }

        try:
            self._context_table = self._db.open_table("schema_context")
        except Exception:
            self._context_table = self._db.create_table(
                "schema_context",
                schema=context_schema,
                mode="create",
            )

        try:
            self._queries_table = self._db.open_table("query_history")
        except Exception:
            self._queries_table = self._db.create_table(
                "query_history",
                schema=queries_schema,
                mode="create",
            )

    def store_query(
        self,
        nl_query: str,
        sql: str,
        tables: list[str],
        user_id: str = "default",
    ) -> str:
        """
        Store a natural language to SQL query mapping.
        
        Args:
            nl_query: The natural language query string.
            sql: The generated SQL query.
            tables: List of database tables used in the query.
            user_id: Identifier for the user who made the query.
            
        Returns:
            The unique record ID for the stored query.
        """
        self._lazy_open()

        record_id = hashlib.sha256(
            f"{nl_query}:{sql}:{time.time()}".encode()
        ).hexdigest()[:16]

        vector = self._generate_embedding(nl_query)

        record = {
            "id": record_id,
            "natural_query": nl_query,
            "generated_sql": sql,
            "tables_used": tables,
            "semantic_vector": vector,
            "timestamp": datetime.now(),
            "user_id": user_id,
        }

        self._queries_table.add([record])

        return record_id

    def fetch_similar(
        self,
        nl_query: str,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Find similar queries using semantic similarity search.
        
        Args:
            nl_query: The natural language query to search for.
            top_k: Maximum number of similar queries to return.
            user_id: Optional user ID to filter results.
            
        Returns:
            List of similar query records with similarity scores.
        """
        self._lazy_open()

        vector = self._generate_embedding(nl_query)

        query = self._queries_table.search(
            vector=vector,
            vector_column_name="semantic_vector",
        ).limit(top_k)

        if user_id:
            query = query.where(f"user_id = '{user_id}'")

        results = query.to_list()

        for record in results:
            if "semantic_vector" in record:
                stored_vector = record["semantic_vector"]
                if isinstance(stored_vector, list):
                    record["similarity"] = self._cosine_similarity(
                        vector, stored_vector
                    )
                else:
                    record["similarity"] = 0.0

        return results

    def recall_table(
        self,
        table_name: str,
        top_k: int = 5,
        user_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Recall historical queries that used a specific table.
        
        Args:
            table_name: Name of the table to recall queries for.
            top_k: Maximum number of queries to return.
            user_id: Optional user ID to filter results.
            
        Returns:
            List of query records that used the specified table.
        """
        self._lazy_open()

        query = self._queries_table.search(
            table_name,
            query_type="fts",
        ).limit(top_k * 2)

        if user_id:
            query = query.where(f"user_id = '{user_id}'")

        results = query.to_list()

        filtered_results = [
            r for r in results
            if table_name.lower() in [t.lower() for t in r.get("tables_used", [])]
        ]

        return filtered_results[:top_k]

    def get_schema_context(
        self,
        tables: list[str],
    ) -> list[dict[str, Any]]:
        """
        Get semantic context for specified tables and their columns.
        
        Args:
            tables: List of table names to get context for.
            
        Returns:
            List of schema context records with semantic descriptions.
        """
        self._lazy_open()

        if not tables:
            return []

        conditions = " OR ".join(
            f"table_name = '{t}'" for t in tables
        )

        try:
            results = (
                self._context_table.search(
                    tables[0],
                    query_type="fts",
                )
                .where(f"({conditions})")
                .limit(len(tables) * 10)
                .to_list()
            )
        except Exception:
            results = []

        return [
            r for r in results
            if r.get("table_name", "").lower() in [t.lower() for t in tables]
        ]

    def store_schema_context(
        self,
        table_name: str,
        column_name: str | None,
        description: str,
    ) -> str:
        """
        Store semantic context for a schema element.
        
        Args:
            table_name: Name of the table.
            column_name: Name of the column (None for table-level description).
            description: Semantic description of the element.
            
        Returns:
            The unique record ID for the stored context.
        """
        self._lazy_open()

        record_id = hashlib.sha256(
            f"{table_name}:{column_name}:{description[:50]}:{time.time()}".encode()
        ).hexdigest()[:16]

        vector = self._generate_embedding(description)

        record = {
            "id": record_id,
            "table_name": table_name,
            "column_name": column_name or "",
            "description": description,
            "semantic_vector": vector,
            "updated_at": datetime.now(),
        }

        self._context_table.add([record])

        return record_id

    def _generate_embedding(self, text: str) -> list[float]:
        """
        Generate an embedding vector for the given text.
        
        Uses a hash-based fallback implementation that creates deterministic
        vectors from text. For production use, consider integrating with
        OpenAI, Cohere, or local embedding models.
        
        Args:
            text: The text to generate an embedding for.
            
        Returns:
            A list of floats representing the embedding vector.
        """
        return _generate_hash_embedding(text, self._embedding_dimension)

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        """
        Calculate cosine similarity between two vectors.
        
        Args:
            a: First vector.
            b: Second vector.
            
        Returns:
            Cosine similarity score between -1 and 1.
        """
        if len(a) != len(b):
            return 0.0

        dot_product = sum(x * y for x, y in zip(a, b))
        magnitude_a = sum(x * x for x in a) ** 0.5
        magnitude_b = sum(x * x for x in b) ** 0.5

        if magnitude_a == 0 or magnitude_b == 0:
            return 0.0

        return dot_product / (magnitude_a * magnitude_b)

    def close(self) -> None:
        """
        Close the LanceDB connection and release resources.
        
        This method should be called when the store is no longer needed
        to properly clean up database connections.
        """
        if self._db is not None:
            self._db = None
            self._context_table = None
            self._queries_table = None
            self._is_open = False

    def __enter__(self) -> "LanceDBMemoryStore":
        """Context manager entry."""
        self._lazy_open()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.close()


class _HashEmbeddingFunction:
    """
    Simple hash-based embedding function for fallback use.
    
    This provides deterministic embeddings without requiring external API calls.
    For production, consider using proper embedding models (OpenAI, Cohere, etc.)
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def generate_embeddings(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of texts."""
        return [_generate_hash_embedding(text, self.dim) for text in texts]


def _generate_hash_embedding(text: str, dim: int) -> list[float]:
    """
    Generate a deterministic embedding from text using hash-based approach.
    
    This creates a pseudo-embedding by hashing the text and mapping
    hash bytes to float values in the range [-1, 1].
    
    Args:
        text: Input text to embed.
        dim: Dimension of the output embedding vector.
        
    Returns:
        List of float values representing the embedding.
    """
    hash_bytes = hashlib.sha256(text.encode("utf-8")).digest()

    values = []
    for i in range(dim):
        byte_index = (i * 2) % len(hash_bytes)
        if byte_index + 1 < len(hash_bytes):
            val = int.from_bytes(
                hash_bytes[byte_index:byte_index + 2],
                byteorder="big",
            )
            normalized = (val / 65535.0) * 2.0 - 1.0
            values.append(normalized)
        else:
            values.append(0.0)

    norm = sum(v * v for v in values) ** 0.5
    if norm > 0:
        values = [v / norm for v in values]

    return values
