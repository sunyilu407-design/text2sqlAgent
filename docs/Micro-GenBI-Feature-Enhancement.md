# Micro-GenBI 功能增强建议

> 基于当前规划的功能优化与新增能力建议
> 版本：v1.0 | 日期：2026-05-25

---

## 一、用户体验增强

### 1.1 查询建议与补全

```python
# src/micro_genbi/intent/query_suggester.py

class QuerySuggester:
    """
    查询建议器

    根据用户输入实时提供查询建议，提升用户体验。
    """

    # 常用查询模板（油库场景）
    OIL_DEPOT_TEMPLATES = [
        # 库存相关
        "各储罐当前液位",
        "今日入库量统计",
        "出库量日报",
        "库存周转率分析",
        # 安全相关
        "最近24小时报警记录",
        "设备运行状态汇总",
        "安全联锁投用率",
        # 生产相关
        "今日加工量统计",
        "产品质量指标",
        "能耗分析报告",
    ]

    # 时间限定词扩展
    TIME_PATTERNS = {
        "今日": "CURDATE()",
        "昨日": "DATE_SUB(CURDATE(), INTERVAL 1 DAY)",
        "本周": "DATE_SUB(CURDATE(), INTERVAL DAYOFWEEK(CURDATE())-1 DAY)",
        "本月": "DATE_FORMAT(CURDATE(), '%Y-%m-01')",
        "上月": "DATE_FORMAT(DATE_SUB(CURDATE(), INTERVAL 1 MONTH), '%Y-%m-01')",
        "最近7天": "DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
        "最近30天": "DATE_SUB(CURDATE(), INTERVAL 30 DAY)",
    }

    def suggest(self, partial_query: str, schema: SchemaMeta) -> list[QuerySuggestion]:
        """
        根据用户输入提供查询建议

        1. 模板匹配补全
        2. Schema 字段联想
        3. 历史查询推荐
        """
        suggestions = []

        # 1. 模板补全
        for template in self.OIL_DEPOT_TEMPLATES:
            if template.startswith(partial_query):
                suggestions.append(QuerySuggestion(
                    text=template,
                    type="template",
                    confidence=0.95,
                ))

        # 2. 字段联想
        for table in schema.tables:
            for col in table.columns:
                if partial_query.lower() in col.logical_name.lower():
                    suggestions.append(QuerySuggestion(
                        text=f"统计{col.logical_name}分布",
                        type="field_based",
                        confidence=0.7,
                        metadata={"table": table.name, "column": col.name},
                    ))

        # 3. 历史推荐
        history_suggestions = await self._get_history_suggestions(partial_query)
        suggestions.extend(history_suggestions)

        return sorted(suggestions, key=lambda x: x.confidence, reverse=True)[:5]

    async def _get_history_suggestions(self, partial: str) -> list[QuerySuggestion]:
        """基于历史查询推荐"""
        # 实现基于用户历史查询的推荐
        pass
```

### 1.2 查询历史与收藏

```python
# src/micro_genbi/service/query_history.py

class QueryHistoryService:
    """
    查询历史服务

    支持：
    - 自动保存所有查询
    - 查询收藏
    - 查询复用
    - 历史搜索
    """

    async def save_query(self, user_id: str, query: QueryRecord) -> str:
        """保存查询记录"""
        record = QueryRecord(
            id=self._generate_id(),
            user_id=user_id,
            natural_query=query.natural_query,
            generated_sql=query.generated_sql,
            tables_used=query.tables_used,
            execution_time_ms=query.execution_time_ms,
            row_count=query.row_count,
            timestamp=datetime.now(),
            session_id=query.session_id,
        )
        await self.db.insert("query_history", record.to_dict())
        return record.id

    async def add_to_favorites(self, user_id: str, query_id: str) -> None:
        """收藏查询"""
        await self.db.insert("query_favorites", {
            "user_id": user_id,
            "query_id": query_id,
            "created_at": datetime.now().isoformat(),
        })

    async def get_favorites(self, user_id: str) -> list[QueryRecord]:
        """获取收藏的查询"""
        # 返回用户收藏的查询列表
        pass

    async def search_history(
        self,
        user_id: str,
        keyword: str,
        date_range: tuple[datetime, datetime] = None,
    ) -> list[QueryRecord]:
        """搜索查询历史"""
        # 支持按关键词、时间范围搜索
        pass
```

### 1.3 实时数据预览

```python
# src/micro_genbi/api/preview.py

@router.post("/api/v1/preview")
async def preview_query(
    query: str,
    session: AsyncSession,
    schema: SchemaMeta,
) -> PreviewResponse:
    """
    实时预览查询结果

    在用户输入时提供实时的数据预览，
    帮助用户验证查询意图是否正确。
    """

    # 1. 解析用户意图
    intent = await classifier.classify(query)

    # 2. 快速生成 SQL（简化版）
    sql = await quick_sql_generator.generate(query, schema, mode="fast")

    # 3. 限制预览范围（只查 5 条）
    preview_sql = f"SELECT * FROM ({sql}) AS t LIMIT 5"

    # 4. 执行预览
    try:
        result = await session.execute(preview_sql)
        rows = result.fetchall()
        columns = result.keys()

        return PreviewResponse(
            sql=sql,
            preview_data=[dict(zip(columns, row)) for row in rows],
            total_hint=f"完整查询将返回约 N 行数据",  # 需要 COUNT
            intent=intent,
        )
    except SQLExecutionError as e:
        return PreviewResponse(
            sql=sql,
            preview_data=[],
            error=str(e),
            intent=intent,
        )
```

### 1.4 SQL 对比与版本

```python
# src/micro_genbi/service/sql_versioning.py

class SQLVersioningService:
    """
    SQL 版本管理

    当用户多次询问相似问题时，保存生成的 SQL 版本，
    方便对比和回退。
    """

    async def save_version(
        self,
        query_id: str,
        sql: str,
        version_note: str = "",
    ) -> str:
        """保存 SQL 版本"""
        version_id = self._generate_id()

        await self.db.insert("sql_versions", {
            "id": version_id,
            "query_id": query_id,
            "sql": sql,
            "version_note": version_note,
            "created_at": datetime.now().isoformat(),
            "is_current": True,
        })

        # 将之前的版本标记为非当前
        await self.db.execute(
            """
            UPDATE sql_versions
            SET is_current = FALSE
            WHERE query_id = ? AND id != ?
            """,
            (query_id, version_id)
        )

        return version_id

    async def compare_versions(
        self,
        version_a: str,
        version_b: str,
    ) -> DiffResult:
        """对比两个 SQL 版本"""
        sql_a = await self._get_version_sql(version_a)
        sql_b = await self._get_version_sql(version_b)

        # 使用 sqlglot 进行 SQL diff
        diff = self._compute_sql_diff(sql_a, sql_b)

        return DiffResult(
            version_a=version_a,
            version_b=version_b,
            additions=diff.additions,
            deletions=diff.deletions,
            changes=diff.changes,
        )

    async def rollback(self, query_id: str, version_id: str) -> None:
        """回滚到指定版本"""
        # 将指定版本标记为当前版本
        pass
```

---

## 二、数据处理增强

### 2.1 智能数据导出

```python
# src/micro_genbi/service/data_exporter.py

class DataExporter:
    """
    数据导出服务

    支持多种格式的查询结果导出。
    """

    SUPPORTED_FORMATS = {
        "csv": "text/csv",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json": "application/json",
        "sql": "application/sql",
        "pdf": "application/pdf",
    }

    async def export(
        self,
        query_id: str,
        format: str,
        user_id: str,
    ) -> ExportResult:
        """导出查询结果"""

        # 1. 检查导出权限
        if not await self._check_export_permission(user_id, query_id):
            raise PermissionDenied("您没有导出此查询的权限")

        # 2. 检查导出限制
        await self._check_export_limits(user_id, format)

        # 3. 获取查询结果
        result = await self._get_query_result(query_id)

        # 4. 格式化数据
        exporter = self._get_exporter(format)
        output = exporter.format(result.data)

        # 5. 保存到临时存储或直接返回
        file_path = await self._save_export(
            user_id=user_id,
            format=format,
            content=output,
            original_query=result.query,
        )

        return ExportResult(
            file_path=file_path,
            format=format,
            row_count=result.row_count,
            expires_at=datetime.now() + timedelta(hours=24),
        )

    def _get_exporter(self, format: str) -> BaseExporter:
        """获取格式对应的导出器"""
        exporters = {
            "csv": CSVExporter(),
            "excel": ExcelExporter(),
            "json": JSONExporter(),
            "sql": SQLExporter(),
            "pdf": PDFExporter(),
        }
        return exporters.get(format, JSONExporter())
```

### 2.2 数据脱敏导出

```python
# src/micro_genbi/service/safe_exporter.py

class SafeExporter:
    """
    安全导出器

    在导出时自动应用数据脱敏规则。
    """

    def __init__(self, masker: DataMasker):
        self.masker = masker

    async def export_with_masking(
        self,
        data: list[dict],
        schema: SchemaMeta,
        user_role: str,
    ) -> list[dict]:
        """
        带脱敏的数据导出

        根据用户角色自动过滤敏感字段。
        """
        # 1. 确定用户可见字段
        visible_fields = self._get_visible_fields(schema, user_role)

        # 2. 过滤字段
        filtered = []
        for row in data:
            filtered_row = {k: v for k, v in row.items() if k in visible_fields}
            filtered.append(filtered_row)

        # 3. 对数值型敏感字段脱敏
        masked = self.masker.mask_result(filtered, schema)

        return masked
```

### 2.3 增量查询

```python
# src/micro_genbi/service/incremental_query.py

class IncrementalQueryService:
    """
    增量查询服务

    对于周期性报表，支持只查询增量数据。
    """

    async def setup_incremental_query(
        self,
        user_id: str,
        base_query: str,
        id_field: str,
        timestamp_field: str,
    ) -> IncrementalConfig:
        """设置增量查询"""

        # 1. 获取上次查询的截止时间
        last_run = await self._get_last_run(user_id, base_query)

        # 2. 构建增量 SQL
        if last_run:
            incremental_sql = f"""
                {base_query}
                WHERE {timestamp_field} > '{last_run.end_time}'
            """
        else:
            incremental_sql = base_query

        return IncrementalConfig(
            base_query=base_query,
            incremental_sql=incremental_sql,
            id_field=id_field,
            timestamp_field=timestamp_field,
            last_sync_time=last_run.end_time if last_run else None,
        )

    async def run_incremental(
        self,
        config: IncrementalConfig,
    ) -> IncrementalResult:
        """执行增量查询"""
        # 1. 执行增量 SQL
        result = await self.db.execute(config.incremental_sql)

        # 2. 更新同步状态
        await self._update_sync_status(
            config_id=config.id,
            end_time=datetime.now(),
            row_count=len(result.rows),
        )

        return IncrementalResult(
            new_rows=result.rows,
            sync_time=datetime.now(),
            total_new=len(result.rows),
        )
```

---

## 三、智能分析增强

### 3.1 自然语言结果解读

```python
# src/micro_genbi/service/result_interpreter.py

class ResultInterpreter:
    """
    查询结果解读器

    使用 LLM 对查询结果进行自然语言解读。
    """

    async def interpret(
        self,
        query: str,
        sql: str,
        result: QueryResult,
        context: dict,
    ) -> Interpretation:
        """
        解读查询结果

        1. 数据概览（总数、最大、最小、平均）
        2. 关键发现
        3. 异常检测
        4. 建议行动
        """

        prompt = RESULT_INTERPRET_PROMPT.format(
            user_query=query,
            sql=sql,
            result_data=self._summarize_data(result),
            context=self._format_context(context),
        )

        response = await self.llm.generate(prompt)

        return Interpretation(
            summary=response.summary,
            key_findings=response.findings,
            anomalies=response.anomalies,
            recommendations=response.recommendations,
        )

    def _summarize_data(self, result: QueryResult) -> str:
        """生成数据摘要"""
        if not result.rows:
            return "查询结果为空"

        # 计算基本统计
        numeric_cols = self._get_numeric_columns(result)
        stats = {}

        for col in numeric_cols:
            values = [row.get(col, 0) for row in result.rows]
            stats[col] = {
                "count": len(values),
                "sum": sum(values),
                "avg": sum(values) / len(values),
                "min": min(values),
                "max": max(values),
            }

        return self._format_stats(stats)
```

### 3.2 异常自动检测

```python
# src/micro_genbi/service/anomaly_detector.py

class AnomalyDetector:
    """
    异常检测服务

    对查询结果进行自动异常检测。
    """

    async def detect_anomalies(
        self,
        data: list[dict],
        metrics: list[str],
    ) -> list[Anomaly]:
        """检测异常数据点"""

        anomalies = []

        for metric in metrics:
            values = [row.get(metric) for row in data if row.get(metric) is not None]

            if not values:
                continue

            # 1. Z-Score 检测
            z_score_anomalies = self._zscore_detection(values)
            anomalies.extend(z_score_anomalies)

            # 2. IQR 检测
            iqr_anomalies = self._iqr_detection(values)
            anomalies.extend(iqr_anomalies)

            # 3. 趋势异常检测
            trend_anomalies = self._trend_detection(values)
            anomalies.extend(trend_anomalies)

        return anomalies

    def _zscore_detection(self, values: list[float], threshold: float = 3.0):
        """Z-Score 异常检测"""
        mean = statistics.mean(values)
        std = statistics.stdev(values)

        if std == 0:
            return []

        anomalies = []
        for i, v in enumerate(values):
            z_score = abs((v - mean) / std)
            if z_score > threshold:
                anomalies.append(Anomaly(
                    index=i,
                    value=v,
                    method="zscore",
                    score=z_score,
                    threshold=threshold,
                ))

        return anomalies

    def _iqr_detection(self, values: list[float], factor: float = 1.5):
        """IQR 四分位距异常检测"""
        sorted_values = sorted(values)
        q1 = statistics.quantiles(sorted_values, n=4)[0]
        q3 = statistics.quantiles(sorted_values, n=4)[2]
        iqr = q3 - q1

        lower_bound = q1 - factor * iqr
        upper_bound = q3 + factor * iqr

        anomalies = []
        for i, v in enumerate(values):
            if v < lower_bound or v > upper_bound:
                anomalies.append(Anomaly(
                    index=i,
                    value=v,
                    method="iqr",
                    score=abs(v - (q1 + q3) / 2) / iqr if iqr > 0 else 0,
                    bounds=(lower_bound, upper_bound),
                ))

        return anomalies
```

### 3.3 智能图表推荐

```python
# src/micro_genbi/chart/smart_recommender.py

class ChartRecommender:
    """
    智能图表推荐器

    根据查询结果自动推荐最佳可视化方式。
    """

    async def recommend(
        self,
        query: str,
        result: QueryResult,
        schema: SchemaMeta,
    ) -> list[ChartRecommendation]:
        """
        推荐可视化方案

        分析查询结果特征，推荐最适合的图表类型。
        """

        recommendations = []

        # 1. 分析数据结构
        analysis = self._analyze_result_structure(result)

        # 2. 基于数据特征推荐
        if analysis.has_time_series:
            recommendations.append(ChartRecommendation(
                chart_type="line",
                reason="检测到时间序列数据",
                confidence=0.95,
                echarts_options=self._build_line_options(analysis),
            ))

        if analysis.has_category and analysis.has_numeric:
            recommendations.append(ChartRecommendation(
                chart_type="bar",
                reason="检测到分类+数值数据",
                confidence=0.9,
                echarts_options=self._build_bar_options(analysis),
            ))

        if analysis.numeric_columns == 1 and analysis.category_column:
            if analysis.unique_values <= 10:
                recommendations.append(ChartRecommendation(
                    chart_type="pie",
                    reason="数据适合饼图展示（<=10 个分类）",
                    confidence=0.85,
                    echarts_options=self._build_pie_options(analysis),
                ))

        # 3. 基于查询意图推荐
        intent = await self.classifier.classify(query)
        if "趋势" in query or "变化" in query:
            recommendations.insert(0, ChartRecommendation(
                chart_type="line",
                reason="根据查询意图（趋势分析）推荐",
                confidence=0.9,
            ))

        return sorted(recommendations, key=lambda x: x.confidence, reverse=True)

    def _analyze_result_structure(self, result: QueryResult) -> DataAnalysis:
        """分析结果数据结构"""
        columns = list(result.columns)
        numeric_cols = [c for c in columns if self._is_numeric(result, c)]
        datetime_cols = [c for c in columns if self._is_datetime(result, c)]

        return DataAnalysis(
            columns=columns,
            numeric_columns=numeric_cols,
            datetime_columns=datetime_cols,
            row_count=len(result.rows),
            has_time_series=len(datetime_cols) > 0 and len(numeric_cols) > 0,
            has_category=len(numeric_cols) >= 1 and len(columns) - len(numeric_cols) >= 1,
            unique_values=self._count_unique_values(result, columns[0]),
        )
```

---

## 四、系统管理增强

### 4.1 仪表盘与报表

```python
# src/micro_genbi/service/dashboard.py

class DashboardService:
    """
    仪表盘服务

    支持用户创建和管理自定义数据看板。
    """

    async def create_dashboard(
        self,
        user_id: str,
        name: str,
        widgets: list[DashboardWidget],
    ) -> Dashboard:
        """创建仪表盘"""

        dashboard = Dashboard(
            id=self._generate_id(),
            user_id=user_id,
            name=name,
            widgets=widgets,
            layout=self._auto_layout(widgets),
            created_at=datetime.now(),
        )

        await self.db.insert("dashboards", dashboard.to_dict())
        return dashboard

    async def add_widget(
        self,
        dashboard_id: str,
        widget: DashboardWidget,
    ) -> None:
        """添加仪表盘组件"""
        # 组件类型：查询卡片、图表、数据表格、文本说明
        pass

    async def refresh_widget(
        self,
        widget_id: str,
    ) -> WidgetData:
        """刷新组件数据"""
        widget = await self._get_widget(widget_id)
        return await self._execute_widget_query(widget)


@dataclass
class DashboardWidget:
    """仪表盘组件"""
    type: str  # "chart", "table", "stat", "text"
    query: str  # 关联的 NLQ
    chart_type: str = None
    position: dict = field(default_factory=lambda: {"x": 0, "y": 0, "w": 4, "h": 3})
    refresh_interval: int = 300  # 秒
```

### 4.2 定时任务与订阅

```python
# src/micro_genbi/service/subscription.py

class SubscriptionService:
    """
    定时订阅服务

    支持周期性查询任务和结果订阅。
    """

    async def create_subscription(
        self,
        user_id: str,
        query: str,
        schedule: CronExpression,
        recipients: list[str],
        format: str = "email",
    ) -> Subscription:
        """创建定时订阅"""

        subscription = Subscription(
            id=self._generate_id(),
            user_id=user_id,
            query=query,
            schedule=schedule,
            recipients=recipients,
            format=format,
            is_active=True,
            last_run=None,
            next_run=schedule.get_next_run(),
        )

        await self.db.insert("subscriptions", subscription.to_dict())

        # 注册到调度器
        await self.scheduler.add_job(
            job_id=subscription.id,
            func=self._execute_subscription,
            trigger="cron",
            **schedule.to_cron_trigger(),
        )

        return subscription

    async def _execute_subscription(self, subscription_id: str) -> None:
        """执行订阅任务"""
        subscription = await self._get_subscription(subscription_id)

        # 1. 执行查询
        result = await self.ask_service.ask(subscription.query)

        # 2. 格式化结果
        formatted = self.exporter.export(result, subscription.format)

        # 3. 发送通知
        await self.notifier.send(
            recipients=subscription.recipients,
            subject=f"[定时报表] {subscription.query}",
            content=formatted,
        )

        # 4. 更新状态
        await self._update_subscription_status(subscription_id)
```

### 4.3 操作日志与追踪

```python
# src/micro_genbi/service/operation_trace.py

class OperationTraceService:
    """
    操作追踪服务

    详细记录用户的每一个操作步骤。
    """

    async def start_trace(
        self,
        user_id: str,
        query: str,
        session_id: str,
    ) -> str:
        """开始追踪"""
        trace_id = self._generate_id()

        await self.db.insert("operation_traces", {
            "id": trace_id,
            "user_id": user_id,
            " query": query,
            "session_id": session_id,
            "started_at": datetime.now().isoformat(),
            "steps": [],
        })

        return trace_id

    async def add_step(
        self,
        trace_id: str,
        step: OperationStep,
    ) -> None:
        """记录操作步骤"""
        step_record = {
            "step_type": step.type,
            "input": step.input,
            "output": step.output,
            "duration_ms": step.duration_ms,
            "timestamp": datetime.now().isoformat(),
        }

        await self.db.execute(
            """
            UPDATE operation_traces
            SET steps = JSON_INSERT(steps, '$[-1]', ?)
            WHERE id = ?
            """,
            (json.dumps(step_record), trace_id)
        )

    async def get_trace(self, trace_id: str) -> OperationTrace:
        """获取追踪记录"""
        record = await self.db.fetchone(
            "SELECT * FROM operation_traces WHERE id = ?",
            (trace_id,)
        )
        return OperationTrace.from_dict(record)


@dataclass
class OperationStep:
    """操作步骤"""
    type: str  # intent_classification, schema_retrieval, sql_generation, etc.
    input: dict
    output: dict
    duration_ms: float
```

---

## 五、运维管理增强

### 5.1 健康检查端点

```python
# src/micro_genbi/api/health.py

@router.get("/health")
async def health_check() -> HealthResponse:
    """
    综合健康检查

    返回系统各组件的健康状态。
    """

    checks = {}

    # 1. 数据库连接
    try:
        await db.execute("SELECT 1")
        checks["database"] = {"status": "healthy", "latency_ms": 0}
    except Exception as e:
        checks["database"] = {"status": "unhealthy", "error": str(e)}

    # 2. LLM 服务
    try:
        latency = await self._ping_llm()
        checks["llm"] = {"status": "healthy", "latency_ms": latency}
    except Exception as e:
        checks["llm"] = {"status": "degraded", "error": str(e)}

    # 3. 磁盘空间
    disk_usage = shutil.disk_usage(".")
    disk_percent = (disk_usage.used / disk_usage.total) * 100
    checks["disk"] = {
        "status": "healthy" if disk_percent < 80 else "warning",
        "used_percent": round(disk_percent, 1),
    }

    # 4. 内存使用
    memory = psutil.virtual_memory()
    checks["memory"] = {
        "status": "healthy" if memory.percent < 80 else "warning",
        "used_percent": memory.percent,
    }

    # 总体状态
    overall = "healthy"
    if any(c.get("status") == "unhealthy" for c in checks.values()):
        overall = "unhealthy"
    elif any(c.get("status") == "warning" for c in checks.values()):
        overall = "degraded"

    return HealthResponse(
        status=overall,
        checks=checks,
        timestamp=datetime.now().isoformat(),
    )
```

### 5.2 配置热更新

```python
# src/micro_genbi/config/hot_reload.py

class ConfigHotReloader:
    """
    配置热更新服务

    支持运行时更新配置，无需重启服务。
    """

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self._config = {}
        self._watcher = None

    async def start(self) -> None:
        """启动配置监听"""
        self._config = self._load_config()

        # 使用文件监听器
        self._watcher = Watcher(self.config_path)
        self._watcher.on_change(self._on_config_change)
        await self._watcher.start()

    async def _on_config_change(self, event: FileChangeEvent) -> None:
        """配置变更回调"""
        logger.info(f"配置文件变更: {event.path}")

        # 1. 重新加载配置
        new_config = self._load_config()

        # 2. 验证配置
        if not self._validate_config(new_config):
            logger.error("配置验证失败，使用旧配置")
            return

        # 3. 差异通知
        changes = self._diff_config(self._config, new_config)

        # 4. 应用变更
        self._config = new_config
        await self._notify_changes(changes)

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        return self._config.get(key, default)
```

---

## 六、推荐新增功能优先级

| 功能 | 模块路径 | 优先级 | 复杂度 | 说明 |
|------|---------|--------|--------|------|
| 查询建议与补全 | `src/micro_genbi/intent/query_suggester.py` | P1 | 中 | 提升用户体验 |
| 数据导出服务 | `src/micro_genbi/service/data_exporter.py` | P1 | 中 | 常规需求 |
| 结果解读 | `src/micro_genbi/service/result_interpreter.py` | P2 | 中 | 增强分析能力 |
| 查询历史与收藏 | `src/micro_genbi/service/query_history.py` | P1 | 低 | 提升复用性 |
| 智能图表推荐 | `src/micro_genbi/chart/smart_recommender.py` | P2 | 中 | 自动化可视化 |
| SQL 版本管理 | `src/micro_genbi/service/sql_versioning.py` | P2 | 低 | SQL 对比与回退 |
| 定时订阅 | `src/micro_genbi/service/subscription.py` | P2 | 高 | 自动化报表 |
| 异常检测 | `src/micro_genbi/service/anomaly_detector.py` | P2 | 高 | 主动发现问题 |
| 仪表盘 | `src/micro_genbi/service/dashboard.py` | P3 | 高 | 数据看板 |
| 实时预览 | `src/micro_genbi/api/preview.py` | P2 | 中 | 提升交互体验 |
| 配置热更新 | `src/micro_genbi/config/hot_reload.py` | P2 | 低 | 运维便利 |
| 操作追踪 | `src/micro_genbi/service/operation_trace.py` | P2 | 中 | 问题排查 |

---

*本建议文档涵盖当前规划中可能遗漏的功能增强点，可根据实际需求选择性实现。*
