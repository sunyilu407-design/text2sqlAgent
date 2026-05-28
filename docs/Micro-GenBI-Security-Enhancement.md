# Micro-GenBI 安全加固方案

> 适用于油库等高危行业的安全增强建议
> 版本：v1.0 | 日期：2026-05-25

---

## 一、安全风险矩阵

### 1.1 威胁分类

| 威胁类别 | 风险等级 | 说明 | 已有措施 | 需增强 |
|---------|---------|------|---------|--------|
| **SQL 注入** | 🔴 极高 | 通过 NLQ 注入恶意 SQL | SQLSafetyValidator | 深度增强 |
| **Prompt 注入** | 🔴 极高 | 通过自然语言注入恶意指令 | 无 | 需新增 |
| **数据泄露** | 🔴 极高 | 未授权访问敏感数据 | ACL 注入 | 需增强 |
| **越权访问** | 🟠 高 | 跨租户/跨角色访问 | 无 | 需新增 |
| **API 滥用** | 🟠 高 | 恶意请求、资源耗尽 | 无 | 需新增 |
| **审计缺失** | 🟠 高 | 操作不可追溯 | 无 | 需新增 |
| **LLM 幻觉** | 🟡 中 | 生成错误 SQL 导致误判 | 自愈重试 | 需增强 |
| **Token 泄露** | 🟡 中 | API Key/Token 泄露 | 无 | 需新增 |

---

## 二、SQL 安全增强

### 2.1 当前措施

- `SQLSafetyValidator`：AST 遍历检测写操作
- LIMIT 强制追加
- 表存在性白名单检查

### 2.2 需增强措施

#### 2.2.1 深度 SQL 注入防护

```python
# src/micro_genbi/pipeline/sql_sanitizer.py

class SQLSanitizer:
    """
    SQL 深度净化器

    在 SQLSafetyValidator 之后执行，对 SQL 进行额外的安全检查。
    """

    # 高危关键词黑名单（大小写不敏感）
    HIGH_RISK_KEYWORDS = frozenset({
        # 数据操作
        "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
        "ALTER", "CREATE", "GRANT", "REVOKE", "DENY",
        "EXEC", "EXECUTE", "CALL", "LOAD", "INTO OUTFILE",
        "INTO DUMPFILE", "LOAD_FILE", "BENCHMARK", "SLEEP",
        # 系统命令
        "SHUTDOWN", "KILL", "RESET", "RESTORE",
        # 注释注入
        "--", "/*", "*/", "#", ";" + "--",
        # 编码绕过
        "0x", "CHAR(", "CONCAT(", "UNHEX(",
        # 联合注入关键词
        "UNION", "SELECT", "FROM",
    })

    # 危险函数黑名单
    DANGEROUS_FUNCTIONS = frozenset({
        # 系统函数
        "SYSTEM", "USER", "CURRENT_USER", "SESSION_USER",
        "LOAD_FILE", "INTO DUMPFILE", "BENCHMARK", "SLEEP",
        "DATABASE", "SCHEMA", "VERSION", "@@VERSION",
        # 文件操作
        "FILE", "LOAD", "OUTFILE", "DUMPFILE",
        # 编码函数（可能被用于绕过）
        "HEX(", "UNHEX(", "CHAR(", "CONCAT(",
        # 复杂编码
        "ENCODE", "DECODE", "AES_DECRYPT", "AES_ENCRYPT",
    })

    def sanitize(self, sql: str) -> str:
        """净化 SQL"""
        # 1. 移除注释
        sql = self._remove_comments(sql)

        # 2. 规范化空白符
        sql = self._normalize_whitespace(sql)

        # 3. 检查高危关键词
        self._check_high_risk_keywords(sql)

        # 4. 检查危险函数
        self._check_dangerous_functions(sql)

        # 5. 检查注释注入
        self._check_comment_injection(sql)

        # 6. 检查编码注入
        self._check_encoding_injection(sql)

        # 7. 规范化字符串字面量
        sql = self._normalize_string_literals(sql)

        return sql

    def _remove_comments(self, sql: str) -> str:
        """移除 SQL 注释"""
        # 移除 -- 注释
        sql = re.sub(r'--[^\n]*', '', sql)
        # 移除 /* */ 注释
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        return sql.strip()

    def _normalize_whitespace(self, sql: str) -> str:
        """规范化空白符"""
        return re.sub(r'\s+', ' ', sql).strip()

    def _check_high_risk_keywords(self, sql: str) -> None:
        """检查高危关键词"""
        sql_upper = sql.upper()
        for keyword in self.HIGH_RISK_KEYWORDS:
            # 使用词边界匹配，避免误报
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper, re.IGNORECASE):
                raise SQLSecurityError(f"检测到高危关键词: {keyword}")

    def _check_dangerous_functions(self, sql: str) -> None:
        """检查危险函数"""
        sql_upper = sql.upper()
        for func in self.DANGEROUS_FUNCTIONS:
            pattern = r'\b' + func.replace('(', r'\s*\(') + r'\b'
            if re.search(pattern, sql_upper, re.IGNORECASE):
                raise SQLSecurityError(f"检测到危险函数: {func}")

    def _check_comment_injection(self, sql: str) -> None:
        """检查注释注入"""
        if '--' in sql or '/*' in sql or '*/' in sql:
            raise SQLSecurityError("检测到注释注入尝试")

    def _check_encoding_injection(self, sql: str) -> None:
        """检查编码注入"""
        if re.search(r'0x[0-9a-fA-F]+', sql):
            raise SQLSecurityError("检测到十六进制编码注入")
        if re.search(r'CHAR\s*\(', sql, re.IGNORECASE):
            raise SQLSecurityError("检测到 CHAR 编码注入")

    def _normalize_string_literals(self, sql: str) -> str:
        """规范化字符串字面量（用于后续检查）"""
        # 保留字符串内容，但标准化格式
        return sql
```

#### 2.2.2 SQL 参数化执行（强制）

```python
# 强制使用参数化查询，禁止字符串拼接
class SafeQueryBuilder:
    """安全的查询构建器"""

    def build_where_clause(self, conditions: dict) -> tuple[str, list]:
        """
        构建 WHERE 子句（参数化）

        Returns:
            (clause, params): SQL 子句和参数列表
        """
        clauses = []
        params = []

        for key, value in conditions.items():
            clauses.append(f'"{key}" = ?')  # 使用 ? 占位符
            params.append(value)

        return " AND ".join(clauses), params

    # 禁止：直接拼接用户输入
    # BAD: f"SELECT * FROM users WHERE name = '{name}'"
    # GOOD: build_where_clause({"name": name})
```

#### 2.2.3 敏感数据识别与脱敏

```python
# src/micro_genbi/security/data_masker.py

class DataMasker:
    """
    敏感数据脱敏器

    对查询结果中的敏感数据进行脱敏处理。
    """

    # 敏感字段模式
    SENSITIVE_PATTERNS = [
        # 证件号
        (r'\b\d{15,18}\b', '********'),  # 身份证
        (r'\b\d{4}-\d{4,8}\b', '****-****'),  # 银行卡
        # 手机号
        (r'\b1[3-9]\d{9}\b', lambda m: m.group()[:3] + '****' + m.group()[-4:]),
        # 邮箱
        (r'\b[\w.-]+@[\w.-]+\.\w+\b', lambda m: m.group()[0] + '***@***' + m.group().split('@')[-1]),
        # 密码相关
        (r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+', lambda m: m.group().split('=')[0] + '= ***'),
    ]

    # 油库专用敏感字段
    OIL_DEPOT_SENSITIVE_FIELDS = {
        "tank_level", "inventory_amount", "stock_quantity",
        "safety_pressure", "alarm_threshold", "password",
        "api_key", "secret_key", "token",
    }

    def mask_result(self, result: list[dict], schema: SchemaMeta) -> list[dict]:
        """对查询结果进行脱敏"""
        masked = []
        for row in result:
            masked_row = {}
            for key, value in row.items():
                if self._is_sensitive_field(key, schema):
                    masked_row[key] = self._mask_value(key, value)
                else:
                    masked_row[key] = value
            masked.append(masked_row)
        return masked

    def _is_sensitive_field(self, field: str, schema: SchemaMeta) -> bool:
        """判断是否为敏感字段"""
        field_lower = field.lower()

        # 1. 检查油库专用敏感字段
        if field_lower in self.OIL_DEPOT_SENSITIVE_FIELDS:
            return True

        # 2. 检查 schema 中标记的敏感字段
        if schema.is_field_sensitive(field):
            return True

        # 3. 检查字段名模式
        sensitive_keywords = ["password", "secret", "key", "token", "credential"]
        return any(kw in field_lower for kw in sensitive_keywords)

    def _mask_value(self, field: str, value: Any) -> str:
        """脱敏值"""
        if value is None:
            return None

        value_str = str(value)
        field_lower = field.lower()

        # 数值型敏感数据
        if any(kw in field_lower for kw in ["level", "amount", "quantity", "stock"]):
            return "[已脱敏]"

        # 密码类
        if any(kw in field_lower for kw in ["password", "passwd", "pwd"]):
            return "******"

        # 默认脱敏
        return "***"
```

---

## 三、访问控制增强

### 3.1 多租户数据隔离

```python
# src/micro_genbi/security/tenant_isolation.py

class TenantIsolationMiddleware:
    """
    多租户隔离中间件

    确保用户只能访问其所属租户的数据。
    """

    def __init__(self, db_session_factory):
        self.db = db_session_factory

    async def __call__(self, request, call_next):
        # 1. 提取租户标识
        tenant_id = self._extract_tenant_id(request)

        # 2. 验证租户访问权限
        if not await self._verify_tenant_access(request.user, tenant_id):
            raise TenantAccessDenied(tenant_id)

        # 3. 注入租户上下文
        request.state.tenant_id = tenant_id

        # 4. 在 SQL 执行时自动注入租户过滤
        response = await call_next(request)
        return response

    def _extract_tenant_id(self, request) -> str:
        """从请求中提取租户 ID"""
        # 优先级：Header > JWT Claim > Session
        return (
            request.headers.get("X-Tenant-ID") or
            request.state.user.tenant_id
        )

    def inject_tenant_filter(self, sql: str, tenant_id: str) -> str:
        """
        在 SQL 中注入租户过滤条件

        对于油库场景，通常有 tenant_id 或 org_id 字段
        """
        # 自动注入 WHERE tenant_id = ?
        # 需要在表结构中标记租户列
        return sql  # 具体实现依赖 schema 配置
```

### 3.2 基于角色的访问控制 (RBAC)

```python
# src/micro_genbi/security/rbac.py

class RBACPermission:
    """权限定义"""

    # 操作权限
    PERM_QUERY = "query:execute"           # 执行查询
    PERM_QUERY_VIEW_SQL = "query:view_sql" # 查看 SQL
    PERM_QUERY_EXPORT = "query:export"     # 导出数据
    PERM_SCHEMA_VIEW = "schema:view"       # 查看 Schema
    PERM_SCHEMA_EDIT = "schema:edit"       # 编辑 Schema
    PERM_ADMIN = "admin"                    # 管理员

    # 角色定义
    ROLE_PERMISSIONS = {
        "viewer": {PERM_QUERY, PERM_QUERY_VIEW_SQL, PERM_SCHEMA_VIEW},
        "analyst": {PERM_QUERY, PERM_QUERY_VIEW_SQL, PERM_QUERY_EXPORT, PERM_SCHEMA_VIEW},
        "operator": {PERM_QUERY, PERM_QUERY_VIEW_SQL, PERM_SCHEMA_VIEW, PERM_SCHEMA_EDIT},
        "admin": {PERM_ADMIN, PERM_QUERY, PERM_QUERY_VIEW_SQL, PERM_QUERY_EXPORT,
                  PERM_SCHEMA_VIEW, PERM_SCHEMA_EDIT},
    }

    # 字段级权限（油库场景）
    FIELD_PERMISSIONS = {
        # 操作员：不能看库存具体数值
        "operator": {
            "inventory_amount": {"mask": True},
            "tank_level": {"mask": True},
        },
        # 访客：不能看任何敏感数据
        "viewer": {
            "*": {"mask": True},
        },
    }


class PermissionChecker:
    """权限检查器"""

    def __init__(self, role: str, tenant_id: str):
        self.role = role
        self.tenant_id = tenant_id
        self.permissions = RBACPermission.ROLE_PERMISSIONS.get(role, set())

    def has_permission(self, permission: str) -> bool:
        """检查权限"""
        if RBACPermission.PERM_ADMIN in self.permissions:
            return True
        return permission in self.permissions

    def check_field_access(self, table: str, field: str) -> FieldAccess:
        """
        检查字段访问权限

        Returns:
            FieldAccess: FULL / MASKED / DENIED
        """
        field_perms = RBACPermission.FIELD_PERMISSIONS.get(self.role, {})

        # 通配符规则
        if "*" in field_perms:
            rule = field_perms["*"]
            if rule.get("mask"):
                return FieldAccess.MASKED

        # 特定字段规则
        if field in field_perms:
            rule = field_perms[field]
            if rule.get("deny"):
                return FieldAccess.DENIED
            if rule.get("mask"):
                return FieldAccess.MASKED

        return FieldAccess.FULL
```

### 3.3 API 认证增强

```python
# src/micro_genbi/security/auth.py

class APIKeyManager:
    """
    API Key 管理器

    支持：
    - Key 轮换
    - 访问频率限制
    - 范围限制（只读/读写）
    - IP 白名单
    """

    def __init__(self):
        self._keys: dict[str, APIKeyInfo] = {}

    async def validate_key(self, api_key: str, request: Request) -> AuthResult:
        """验证 API Key"""
        key_info = self._keys.get(api_key)
        if not key_info:
            return AuthResult(success=False, error="Invalid API Key")

        # 1. 检查 Key 状态
        if key_info.status != "active":
            return AuthResult(success=False, error="API Key 已停用")

        # 2. 检查过期时间
        if key_info.expires_at and datetime.now() > key_info.expires_at:
            return AuthResult(success=False, error="API Key 已过期")

        # 3. 检查 IP 白名单
        if key_info.allowed_ips:
            client_ip = self._get_client_ip(request)
            if client_ip not in key_info.allowed_ips:
                return AuthResult(success=False, error="IP 不在白名单")

        # 4. 检查权限范围
        if not self._check_key_scope(key_info, request):
            return AuthResult(success=False, error="API Key 权限不足")

        # 5. 记录访问
        await self._log_access(key_info, request)

        return AuthResult(success=True, user_id=key_info.user_id)

    def _check_key_scope(self, key_info: APIKeyInfo, request: Request) -> bool:
        """检查 Key 范围限制"""
        if key_info.scope == "readonly":
            # 只读 Key 只能执行 GET 请求
            return request.method in ["GET", "HEAD"]
        return True
```

---

## 四、Prompt 注入防护

### 4.1 问题说明

攻击者可能通过构造特殊的自然语言输入，试图：
1. 绕过 SQL 限制，获取管理员权限
2. 提取系统 Prompt 中的敏感信息
3. 诱导生成恶意 SQL

### 4.2 防护措施

```python
# src/micro_genbi/security/prompt_injection_detector.py

class PromptInjectionDetector:
    """
    Prompt 注入检测器

    检测用户输入中可能的 Prompt 注入尝试。
    """

    # 注入模式
    INJECTION_PATTERNS = [
        # 角色扮演绕过
        r"(?i)(ignore|disregard|bypass).*(previous|above|instruction|system)",
        r"(?i)(you are now|act as|pretend to be|imagine you are)",
        r"(?i)(forget (all |)previous (instructions|commands|rules)",
        # 提示泄露
        r"(?i)(what (are |is )?your (system |)prompt)",
        r"(?i)(reveal your (system |)instruction)",
        r"(?i)(what (were |was )?you told",
        # 越狱提示
        r"(?i)( DAN[ ,]?(do|anything|now))",
        r"(?i)(jailbreak)",
        r"(?i)(developer mode)",
        # SQL 注入试探
        r"(?i)(admin|';|UNION|SELECT|--).*(FROM|WHERE)",
        r"(?i)(execute|run).*(shell|command|system)",
    ]

    # 油库场景敏感词
    OIL_DEPOT_SENSITIVE_PATTERNS = [
        r"(?i)(shutdown|stop|emergency|evacuation)",
        r"(?i)(override|disable).*(safety|alarm|protocol)",
        r"(?i)(set.*pressure.*high|disable.*sensor)",
    ]

    def detect(self, user_input: str) -> InjectionCheckResult:
        """检测 Prompt 注入"""
        violations = []

        # 1. 模式匹配检测
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, user_input):
                violations.append({
                    "type": "injection_pattern",
                    "pattern": pattern,
                    "severity": "high",
                })

        # 2. 油库敏感词检测
        for pattern in self.OIL_DEPOT_SENSITIVE_PATTERNS:
            if re.search(pattern, user_input):
                violations.append({
                    "type": "oil_depot_sensitive",
                    "pattern": pattern,
                    "severity": "critical",
                    "action": "block",
                })

        # 3. 重复模式检测（自动注入特征）
        if self._detect_repetition(user_input):
            violations.append({
                "type": "repetition_pattern",
                "severity": "medium",
            })

        # 4. Base64/编码检测
        if self._contains_encoded_content(user_input):
            violations.append({
                "type": "encoded_content",
                "severity": "high",
            })

        return InjectionCheckResult(
            is_safe=len([v for v in violations if v.get("action") == "block"]) == 0,
            violations=violations,
            risk_score=self._calculate_risk_score(violations),
        )

    def _detect_repetition(self, text: str) -> bool:
        """检测重复模式（自动注入特征）"""
        words = text.split()
        if len(words) < 20:
            return False

        # 检查是否有大量重复词
        word_counts = Counter(words)
        max_ratio = max(word_counts.values()) / len(words)
        return max_ratio > 0.3

    def _contains_encoded_content(self, text: str) -> bool:
        """检测编码内容"""
        # Base64 检测
        if re.match(r'^[A-Za-z0-9+/]+=*$', text.strip()):
            if len(text.strip()) > 50:
                return True
        return False
```

---

## 五、速率限制与防护

### 5.1 多层限流

```python
# src/micro_genbi/security/rate_limiter.py

class MultiLayerRateLimiter:
    """
    多层速率限制器

    - 接入层：IP 限流
    - 网关层：API Key 限流
    - 应用层：用户限流
    - 资源层：SQL 执行限流
    """

    # 油库场景限制配置
    LIMITS = {
        # 查询限制（每分钟）
        "query_per_minute": 30,
        "query_per_hour": 500,
        "query_per_day": 2000,

        # Token 限制
        "total_tokens_per_day": 1_000_000,

        # 导出限制
        "export_per_day": 10,
        "export_rows_max": 10000,

        # SQL 执行超时
        "sql_timeout_seconds": 30,

        # 大结果集限制
        "result_rows_max": 5000,
    }

    async def check_rate_limit(self, identifier: str, action: str) -> RateLimitResult:
        """检查速率限制"""
        limits = self.LIMITS

        # 实现滑动窗口计数
        key = f"{identifier}:{action}"
        count = await self._get_count(key)

        if count >= limits.get(f"{action}_per_minute", 100):
            return RateLimitResult(
                allowed=False,
                retry_after=self._get_window_seconds(key),
                limit=limits.get(f"{action}_per_minute"),
            )

        await self._increment(key)
        return RateLimitResult(allowed=True)
```

### 5.2 SQL 执行限制

```python
# src/micro_genbi/security/sql_execution_guard.py

class SQLExecutionGuard:
    """
    SQL 执行守护

    对 SQL 执行进行额外的安全限制。
    """

    def __init__(self):
        self.max_execution_time = 30  # 最大执行时间（秒）
        self.max_result_rows = 5000  # 最大返回行数
        self.max_memory_mb = 512  # 最大内存使用（MB）

    async def execute_with_guard(
        self,
        sql: str,
        session,
        user_context: dict,
    ) -> ExecutionResult:
        """带守卫的 SQL 执行"""

        # 1. 解析 SQL 预估复杂度
        complexity = self._estimate_complexity(sql)
        if complexity > 10:  # JOIN 数过多
            raise SQLComplexityError("SQL 过于复杂")

        # 2. 设置执行超时
        start_time = time.time()

        try:
            result = await asyncio.wait_for(
                session.execute(sql),
                timeout=self.max_execution_time
            )

            # 3. 检查结果集大小
            if result.rowcount > self.max_result_rows:
                # 自动 LIMIT
                sql = self._append_limit(sql, self.max_result_rows)
                result = await session.execute(sql)

            # 4. 记录执行统计
            execution_time = time.time() - start_time
            await self._log_execution(sql, user_context, execution_time)

            return result

        except asyncio.TimeoutError:
            await self._log_timeout(sql, user_context)
            raise SQLTimeoutError("SQL 执行超时")
```

---

## 六、审计日志

### 6.1 审计事件定义

```python
# src/micro_genbi/security/audit.py

class AuditEventType:
    """审计事件类型"""

    # 认证事件
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FAILED = "auth.failed"
    AUTH_KEY_CREATED = "auth.key_created"
    AUTH_KEY_REVOKED = "auth.key_revoked"

    # 查询事件
    QUERY_SUBMITTED = "query.submitted"
    QUERY_EXECUTED = "query.executed"
    QUERY_BLOCKED = "query.blocked"
    QUERY_TIMEOUT = "query.timeout"
    QUERY_EXPORT = "query.export"

    # 安全事件
    SECURITY_INJECTION_BLOCKED = "security.injection_blocked"
    SECURITY_RATE_LIMITED = "security.rate_limited"
    SECURITY_PERMISSION_DENIED = "security.permission_denied"
    SECURITY_TENANT_VIOLATION = "security.tenant_violation"


@dataclass
class AuditLogEntry:
    """审计日志条目"""
    timestamp: datetime
    event_type: str
    user_id: str
    tenant_id: str
    ip_address: str
    user_agent: str
    request_path: str
    request_method: str
    resource: str  # 表名、Schema 名等
    action: str
    result: str  # success / failed / blocked
    error_message: Optional[str]
    metadata: dict  # 额外信息（SQL、Token 使用等）


class AuditLogger:
    """审计日志记录器"""

    def __init__(self, db_session):
        self.db = db_session

    async def log(self, event: AuditLogEntry) -> None:
        """记录审计日志"""
        # 1. 存储到数据库
        await self.db.execute(
            """
            INSERT INTO audit_logs (
                timestamp, event_type, user_id, tenant_id,
                ip_address, user_agent, request_path, request_method,
                resource, action, result, error_message, metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event.timestamp.isoformat(),
                event.event_type,
                event.user_id,
                event.tenant_id,
                event.ip_address,
                event.user_agent,
                event.request_path,
                event.request_method,
                event.resource,
                event.action,
                event.result,
                event.error_message,
                json.dumps(event.metadata),
            )
        )

        # 2. 实时告警（高危事件）
        if self._is_high_risk_event(event):
            await self._send_security_alert(event)

    def _is_high_risk_event(self, event: AuditLogEntry) -> bool:
        """判断是否为高危事件"""
        high_risk_events = {
            AuditEventType.AUTH_FAILED,  # 频繁登录失败
            AuditEventType.QUERY_BLOCKED,  # 查询被拦截
            AuditEventType.SECURITY_INJECTION_BLOCKED,  # 注入攻击
            AuditEventType.SECURITY_TENANT_VIOLATION,  # 越权访问
        }
        return event.event_type in high_risk_events

    async def _send_security_alert(self, event: AuditLogEntry) -> None:
        """发送安全告警"""
        # 支持多种告警渠道
        # - 企业微信/钉钉 webhook
        # - 邮件
        # - SMS
        # - SIEM 系统
        pass
```

---

## 七、网络安全配置

### 7.1 HTTPS 配置

```yaml
# nginx.conf 或反向代理配置

server {
    listen 443 ssl http2;
    server_name api.oildepot.example.com;

    # SSL 证书配置
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # SSL 安全配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 10m;

    # HSTS
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

    # 安全响应头
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Content-Security-Policy "default-src 'self'; script-src 'self'" always;
}
```

### 7.2 CORS 配置

```python
# FastAPI CORS 配置
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.oildepot.example.com"],  # 精确域名
    allow_credentials=True,
    allow_methods=["GET", "POST"],  # 只允许必要方法
    allow_headers=["Authorization", "Content-Type", "X-Tenant-ID"],
    max_age=600,  # 预检请求缓存
)
```

---

## 八、安全测试清单

### 8.1 功能测试

| 测试项 | 测试方法 | 预期结果 |
|-------|---------|---------|
| SQL 注入防护 | 输入 `'; DROP TABLE users; --` | 查询被拦截 |
| UNION 注入防护 | 输入 `UNION SELECT * FROM admin` | 查询被拦截 |
| 注释注入防护 | 输入 `1; -- comment` | 查询被拦截 |
| 参数化查询 | 检查生成的 SQL | 使用 ? 占位符 |
| LIMIT 强制 | 不含 LIMIT 的查询 | 自动追加 LIMIT |
| 表白名单 | 查询白名单外表 | 查询被拒绝 |
| 角色权限 | 访客查看敏感字段 | 数据被脱敏 |
| 租户隔离 | 用户 A 访问用户 B 数据 | 访问被拒绝 |

### 8.2 渗透测试

```bash
# SQL 注入测试
sqlmap -u "https://api.oildepot.com/api/v1/query" \
       --data='{"query":"测试"}' \
       --level=5 --risk=3

# CSRF 测试
# 使用 Burp Suite CSRF PoC Generator

# XSS 测试
# 提交 <script>alert(1)</script> 作为查询
```

### 8.3 性能压力测试

```bash
# 使用 wrk 进行压力测试
wrk -t12 -c400 -d30s https://api.oildepot.com/api/v1/query \
    --latency \
    -s post.lua
```

### 8.4 合规检查

- [ ] OWASP Top 10 检查
- [ ] GB/T 22239-2019 等保 2.0 相关条款
- [ ] 油库行业信息安全要求

---

## 九、安全文档清单

业主安全测试通常需要以下文档：

### 9.1 安全设计文档

```
security/
├── 安全架构设计.md
├── 威胁建模报告.md
├── 数据流图 (DFD)
├── 信任边界定义.md
└── 密钥管理方案.md
```

### 9.2 安全测试报告

```
security/
├── 渗透测试报告.md
├── 漏洞扫描报告.md
├── 代码安全审计报告.md
├── SQL 注入防护测试报告.md
├── 访问控制测试报告.md
└── 应急响应预案.md
```

### 9.3 合规证明

```
security/
├── 等保测评报告.md
├── 安全评估证书/
├── 数据加密证明.md
├── 日志审计配置.md
└── 隐私保护措施.md
```

---

## 十、推荐新增模块

| 模块名称 | 文件路径 | 优先级 | 说明 |
|---------|---------|--------|------|
| SQLSanitizer | `src/micro_genbi/security/sql_sanitizer.py` | P0 | 深度 SQL 注入防护 |
| PromptInjectionDetector | `src/micro_genbi/security/prompt_injection_detector.py` | P0 | Prompt 注入检测 |
| DataMasker | `src/micro_genbi/security/data_masker.py` | P0 | 敏感数据脱敏 |
| AuditLogger | `src/micro_genbi/security/audit.py` | P0 | 审计日志 |
| RBAC | `src/micro_genbi/security/rbac.py` | P1 | 权限控制 |
| RateLimiter | `src/micro_genbi/security/rate_limiter.py` | P1 | 速率限制 |
| TenantIsolation | `src/micro_genbi/security/tenant_isolation.py` | P1 | 多租户隔离 |
| APIKeyManager | `src/micro_genbi/security/auth.py` | P1 | API Key 管理 |

---

*本方案为 Micro-GenBI 的安全加固建议，具体实施需根据实际环境和合规要求进行调整。*
