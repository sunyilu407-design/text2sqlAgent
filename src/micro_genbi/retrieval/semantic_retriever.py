"""语义检索模块

基于 TF-IDF 的语义检索，用于从 Schema 中检索相关表和列。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Any
from collections import Counter

from micro_genbi import get_logger

logger = get_logger(__name__)


@dataclass
class RetrievalResult:
    """检索结果"""
    table_name: str
    score: float
    matched_columns: list[str] = field(default_factory=list)
    reasoning: str = ""


class TFIDFRetriever:
    """
    TF-IDF 语义检索器

    基于词频-逆文档频率算法检索相关表。
    """

    def __init__(self, schema_registry):
        self.schema_registry = schema_registry
        self._index: dict[str, dict] = {}

    def build_index(self) -> None:
        """构建检索索引"""
        self._index.clear()

        for fqn, table_info in self.schema_registry._tables.items():
            # 构建表的索引词
            terms = self._extract_terms(table_info)
            self._index[fqn] = {
                "terms": terms,
                "table_info": table_info,
            }

    def _extract_terms(self, table_info) -> dict[str, int]:
        """提取表的索引词"""
        terms = Counter()

        # 表名分词
        terms.update(self._tokenize(table_info.name))

        # 显示名分词
        if hasattr(table_info, "logical_name"):
            terms.update(self._tokenize(table_info.logical_name))

        # 描述分词
        if hasattr(table_info, "description") and table_info.description:
            terms.update(self._tokenize(table_info.description))

        # 列名分词
        for col in table_info.columns:
            terms.update(self._tokenize(col.name))
            if hasattr(col, "logical_name"):
                terms.update(self._tokenize(col.logical_name))
            if hasattr(col, "description") and col.description:
                terms.update(self._tokenize(col.description))

        return dict(terms)

    def _tokenize(self, text: str) -> list[str]:
        """分词"""
        if not text:
            return []

        # 转换为小写
        text = text.lower()

        # 分词（中文、英文、数字）
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-z0-9]+', text)

        # 停用词过滤
        stopwords = {"的", "是", "在", "和", "了", "有", "与", "或", "等", "表", "数据"}
        tokens = [t for t in tokens if t not in stopwords and len(t) > 1]

        return tokens

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """
        检索相关表

        Args:
            query: 查询文本
            top_k: 返回数量

        Returns:
            list[RetrievalResult]: 检索结果
        """
        if not self._index:
            self.build_index()

        # 查询分词
        query_terms = self._tokenize(query)
        if not query_terms:
            return []

        # 计算每个表的 TF-IDF 分数
        scores: dict[str, float] = {}

        for fqn, indexed in self._index.items():
            score = self._calculate_score(query_terms, indexed["terms"])
            if score > 0:
                scores[fqn] = score

        # 排序并返回 top_k
        sorted_results = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for fqn, score in sorted_results[:top_k]:
            table_info = self._index[fqn]["table_info"]

            # 找出匹配的列
            matched_cols = self._find_matched_columns(query_terms, table_info)

            results.append(RetrievalResult(
                table_name=fqn,
                score=score,
                matched_columns=matched_cols,
                reasoning=f"匹配词: {', '.join(query_terms)}",
            ))

        return results

    def _calculate_score(self, query_terms: list[str], doc_terms: dict[str, int]) -> float:
        """计算 TF-IDF 分数"""
        score = 0.0

        doc_total = sum(doc_terms.values())
        if doc_total == 0:
            return 0.0

        for term in query_terms:
            # TF
            tf = doc_terms.get(term, 0) / doc_total

            # 简单 IDF（实际应用中应使用逆文档频率）
            idf = 1.0

            # 分数累加
            score += tf * idf

        return score

    def _find_matched_columns(self, query_terms: list[str], table_info) -> list[str]:
        """找出匹配的列"""
        matched = []

        for col in table_info.columns:
            col_str = f"{col.name} {getattr(col, 'logical_name', '')} {getattr(col, 'description', '')}"
            col_terms = self._tokenize(col_str)

            if any(term in col_terms for term in query_terms):
                matched.append(col.name)

        return matched


class SemanticRetriever:
    """
    语义检索器

    支持多种检索策略的组合。
    """

    def __init__(self, schema_registry):
        self.schema_registry = schema_registry
        self.tfidf_retriever = TFIDFRetriever(schema_registry)

    def retrieve_relevant_tables(
        self,
        query: str,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        """
        检索相关表

        Args:
            query: 用户查询
            top_k: 返回数量

        Returns:
            list[RetrievalResult]: 相关表列表
        """
        # 1. 精确匹配
        exact_matches = self._exact_match(query)

        # 2. TF-IDF 检索
        tfidf_results = self.tfidf_retriever.retrieve(query, top_k)

        # 3. 合并结果（精确匹配优先）
        seen = set()
        results = []

        for table in exact_matches:
            if table not in seen:
                results.append(table)
                seen.add(table)

        for result in tfidf_results:
            if result.table_name not in seen:
                results.append(result)
                seen.add(result.table_name)

        return results[:top_k]

    def _exact_match(self, query: str) -> list[RetrievalResult]:
        """精确匹配"""
        results = []
        query_lower = query.lower()

        for fqn, table_info in self.schema_registry._tables.items():
            # 表名精确匹配
            if query_lower in table_info.name.lower():
                results.append(RetrievalResult(
                    table_name=fqn,
                    score=1.0,
                    matched_columns=[c.name for c in table_info.columns],
                    reasoning="表名精确匹配",
                ))

        return results

    def build_context(
        self,
        query: str,
        max_tables: int = 5,
        max_columns_per_table: int = 10,
    ) -> str:
        """
        构建检索上下文

        Args:
            query: 用户查询
            max_tables: 最大表数量
            max_columns_per_table: 每表最大列数

        Returns:
            str: 上下文字符串
        """
        results = self.retrieve_relevant_tables(query, top_k=max_tables)

        if not results:
            return "/* 未找到相关表 */"

        context_parts = []

        for result in results:
            table_info = self.schema_registry._tables.get(result.table_name)
            if not table_info:
                continue

            # 构建表描述
            table_desc = f"-- 表: {table_info.logical_name} ({table_info.name})"
            if table_info.description:
                table_desc += f"\n-- 描述: {table_info.description}"

            # 构建列描述
            columns_desc = []
            for col in table_info.columns[:max_columns_per_table]:
                col_desc = f"  {col.name} ({col.col_type})"
                if col.logical_name != col.name:
                    col_desc += f" - {col.logical_name}"
                if col.description:
                    col_desc += f": {col.description}"
                columns_desc.append(col_desc)

            context_parts.append(
                f"{table_desc}\n" + "\n".join(columns_desc)
            )

        return "\n\n".join(context_parts)
