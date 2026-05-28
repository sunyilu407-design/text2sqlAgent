"""SQL 生成 Prompt 模板

包含中文优化的 System Prompt、Few-shot 示例和错误修正 Prompt。
支持 MySQL / PostgreSQL / SQLite 三种方言的动态适配。
"""

from __future__ import annotations

from typing import Optional


# ── 方言适配 ──────────────────────────────────────────────────

DIALECT_CONFIG = {
    "mysql": {
        "name": "MySQL",
        "date_format": "DATE_FORMAT({col}, '%Y-%m-%d')",
        "date_sub": "DATE_SUB({col}, INTERVAL {n} {unit})",
        "date_add": "DATE_ADD({col}, INTERVAL {n} {unit})",
        "date_diff": "DATEDIFF({col1}, {col2})",
        "now": "NOW()",
        "concat": "CONCAT({cols})",
        "string_agg": "GROUP_CONCAT({col} SEPARATOR ',')",
        "ifnull": "IFNULL({col}, {default})",
        "limit": "LIMIT {n}",
        "quote_char": "`",
        "like_case": "LIKE",
        "cast_int": "CAST({col} AS SIGNED)",
        "cast_float": "CAST({col} AS DECIMAL(18,2))",
    },
    "postgresql": {
        "name": "PostgreSQL",
        "date_format": "TO_CHAR({col}, 'YYYY-MM-DD')",
        "date_sub": "{col} - INTERVAL '{n} {unit}'",
        "date_add": "{col} + INTERVAL '{n} {unit}'",
        "date_diff": "DATE({col1}) - DATE({col2})",
        "now": "NOW()",
        "concat": "CONCAT({cols})",
        "string_agg": "STRING_AGG({col}, ',')",
        "ifnull": "COALESCE({col}, {default})",
        "limit": "LIMIT {n}",
        "quote_char": '"',
        "like_case": "ILIKE",
        "cast_int": "{col}::INTEGER",
        "cast_float": "{col}::DECIMAL(18,2)",
    },
    "sqlite": {
        "name": "SQLite",
        "date_format": "STRFTIME('%Y-%m-%d', {col})",
        "date_sub": "DATETIME({col}, '-{n} {unit}')",
        "date_add": "DATETIME({col}, '+{n} {unit}')",
        "date_diff": "JULIANDAY({col1}) - JULIANDAY({col2})",
        "now": "DATETIME('now')",
        "concat": "{cols} || ',' || {cols2}",
        "string_agg": "GROUP_CONCAT({col}, ',')",
        "ifnull": "IFNULL({col}, {default})",
        "limit": "LIMIT {n}",
        "quote_char": '"',
        "like_case": "LIKE",
        "cast_int": "CAST({col} AS INTEGER)",
        "cast_float": "CAST({col} AS REAL)",
    },
}


def get_dialect_config(dialect: str) -> dict:
    """获取方言配置"""
    return DIALECT_CONFIG.get(dialect.lower(), DIALECT_CONFIG["postgresql"])


def get_dialect_hint(dialect: str, key: str) -> str:
    """获取方言特定的语法提示"""
    config = get_dialect_config(dialect)
    return config.get(key, key)


# 向后兼容别名
DIALECT_HINTS = DIALECT_CONFIG


def _build_dialect_tips(dialect: str) -> str:
    """根据方言生成具体的语法提示"""
    cfg = get_dialect_config(dialect)
    q = cfg["quote_char"]

    tips = []
    if dialect.lower() == "mysql":
        tips = [
            f"时间函数：{cfg['date_format'].replace('{col}', 'col').replace('%Y-%m-%d', '日期列格式')}",
            f"日期计算：{cfg['date_sub'].replace('{col}', 'DATE').replace('{n} {unit}', '7 DAY')}（7天前）",
            f"字符串拼接：{cfg['concat']}",
            f"空值处理：{cfg['ifnull'].replace('{col}', 'col').replace('{default}', '0')}",
            f"时间过滤示例：WHERE {cfg['date_format'].replace('{col}', 'created_at')} >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)",
        ]
    elif dialect.lower() == "postgresql":
        tips = [
            f"时间函数：{cfg['date_format'].replace('{col}', 'col').replace('YYYY-MM-DD', '日期列格式')}",
            f"日期计算：{cfg['date_sub'].replace('{col}', 'DATE').replace('{n} {unit}', '7 days')}（7天前）",
            f"字符串拼接：CONCAT(col1, ',', col2)",
            f"空值处理：{cfg['ifnull'].replace('{col}', 'col').replace('{default}', '0')}",
            f"大小写不敏感：使用 ILIKE 而非 LIKE",
            f"时间过滤示例：WHERE {cfg['date_format'].replace('{col}', 'created_at')} >= (NOW() - INTERVAL '1 month')::DATE",
        ]
    else:  # sqlite
        tips = [
            f"时间函数：{cfg['date_format'].replace('{col}', 'col').replace('%Y-%m-%d', '日期列格式')}",
            f"日期计算：{cfg['date_sub'].replace('{col}', 'DATE').replace('{n} {unit}', '7 days')}（7天前）",
            f"空值处理：{cfg['ifnull'].replace('{col}', 'col').replace('{default}', '0')}",
            f"时间过滤示例：WHERE {cfg['date_format'].replace('{col}', 'created_at')} >= DATE('now', '-1 month')",
        ]

    return "\n".join(f"- {t}" for t in tips)


def _build_dialect_examples(dialect: str) -> str:
    """生成方言特定的 SQL 示例"""
    q = get_dialect_hint(dialect, "quote_char")

    if dialect.lower() == "mysql":
        return f"""【{dialect} SQL 示例】
SELECT
    {q}dept_name{q} AS "部门",
    SUM({q}amount{q}) AS "报销总额",
    COUNT(*) AS "报销笔数",
    AVG({q}amount{q}) AS "平均单笔金额"
FROM {q}dept_expense{q}
WHERE {q}submit_date{q} >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
  AND {q}submit_date{q} < DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY {q}dept_name{q}
ORDER BY SUM({q}amount{q}) DESC
LIMIT 1000

时间趋势示例：
SELECT
    DATE_FORMAT({q}order_date{q}, '%Y-%m') AS "月份",
    COUNT(*) AS "订单数"
FROM {q}orders{q}
WHERE {q}order_date{q} >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)
GROUP BY DATE_FORMAT({q}order_date{q}, '%Y-%m')
ORDER BY DATE_FORMAT({q}order_date{q}, '%Y-%m')
LIMIT 100"""

    elif dialect.lower() == "postgresql":
        return f"""【{dialect} SQL 示例】
SELECT
    {q}dept_name{q} AS "部门",
    SUM({q}amount{q}) AS "报销总额",
    COUNT(*) AS "报销笔数",
    AVG({q}amount{q})::DECIMAL(18,2) AS "平均单笔金额"
FROM {q}dept_expense{q}
WHERE {q}submit_date{q} >= (NOW() - INTERVAL '1 month')::DATE
GROUP BY {q}dept_name{q}
ORDER BY SUM({q}amount{q}) DESC
LIMIT 1000

时间趋势示例：
SELECT
    TO_CHAR({q}order_date{q}, 'YYYY-MM') AS "月份",
    COUNT(*) AS "订单数"
FROM {q}orders{q}
WHERE {q}order_date{q} >= (NOW() - INTERVAL '3 months')::DATE
GROUP BY TO_CHAR({q}order_date{q}, 'YYYY-MM')
ORDER BY TO_CHAR({q}order_date{q}, 'YYYY-MM')
LIMIT 100"""

    else:  # sqlite
        return f"""【{dialect} SQL 示例】
SELECT
    {q}dept_name{q} AS "部门",
    SUM({q}amount{q}) AS "报销总额",
    COUNT(*) AS "报销笔数",
    AVG({q}amount{q}) AS "平均单笔金额"
FROM {q}dept_expense{q}
WHERE {q}submit_date{q} >= DATE('now', '-1 month')
GROUP BY {q}dept_name{q}
ORDER BY SUM({q}amount{q}) DESC
LIMIT 1000

时间趋势示例：
SELECT
    STRFTIME('%Y-%m', {q}order_date{q}) AS "月份",
    COUNT(*) AS "订单数"
FROM {q}orders{q}
WHERE {q}order_date{q} >= DATE('now', '-3 months')
GROUP BY STRFTIME('%Y-%m', {q}order_date{q})
ORDER BY STRFTIME('%Y-%m', {q}order_date{q})
LIMIT 100"""


def build_sql_system_prompt(schema_context: str, dialect: str = "postgresql") -> str:
    """构建 SQL 生成 System Prompt（方言自适应）"""
    dialect_tips = _build_dialect_tips(dialect)
    dialect_examples = _build_dialect_examples(dialect)
    cfg = get_dialect_config(dialect)
    q = cfg["quote_char"]

    return f"""你是一个专业的 SQL 数据分析助手，擅长将自然语言问题转换为精确的 SQL 查询。

【数据库类型】
{cfg['name']}

【数据库语义配置】
{schema_context}

【输出要求】
1. 只生成 SELECT 查询，禁止任何写操作（INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE）
2. 必须包含 LIMIT（默认 1000）
3. 禁止使用 SELECT *，必须列出需要的字段
4. 使用清晰的列别名（AS），推荐使用中文别名提高可读性
5. GROUP BY 后出现的字段必须在 SELECT 中出现，或使用聚合函数包裹
6. 字段名、表名使用 {q} 包裹（{cfg['name']} 语法）

【方言语法提示】
{dialect_tips}

【字段别名规范】
示例：
SELECT
    {q}dept_name{q} AS "部门",
    SUM({q}amount{q}) AS "报销总额",
    COUNT(DISTINCT {q}employee_id{q}) AS "员工人数",
    AVG({q}amount{q}) AS "平均金额"
FROM {q}dept_expense{q}
...

{dialect_examples}

请根据以下问题生成 SQL（使用 {cfg['name']} 语法）：
"""


# ── 便捷函数（保持向后兼容）─────────────────────────────────────

SQL_SYSTEM_PROMPT = build_sql_system_prompt("{schema_context}", "postgresql")
MULTI_DB_SYSTEM_PROMPT = """你是一个专业的跨数据库 SQL 分析助手。

【数据库语义配置】
{schema_context}

【查询模式】
{query_mode}

【任务】
根据用户问题生成跨库 SQL 查询。

【模式说明】
- aggregate（聚合模式）：同构多库 UNION ALL 后聚合
- federated（联邦模式）：异构库分别查询后流式归并
- hybrid（混合模式）：先聚合后关联

【输出要求】
1. 只生成 SELECT 查询
2. 必须包含 LIMIT
3. 使用表的全限定名（"db_id"."table_name"）
4. 包含库标识列用于归并

请生成 SQL：
"""


# ── SQL 生成 Few-shot 示例（PostgreSQL 基准）──────────────────

SQL_EXAMPLES = [
    {
        "intent": "count_aggregate",
        "input": "各部门上月的报销总额是多少？",
        "output": """```sql
SELECT
    "dept_name" AS "部门",
    SUM("amount") AS "报销总额",
    COUNT(*) AS "报销笔数",
    AVG("amount")::DECIMAL(18,2) AS "平均单笔金额"
FROM "dept_expense"
WHERE "submit_date" >= (NOW() - INTERVAL '1 month')::DATE
GROUP BY "dept_name"
ORDER BY SUM("amount") DESC
LIMIT 1000
```"""
    },
    {
        "intent": "time_trend",
        "input": "过去7天每天的订单量是多少？",
        "output": """```sql
SELECT
    DATE("order_date") AS "日期",
    COUNT(*) AS "订单数",
    SUM("total_amount") AS "订单总额"
FROM "orders"
WHERE "order_date" >= (NOW() - INTERVAL '7 days')::DATE
GROUP BY DATE("order_date")
ORDER BY DATE("order_date") ASC
LIMIT 1000
```"""
    },
    {
        "intent": "top_n",
        "input": "销售额最高的前10名商品是什么？",
        "output": """```sql
SELECT
    "product_name" AS "商品名称",
    "category" AS "类别",
    SUM("quantity") AS "销售数量",
    SUM("amount") AS "销售额"
FROM "sales"
GROUP BY "product_name", "category"
ORDER BY SUM("amount") DESC
LIMIT 10
```"""
    },
    {
        "intent": "single_value",
        "input": "本月新增了多少客户？",
        "output": """```sql
SELECT
    COUNT(*) AS "新增客户数"
FROM "customers"
WHERE "created_at" >= DATE_TRUNC('month', NOW())::DATE
```"""
    },
]

# ── SQL 错误修正 Prompt ────────────────────────────────────────

ERROR_CORRECTION_PROMPT = """你是一个专业的 SQL 调试助手。

【原始问题】
{user_query}

【原始生成的 SQL】
```sql
{original_sql}
```

【执行错误】
```
{error_message}
```

【数据库类型】
{dialect}

【任务】
1. 分析错误原因
2. 修正 SQL
3. 确保修正后的 SQL：
   - 只生成 SELECT 查询
   - 必须包含 LIMIT
   - 使用正确的 {dialect} 语法

请只输出修正后的 SQL（使用 ```sql 包裹）：
"""

# ── 错误类型归因 Prompt ────────────────────────────────────────

ERROR_CLASSIFICATION_PROMPT = """分析以下 SQL 执行错误，判断错误类型：

【错误信息】
```
{error_message}
```

【SQL 语句】
```sql
{sql}
```

请判断错误类型（只输出一个）：
1. SYNTAX_ERROR - SQL 语法错误
2. TABLE_NOT_FOUND - 表或列不存在
3. TYPE_MISMATCH - 数据类型不匹配
4. PERMISSION_DENIED - 权限不足
5. TIMEOUT - 查询超时
6. UNKNOWN - 未知错误
"""

# ── 结果解读 Prompt ────────────────────────────────────────────

RESULT_INTERPRET_PROMPT = """你是一个专业的数据分析师。

【用户问题】
{user_query}

【SQL 查询】
```sql
{sql}
```

【查询结果】
{result_data}

【任务】
1. 简要总结查询结果
2. 指出关键发现或异常
3. 用自然语言解释数据含义

请用简洁的中文回答：
"""


# ── Prompt 模板注册表 ──────────────────────────────────────────

PROMPT_TEMPLATES = {
    "sql_generation": build_sql_system_prompt("{schema_context}", "postgresql"),
    "error_correction": ERROR_CORRECTION_PROMPT,
    "error_classification": ERROR_CLASSIFICATION_PROMPT,
    "result_interpret": RESULT_INTERPRET_PROMPT,
    "multi_db": MULTI_DB_SYSTEM_PROMPT,
}


# ── 渲染函数 ──────────────────────────────────────────────────

def render_sql_prompt(
    user_query: str,
    schema_context: str,
    dialect: str = "postgresql",
    include_examples: bool = True,
) -> str:
    """
    渲染 SQL 生成 Prompt（方言自适应）

    Args:
        user_query: 用户问题
        schema_context: Schema 上下文
        dialect: 数据库方言（mysql/postgresql/sqlite）
        include_examples: 是否包含 few-shot 示例

    Returns:
        渲染后的完整 Prompt
    """
    prompt = build_sql_system_prompt(schema_context, dialect)
    prompt += f"\n\n【用户问题】\n{user_query}"

    if include_examples:
        dialect_examples = _build_dialect_examples(dialect)
        prompt += f"\n\n{dialect_examples}"

    return prompt


def render_error_correction_prompt(
    user_query: str,
    original_sql: str,
    error_message: str,
    dialect: str = "postgresql",
) -> str:
    """渲染错误修正 Prompt"""
    return ERROR_CORRECTION_PROMPT.format(
        user_query=user_query,
        original_sql=original_sql,
        error_message=error_message,
        dialect=get_dialect_config(dialect)["name"],
    )


def render_multi_db_prompt(
    user_query: str,
    schema_context: str,
    query_mode: str = "aggregate",
) -> str:
    """渲染多库查询 Prompt"""
    return MULTI_DB_SYSTEM_PROMPT.format(
        schema_context=schema_context,
        query_mode=query_mode,
    )
