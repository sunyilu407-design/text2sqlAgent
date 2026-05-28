"""
Semantic Memory Module

This module provides vector-based semantic memory storage and retrieval
capabilities for the Text2SQL pipeline. It enables storing natural language
queries with their generated SQL counterparts and recalling semantically
similar queries for context enrichment.

Main Components:
- LanceDBMemoryStore: Low-level vector storage using LanceDB
- MemoryAPI: High-level API with caching and context building
- MemoryTools: AI agent-friendly tool interface
- QueryMemory: Data class for query memory records

Usage:
    from micro_genbi.memory import MemoryAPI, MemoryTools

    # Using MemoryAPI directly
    api = MemoryAPI()
    api.store("Show me all users", "SELECT * FROM users", ["users"])
    results = api.fetch("List users")
    context = api.get_context_for_llm("Show users")
    api.close()

    # Using MemoryTools for agent integration
    tools = MemoryTools()
    result = tools.recall_similar_queries_tool("Show me users")
    if result["success"]:
        print(result["data"])
    tools.close()

    # Using context manager
    with MemoryAPI() as api:
        results = api.fetch("monthly sales")
        print(results)
"""

from __future__ import annotations

from .lancedb_store import LanceDBMemoryStore, LANCEDB_AVAILABLE

from .memory_api import MemoryAPI, MemoryConfig, QueryMemory
from .memory_tools import MemoryTools

__all__ = [
    "LanceDBMemoryStore",
    "LANCEDB_AVAILABLE",
    "MemoryAPI",
    "MemoryConfig",
    "MemoryTools",
    "QueryMemory",
]
