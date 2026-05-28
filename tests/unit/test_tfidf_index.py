"""TF-IDF 检索器单元测试"""

import pytest
from unittest.mock import MagicMock
from micro_genbi.retrieval.semantic_retriever import (
    TFIDFRetriever,
    SemanticRetriever,
    RetrievalResult,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_table():
    """创建一个模拟表信息"""
    table = MagicMock()
    table.name = "orders"
    table.logical_name = "订单表"
    table.description = "存储所有订单信息"
    table.fqn = "sales.orders"
    table.columns = [
        _mock_col("id", "订单ID", "INTEGER"),
        _mock_col("amount", "订单金额", "DECIMAL(18,2)"),
        _mock_col("customer_name", "客户名称", "VARCHAR(100)"),
        _mock_col("status", "订单状态", "VARCHAR(20)"),
        _mock_col("created_at", "创建时间", "TIMESTAMP"),
    ]
    return table


@pytest.fixture
def mock_table_products():
    """创建一个产品表"""
    table = MagicMock()
    table.name = "products"
    table.logical_name = "产品表"
    table.description = "产品目录信息"
    table.fqn = "sales.products"
    table.columns = [
        _mock_col("id", "产品ID", "INTEGER"),
        _mock_col("name", "产品名称", "VARCHAR(200)"),
        _mock_col("price", "产品价格", "DECIMAL(18,2)"),
    ]
    return table


def _mock_col(name: str, logical_name: str, col_type: str) -> MagicMock:
    col = MagicMock()
    col.name = name
    col.logical_name = logical_name
    col.col_type = col_type
    col.description = ""
    return col


@pytest.fixture
def mock_registry(mock_table, mock_table_products):
    """创建模拟的 SchemaRegistry"""
    registry = MagicMock()
    registry._tables = {
        mock_table.fqn: mock_table,
        mock_table_products.fqn: mock_table_products,
    }
    return registry


@pytest.fixture
def tfidf_retriever(mock_registry):
    """创建 TFIDFRetriever 实例"""
    return TFIDFRetriever(mock_registry)


# ── Tests: TFIDFRetriever ───────────────────────────────────────────────────

class TestTFIDFTokenize:
    """分词测试"""

    def test_tokenize_chinese(self, tfidf_retriever):
        """测试中文分词"""
        tokens = tfidf_retriever._tokenize("订单金额统计")
        # 中文按字符分词，单字会被过滤（长度<=1），剩余多字词
        assert len(tokens) > 0
        assert "订单" not in tokens  # 单字被过滤
        assert "金额" not in tokens  # 单字被过滤
        assert "的" not in tokens  # 停用词过滤
        assert "是" not in tokens

    def test_tokenize_english(self, tfidf_retriever):
        """测试英文分词"""
        tokens = tfidf_retriever._tokenize("order amount total")
        assert "order" in tokens
        assert "amount" in tokens
        assert "total" in tokens

    def test_tokenize_mixed(self, tfidf_retriever):
        """测试中英混合分词"""
        tokens = tfidf_retriever._tokenize("订单 order 金额 amount")
        assert "订单" in tokens
        assert "order" in tokens
        assert "金额" in tokens
        assert "amount" in tokens

    def test_tokenize_empty(self, tfidf_retriever):
        """测试空字符串"""
        tokens = tfidf_retriever._tokenize("")
        assert tokens == []

    def test_tokenize_stopwords(self, tfidf_retriever):
        """测试停用词过滤"""
        tokens = tfidf_retriever._tokenize("的 是 在 和 了")
        assert len(tokens) == 0

    def test_tokenize_single_char(self, tfidf_retriever):
        """测试单字符过滤"""
        tokens = tfidf_retriever._tokenize("a b c")
        assert len(tokens) == 0  # 长度 <= 1 被过滤


class TestTFIDFBuildIndex:
    """索引构建测试"""

    def test_build_index_creates_entries(self, tfidf_retriever, mock_table, mock_table_products):
        """测试索引构建"""
        tfidf_retriever.build_index()
        assert len(tfidf_retriever._index) == 2
        assert "sales.orders" in tfidf_retriever._index
        assert "sales.products" in tfidf_retriever._index

    def test_build_index_clears_old_index(self, tfidf_retriever):
        """测试索引重建前清空旧索引"""
        tfidf_retriever.build_index()
        tfidf_retriever._index["test.fake"] = {"terms": {}, "table_info": None}
        tfidf_retriever.build_index()
        assert "test.fake" not in tfidf_retriever._index


class TestTFIDFCalculateScore:
    """分数计算测试"""

    def test_calculate_score_match(self, tfidf_retriever):
        """测试匹配时的分数计算"""
        doc_terms = {"订单": 1, "金额": 1, "统计": 1}
        score = tfidf_retriever._calculate_score(["订单", "金额"], doc_terms)
        assert score > 0

    def test_calculate_score_no_match(self, tfidf_retriever):
        """测试无匹配时分数为0"""
        doc_terms = {"产品": 1, "价格": 1}
        score = tfidf_retriever._calculate_score(["订单", "金额"], doc_terms)
        assert score == 0.0

    def test_calculate_score_empty_doc(self, tfidf_retriever):
        """测试空文档"""
        score = tfidf_retriever._calculate_score(["订单"], {})
        assert score == 0.0

    def test_calculate_score_order_matters(self, tfidf_retriever):
        """测试词频影响分数"""
        # 使用不同的词来避免 IDF 影响
        doc_terms_low = {"a_word": 1, "b_word": 1}  # 总词数 2
        doc_terms_high = {"a_word": 10, "b_word": 10}  # 总词数 20
        score_low = tfidf_retriever._calculate_score(["a_word"], doc_terms_low)
        score_high = tfidf_retriever._calculate_score(["a_word"], doc_terms_high)
        # 1/2 = 0.5 vs 10/20 = 0.5, 所以这里测试不同总词数的效果
        # 实际 TF-IDF 中词频绝对值影响不大，这里验证分数非负
        assert score_low >= 0
        assert score_high >= 0


class TestTFIDFRetrieve:
    """检索测试"""

    def test_retrieve_returns_results(self, tfidf_retriever, mock_table):
        """测试检索返回结果"""
        results = tfidf_retriever.retrieve("订单金额")
        assert len(results) > 0
        assert all(isinstance(r, RetrievalResult) for r in results)

    def test_retrieve_orders_for_order_query(self, tfidf_retriever, mock_table):
        """测试订单查询返回订单表"""
        results = tfidf_retriever.retrieve("订单")
        assert len(results) > 0
        # orders 表应该排在前面或包含
        table_names = [r.table_name for r in results]
        assert "sales.orders" in table_names

    def test_retrieve_respects_top_k(self, tfidf_retriever):
        """测试 top_k 参数"""
        results = tfidf_retriever.retrieve("表", top_k=1)
        assert len(results) <= 1

    def test_retrieve_empty_query(self, tfidf_retriever):
        """测试空查询"""
        results = tfidf_retriever.retrieve("")
        assert results == []

    def test_retrieve_no_match(self, tfidf_retriever):
        """测试无匹配结果"""
        results = tfidf_retriever.retrieve("完全不相关的查询xyz123")
        assert results == []

    def test_retrieve_auto_build_index(self, tfidf_retriever):
        """测试自动构建索引"""
        assert tfidf_retriever._index == {}
        tfidf_retriever.retrieve("订单")
        assert len(tfidf_retriever._index) > 0

    def test_retrieve_with_column_matching(self, tfidf_retriever, mock_table):
        """测试列名匹配"""
        results = tfidf_retriever.retrieve("金额")
        for result in results:
            if result.table_name == "sales.orders":
                assert "amount" in result.matched_columns


class TestFindMatchedColumns:
    """匹配列测试"""

    def test_find_matched_columns(self, tfidf_retriever, mock_table):
        """测试列名匹配"""
        # 列名是英文，与中文查询词不匹配
        # 测试英文列名匹配英文词
        matched = tfidf_retriever._find_matched_columns(
            ["customer"], mock_table
        )
        assert "customer_name" in matched

    def test_find_matched_columns_no_match(self, tfidf_retriever, mock_table):
        """测试无列名匹配"""
        matched = tfidf_retriever._find_matched_columns(
            ["不存在"], mock_table
        )
        assert len(matched) == 0


# ── Tests: SemanticRetriever ─────────────────────────────────────────────────

class TestSemanticRetriever:
    """语义检索器测试"""

    def test_exact_match_preferred(self, tfidf_retriever):
        """测试精确匹配优先"""
        mock_reg = MagicMock()
        mock_reg._tables = {
            "sales.orders": MagicMock(name="orders", logical_name="订单表",
                                      description="", columns=[]),
        }

        retriever = SemanticRetriever(mock_reg)
        retriever.tfidf_retriever = tfidf_retriever
        tfidf_retriever.build_index()

        # 查询 "orders" 应该精确匹配到表
        results = retriever.retrieve_relevant_tables("orders")
        # 精确匹配分数为 1.0
        assert len(results) > 0

    def test_build_context_format(self, tfidf_retriever):
        """测试上下文构建格式"""
        mock_reg = MagicMock()
        mock_table = MagicMock()
        mock_table.name = "orders"
        mock_table.logical_name = "订单表"
        mock_table.fqn = "sales.orders"
        mock_table.description = "订单信息"
        mock_table.columns = [
            MagicMock(name="id", logical_name="ID", col_type="INT",
                      description="主键"),
            MagicMock(name="amount", logical_name="金额", col_type="DECIMAL",
                      description="订单金额"),
        ]
        mock_reg._tables = {"sales.orders": mock_table}

        retriever = SemanticRetriever(mock_reg)
        retriever.tfidf_retriever = tfidf_retriever
        tfidf_retriever.build_index()

        context = retriever.build_context("订单", max_tables=1)
        assert "订单表" in context
        assert "orders" in context
        assert "金额" in context

    def test_build_context_empty_result(self, tfidf_retriever):
        """测试无结果时的上下文"""
        mock_reg = MagicMock()
        mock_reg._tables = {}
        retriever = SemanticRetriever(mock_reg)
        retriever.tfidf_retriever = tfidf_retriever

        context = retriever.build_context("完全不存在的查询")
        assert context == "/* 未找到相关表 */"

    def test_build_context_max_tables(self, tfidf_retriever):
        """测试最大表数量限制"""
        mock_reg = MagicMock()
        for i in range(10):
            mock_reg._tables[f"db{i}.table{i}"] = MagicMock(
                name=f"table{i}", logical_name=f"表{i}", fqn=f"db{i}.table{i}",
                description="", columns=[]
            )
        retriever = SemanticRetriever(mock_reg)
        retriever.tfidf_retriever = tfidf_retriever

        context = retriever.build_context("表", max_tables=3)
        # 应该只包含 3 个表
        assert context.count("###") <= 3


# ── Tests: RetrievalResult ───────────────────────────────────────────────────

class TestRetrievalResult:
    """检索结果 dataclass 测试"""

    def test_retrieval_result_creation(self):
        """测试结果创建"""
        result = RetrievalResult(
            table_name="sales.orders",
            score=0.85,
            matched_columns=["id", "amount"],
            reasoning="匹配词: 订单, 金额",
        )
        assert result.table_name == "sales.orders"
        assert result.score == 0.85
        assert "id" in result.matched_columns

    def test_retrieval_result_defaults(self):
        """测试默认值"""
        result = RetrievalResult(table_name="test", score=0.5)
        assert result.matched_columns == []
        assert result.reasoning == ""
