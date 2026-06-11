# Micro-GenBI — LLM 成本追踪文档

> 版本：v1.0
> 日期：2026-05-28
> 模块：`src/micro_genbi/llm/cost_tracker.py`

---

## 一、概述

`cost_tracker.py` 实现了 Micro-GenBI 的 **LLM 成本追踪模块**，记录每一次 LLM API 调用的 Token 消耗和预估成本，并提供按 Provider / Model / Intent 类型的多维度统计分析。

### 设计目标

- **透明可控**：每次调用都有记录，成本一目了然
- **多维度分析**：支持按时间、Provider、Model、Intent 类型分组
- **告警机制**：支持日/月成本上限告警
- **导出能力**：支持 CSV 导出，便于财务分析

---

## 二、核心数据模型

### 2.1 LLMCallRecord（单次调用记录）

```python
@dataclass
class LLMCallRecord:
    timestamp: str          # ISO 格式时间戳
    provider: str           # 提供商: deepseek / openai / ollama
    model: str              # 模型名: deepseek-chat / gpt-4o / ollama-local
    prompt_tokens: int      # 输入 Token 数
    completion_tokens: int  # 输出 Token 数
    total_tokens: int       # 总 Token 数
    duration_ms: float      # 调用耗时（毫秒）
    success: bool           # 是否成功
    error: Optional[str]    # 错误信息
    cost_usd: float         # 预估成本（USD）
    intent_type: Optional[str]  # 意图类型（用于分类统计）
```

### 2.2 CostSummary（成本汇总）

```python
@dataclass
class CostSummary:
    total_calls: int              # 总调用次数
    successful_calls: int          # 成功次数
    failed_calls: int             # 失败次数
    total_prompt_tokens: int      # 总输入 Token
    total_completion_tokens: int   # 总输出 Token
    total_tokens: int             # 总 Token
    total_cost_usd: float         # 总成本（USD）
    by_provider: dict[str, float] # 按 Provider 分组成本
    by_model: dict[str, float]    # 按 Model 分组成本
    by_intent: dict[str, int]    # 按 Intent 分组 Token 消耗
```

---

## 三、Token 单价配置

### 3.1 官方定价（USD / 1M Tokens）

| Provider | Model | Input ($/1M) | Output ($/1M) |
|----------|-------|-------------|---------------|
| DeepSeek | `deepseek-chat` | $0.27 | $1.10 |
| DeepSeek | `deepseek-reasoner` | $0.27 | $1.10 |
| OpenAI | `gpt-4o` | $2.50 | $10.00 |
| OpenAI | `gpt-4o-mini` | $0.15 | $0.60 |
| OpenAI | `gpt-3.5-turbo` | $0.50 | $1.50 |
| Ollama | `ollama-local` | $0.00 | $0.00 |

> **注意**：价格基于官方公开定价（2026年5月），实际费用以各平台账单为准。

### 3.2 成本计算公式

```
cost = (prompt_tokens / 1_000_000) × input_price
     + (completion_tokens / 1_000_000) × output_price
```

### 3.3 自定义单价

如需使用其他模型，可在初始化时扩展 `TOKEN_PRICING`：

```python
TOKEN_PRICING["custom-model"] = {"input": 1.0, "output": 2.0}
```

---

## 四、API 参考

### 4.1 LLMCostTracker 类

#### `__init__(daily_cost_limit: float = 10.0, monthly_cost_limit: float = 1000.0)`

初始化成本追踪器，支持设置日/月成本上限。

```python
tracker = LLMCostTracker(
    daily_cost_limit=50.0,    # 日成本上限 $50
    monthly_cost_limit=1000.0 # 月成本上限 $1000
)
```

#### `record(...) -> LLMCallRecord`

记录一次 LLM 调用：

```python
record = tracker.record(
    provider="deepseek",
    model="deepseek-chat",
    prompt_tokens=1500,
    completion_tokens=350,
    duration_ms=1200,
    success=True,
    intent_type="count_aggregate",
)
```

#### `summary() -> CostSummary`

获取当前所有记录的成本汇总：

```python
summary = tracker.summary()
print(f"总成本: ${summary.total_cost_usd:.4f}")
print(f"按 Provider: {summary.by_provider}")
```

#### `summary_by_date(days: int = 7) -> dict[str, float]`

获取最近 N 天的每日成本趋势：

```python
trend = tracker.summary_by_date(days=30)
# {'2026-05-01': 2.50, '2026-05-02': 1.80, ...}
```

#### `get_recent_records(limit: int = 10) -> list[dict]`

获取最近的调用记录：

```python
records = tracker.get_recent_records(limit=20)
for r in records:
    print(f"{r['timestamp']} | {r['model']} | ${r['cost_usd']:.4f}")
```

#### `export_csv(filepath: str) -> None`

导出所有记录到 CSV 文件：

```python
tracker.export_csv("/tmp/llm_cost_2026_05.csv")
```

#### `reset() -> None`

重置所有统计数据（保留记录列表）。

### 4.2 全局快捷函数

```python
from micro_genbi.llm.cost_tracker import (
    get_cost_tracker,
    record_llm_call,
)

# 获取全局追踪器
tracker = get_cost_tracker()

# 快速记录一次调用
record_llm_call(
    provider="deepseek",
    model="deepseek-chat",
    prompt_tokens=1000,
    completion_tokens=200,
    duration_ms=800,
)
```

---

## 五、告警机制

### 5.1 成本上限检查

每次 `record()` 调用时自动检查日/月成本是否超出上限：

```python
warnings = tracker._check_cost_limits()
# 返回格式:
# [
#     {"type": "daily_limit", "limit": 10.0, "current": 12.50,
#      "message": "日成本 $12.5000 已超出上限 $10.0"},
#     {"type": "monthly_limit", "limit": 1000.0, "current": 1050.00,
#      "message": "月成本 $1050.0000 已超出上限 $1000.0"},
# ]
```

### 5.2 告警集成建议

```python
from micro_genbi.llm.cost_tracker import get_cost_tracker

tracker = get_cost_tracker()

# 在 LLM 调用后检查
original_call = llm_client.chat
def monitored_call(*args, **kwargs):
    result = original_call(*args, **kwargs)
    warnings = tracker._check_cost_limits()
    if warnings:
        for w in warnings:
            send_alert(w["message"])  # 接入告警系统
    return result
```

---

## 六、与 API 端点的对应关系

### 6.1 后端 API 端点

| 端点 | 方法 | 对应功能 |
|------|------|---------|
| `/admin/llm/cost` | GET | 获取 LLM 成本统计 |
| `/admin/llm/cost/export` | GET | 导出成本报告 CSV |

### 6.2 前端集成

前端 `AdminDashboardView` 组件通过 `adminApi.getCost()` 和 `adminApi.getCostByUser()` 调用这些端点，在"成本分析"标签页展示。

---

## 七、使用示例

### 7.1 在 LLM 客户端中集成

```python
import time
from micro_genbi.llm.cost_tracker import get_cost_tracker

class DeepSeekClient:
    def __init__(self):
        self.tracker = get_cost_tracker()

    def chat(self, messages: list[dict]) -> str:
        start = time.time()

        # 调用 LLM
        response = self._call_api(messages)

        # 记录成本
        duration_ms = (time.time() - start) * 1000
        self.tracker.record(
            provider="deepseek",
            model="deepseek-chat",
            prompt_tokens=response.usage.prompt_tokens,
            completion_tokens=response.usage.completion_tokens,
            duration_ms=duration_ms,
            success=response.error is None,
            error=response.error,
            intent_type=get_current_intent(),
        )

        return response.content
```

### 7.2 月度成本报告生成

```python
from micro_genbi.llm.cost_tracker import get_cost_tracker

def generate_monthly_report(year: int, month: int) -> dict:
    tracker = get_cost_tracker()

    summary = tracker.summary()
    trend = tracker.summary_by_date(days=30)

    return {
        "period": f"{year}-{month:02d}",
        "total_cost_usd": summary.total_cost_usd,
        "total_calls": summary.total_calls,
        "total_tokens": summary.total_tokens,
        "by_provider": summary.by_provider,
        "by_model": summary.by_model,
        "daily_trend": trend,
    }
```

---

## 八、注意事项

1. **成本为预估**：所有成本基于官方公开定价计算，实际账单可能因用量折扣、API 版本等因素有所不同。
2. **Ollama 本地免费**：`ollama-local` 模型的单价为 $0.00，适合开发测试环境。
3. **记录持久化**：当前 `LLMCostTracker` 仅在内存中存储，重启后会清空。如需持久化，建议定期 `export_csv()` 或接入数据库。
4. **线程安全**：`LLMCostTracker` 的 `record()` 方法是线程安全的，可用于多线程场景。

---

## 九、配置参考

| 配置项 | 说明 | 默认值 |
|--------|------|--------|
| `daily_cost_limit` | 日成本上限（USD） | $10.0 |
| `monthly_cost_limit` | 月成本上限（USD） | $1000.0 |

可通过环境变量覆盖：

```bash
# .env
LLM_DAILY_COST_LIMIT=50.0
LLM_MONTHLY_COST_LIMIT=5000.0
```
