# Micro-GenBI — Prompt 模板系统文档

> 版本：v1.0
> 日期：2026-05-28
> 模块：`src/micro_genbi/llm/prompts.py`

---

## 一、概述

`prompts.py` 是 Micro-GenBI 的**核心 Prompt 工程模块**，包含：

1. **多数据库方言适配**：MySQL / PostgreSQL / SQLite 三种方言的动态切换
2. **SQL 生成 System Prompt**：含方言语法提示、字段别名规范和 Few-shot 示例
3. **错误修正 Prompt**：SQL 自愈（Self-Correction）阶段使用的修正模板
4. **结果解读 Prompt**：LLM 解读查询结果的自然语言描述
5. **Prompt 模板注册表**：统一管理和渲染所有 Prompt

---

## 二、方言配置

### 2.1 支持的方言

| 方言 | 标识符 | 引用字符 | 大小写敏感 |
|------|--------|---------|-----------|
| MySQL | `mysql` | `` ` `` (反引号) | 否 |
| PostgreSQL | `postgresql` | `"` (双引号) | 否（ILIKE） |
| SQLite | `sqlite` | `"` (双引号) | 是（LIKE） |

### 2.2 方言配置项

每种方言提供以下语法模板：

| 配置项 | 说明 | MySQL 示例 | PostgreSQL 示例 |
|--------|------|-----------|----------------|
| `date_format` | 日期格式化 | `DATE_FORMAT(col, '%Y-%m-%d')` | `TO_CHAR(col, 'YYYY-MM-DD')` |
| `date_sub` | 日期减法 | `DATE_SUB(col, INTERVAL n unit)` | `col - INTERVAL 'n unit'` |
| `date_add` | 日期加法 | `DATE_ADD(col, INTERVAL n unit)` | `col + INTERVAL 'n unit'` |
| `date_diff` | 日期差 | `DATEDIFF(col1, col2)` | `DATE(col1) - DATE(col2)` |
| `concat` | 字符串拼接 | `CONCAT(col1, col2)` | `CONCAT(col1, col2)` |
| `string_agg` | 聚合拼接 | `GROUP_CONCAT(col SEPARATOR ',')` | `STRING_AGG(col, ',')` |
| `ifnull` | 空值处理 | `IFNULL(col, default)` | `COALESCE(col, default)` |
| `cast_int` | 整数转换 | `CAST(col AS SIGNED)` | `col::INTEGER` |
| `cast_float` | 浮点转换 | `CAST(col AS DECIMAL(18,2))` | `col::DECIMAL(18,2)` |

### 2.3 方言选择逻辑

```python
from micro_genbi.llm.prompts import get_dialect_config, DIALECT_CONFIG

# 自动选择
dialect = "mysql"  # 可从数据库连接配置中获取
cfg = get_dialect_config(dialect)
print(cfg["quote_char"])  # "`"
```

---

## 三、核心 Prompt 模板

### 3.1 SQL 生成 System Prompt

`build_sql_system_prompt(schema_context, dialect)` 生成完整的 SQL 生成 Prompt：

```
你是一个专业的 SQL 数据分析助手，擅长将自然语言问题转换为精确的 SQL 查询。

【数据库类型】
{cfg['name']}  ← 例如 "MySQL"

【数据库语义配置】
{schema_context}  ← 包含表结构、列描述、别名等

【输出要求】
1. 只生成 SELECT 查询，禁止任何写操作（INSERT/UPDATE/DELETE/DROP/TRUNCATE/ALTER/CREATE）
2. 必须包含 LIMIT（默认 1000）
3. 禁止使用 SELECT *，必须列出需要的字段
4. 使用清晰的列别名（AS），推荐使用中文别名提高可读性
5. GROUP BY 后出现的字段必须在 SELECT 中出现，或使用聚合函数包裹
6. 字段名、表名使用 {quote_char} 包裹

【方言语法提示】
- 时间函数：DATE_FORMAT(col, '%Y-%m-%d')
- 日期计算：DATE_SUB(col, INTERVAL 7 DAY)（7天前）
- 字符串拼接：CONCAT(col1, ',', col2)
- 空值处理：IFNULL(col, 0)
- 时间过滤示例：WHERE DATE_FORMAT(created_at) >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)

【字段别名规范】
示例：
SELECT
    `dept_name` AS "部门",
    SUM(`amount`) AS "报销总额",
    COUNT(DISTINCT `employee_id`) AS "员工人数",
    AVG(`amount`) AS "平均金额"
FROM `dept_expense`
...

【MySQL SQL 示例】
...
```

### 3.2 错误修正 Prompt

`ERROR_CORRECTION_PROMPT` 用于 SQL 执行失败后的自动修正：

```
你是一个专业的 SQL 调试助手。

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
```

### 3.3 错误类型归因 Prompt

`ERROR_CLASSIFICATION_PROMPT` 用于将 SQL 错误分类为以下类型：

| 类型 | 说明 |
|------|------|
| `SYNTAX_ERROR` | SQL 语法错误 |
| `TABLE_NOT_FOUND` | 表或列不存在 |
| `TYPE_MISMATCH` | 数据类型不匹配 |
| `PERMISSION_DENIED` | 权限不足 |
| `TIMEOUT` | 查询超时 |
| `UNKNOWN` | 未知错误 |

### 3.4 结果解读 Prompt

`RESULT_INTERPRET_PROMPT` 用于 LLM 分析查询结果：

```
你是一个专业的数据分析师。

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
```

---

## 四、Prompt 模板注册表

```python
PROMPT_TEMPLATES = {
    "sql_generation": build_sql_system_prompt("{schema_context}", "postgresql"),
    "error_correction": ERROR_CORRECTION_PROMPT,
    "error_classification": ERROR_CLASSIFICATION_PROMPT,
    "result_interpret": RESULT_INTERPRET_PROMPT,
    "multi_db": MULTI_DB_SYSTEM_PROMPT,
}
```

---

## 五、渲染函数

### 5.1 `render_sql_prompt(...)`

方言自适应的 SQL 生成 Prompt 渲染：

```python
from micro_genbi.llm.prompts import render_sql_prompt

prompt = render_sql_prompt(
    user_query="各部门上月的报销总额是多少？",
    schema_context="表: dept_expense\n列: dept_name, amount, submit_date",
    dialect="mysql",
    include_examples=True,
)
```

### 5.2 `render_error_correction_prompt(...)`

错误修正 Prompt 渲染：

```python
from micro_genbi.llm.prompts import render_error_correction_prompt

prompt = render_error_correction_prompt(
    user_query="各部门报销总额",
    original_sql="SELECT dept_name, SUM(amount) FROM dept_expense",
    error_message="Column 'dept_name' not found in group by clause",
    dialect="mysql",
)
```

### 5.3 `render_multi_db_prompt(...)`

多库查询 Prompt 渲染：

```python
from micro_genbi.llm.prompts import render_multi_db_prompt

prompt = render_multi_db_prompt(
    user_query="统计各油库库存总量",
    schema_context="...多库 Schema...",
    query_mode="aggregate",  # aggregate / federated / hybrid
)
```

---

## 六、Few-shot 示例

### 6.1 内置示例类型

`SQL_EXAMPLES` 包含 4 种常见意图的示例：

| 意图 | 示例问题 | SQL 模式 |
|------|---------|---------|
| `count_aggregate` | 各部门上月的报销总额是多少？ | SUM + GROUP BY + 时间过滤 |
| `time_trend` | 过去7天每天的订单量是多少？ | DATE + GROUP BY + 时间过滤 |
| `top_n` | 销售额最高的前10名商品是什么？ | SUM + ORDER BY + LIMIT |
| `single_value` | 本月新增了多少客户？ | COUNT + 时间过滤（无 GROUP BY） |

### 6.2 动态生成示例

`_build_dialect_examples(dialect)` 根据目标方言动态生成 Few-shot 示例，确保语法正确。

---

## 七、多库查询模式

`MULTI_DB_SYSTEM_PROMPT` 支持三种跨库查询模式：

| 模式 | 说明 | SQL 特征 |
|------|------|---------|
| `aggregate`（聚合模式） | 同构多库 UNION ALL 后聚合 | `UNION ALL` + `GROUP BY` |
| `federated`（联邦模式） | 异构库分别查询后流式归并 | 各库独立子查询 |
| `hybrid`（混合模式） | 先聚合后关联 | 聚合子查询 + JOIN |

---

## 八、扩展指南

### 8.1 添加新方言

在 `DIALECT_CONFIG` 中添加新条目：

```python
DIALECT_CONFIG["oracle"] = {
    "name": "Oracle",
    "date_format": "TO_CHAR({col}, 'YYYY-MM-DD')",
    "date_sub": "{col} - NUMTODSINTERVAL({n}, '{unit}')",
    "concat": "({col1} || ',' || {col2})",
    "ifnull": "NVL({col}, {default})",
    "quote_char": '"',
    "cast_int": "CAST({col} AS INTEGER)",
    "cast_float": "CAST({col} AS NUMBER(18,2))",
    # ...
}
```

### 8.2 添加新 Prompt 模板

```python
# 添加新模板
CUSTOM_PROMPT = """你的角色是...

【上下文】
{context}

请按要求执行：
"""

# 注册到模板库
PROMPT_TEMPLATES["custom_task"] = CUSTOM_PROMPT

# 创建渲染函数
def render_custom_prompt(context: str) -> str:
    return CUSTOM_PROMPT.format(context=context)
```

---

## 九、Prompt 优化建议

### 9.1 Token 预算控制

| 组件 | Token 上限 | 说明 |
|------|-----------|------|
| System Prompt | ~1500 | 包含方言规则和输出要求 |
| Schema Context | ~3000 | 表结构、列描述 |
| User Query | ~500 | 用户问题 |
| Few-shot 示例 | ~1000 | 方言特定示例 |
| **总计** | **~6000** | 留 2000 给 LLM 输出 |

### 9.2 Schema Context 裁剪策略

1. **按相关性**：只包含查询涉及的表
2. **按重要性**：优先保留主表和关联表
3. **按大小**：单个表的列数过多时只保留关键列
4. **按枚举值**：有限枚举值的列提供完整列表

### 9.3 调试技巧

```python
# 打印最终 Prompt（用于调试）
prompt = render_sql_prompt(user_query, schema_context, dialect)
print(f"Prompt tokens (approx): {len(prompt) // 4}")
print(prompt)
```
