# Micro-GenBI 完整 RESTful API 规范

> 版本：v2.2
> 日期：2026-05-25
> 基础路径：`/api/v1`

---

## 一、Swagger / OpenAPI 支持

### 1.1 Swagger UI 访问

部署后可通过以下地址访问交互式 API 文档：

```
生产环境：https://api.oildepot.example.com/docs
预发环境：https://staging-api.oildepot.example.com/docs
本地开发：http://localhost:8000/docs
```

### 1.2 OpenAPI JSON 端点

```
GET /openapi.json          # 完整 OpenAPI 3.0 规范（JSON 格式）
GET /redoc                 # ReDoc 风格的 API 文档
```

### 1.3 FastAPI Swagger 配置

```python
# src/micro_genbi/api/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html

app = FastAPI(
    title="Micro-GenBI Text-to-SQL API",
    description="""
## 简介

Micro-GenBI 是一个企业级 Text2SQL 智能分析平台，提供自然语言数据查询能力。

## 认证方式

### 方式一：JWT Token
```
Authorization: Bearer <access_token>
```

### 方式二：API Key
```
X-API-Key: <your-api-key>
X-User-Id: <user-id>
X-User-Role: <role>
```

## 注意事项

- 所有请求必须使用 HTTPS
- 请求 Content-Type: application/json
- 响应均为 JSON 格式
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.oildepot.example.com",
        "https://admin.oildepot.example.com",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# Swagger UI 自定义配置
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Micro-GenBI API 文档",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": 1,
            "defaultModelExpandDepth": 1,
            "docExpansion": "list",
            "filter": True,
            "showExtensions": True,
            "showCommonExtensions": True,
        },
    )
```

### 1.4 Swagger 安全配置

```python
# src/micro_genbi/api/security.py

from fastapi.security import HTTPBearer, APIKeyHeader
from fastapi import Security, Depends

# Bearer Token 认证
bearer_scheme = HTTPBearer(
    scheme_name="Bearer Token",
    description="JWT Access Token，从 /auth/login 获取",
    auto_error=True,
)

# API Key 认证
api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="API Key",
    description="API Key，从 /auth/api-keys 创建",
    auto_error=True,
)

# 认证依赖
async def get_auth(
    bearer: str = Security(bearer_scheme),
    api_key: str = Security(api_key_header),
):
    """支持 Bearer Token 或 API Key 认证"""
    if bearer:
        return {"auth": "bearer", "token": bearer}
    elif api_key:
        return {"auth": "apikey", "key": api_key}
    else:
        raise HTTPException(status_code=401, detail="未提供认证信息")
```

---

## 二、.NET 桌面端对接指南

### 2.1 环境要求

- .NET 6.0 或更高版本
- 推荐使用 WPF、WinForms、MAUI 或 Avalonia

### 2.2 安装依赖

```xml
<!-- WinForms / WPF / Console -->
<PackageReference Include="Microsoft.Extensions.Http" Version="8.0.0" />
<PackageReference Include="System.Text.Json" Version="8.0.0" />
<PackageReference Include="System.IdentityModel.Tokens.Jwt" Version="7.0.0" />

<!-- 或者使用 RestSharp -->
<PackageReference Include="RestSharp" Version="110.2.0" />

<!-- 如果需要 SSE 流式接收 -->
<PackageReference Include="System.Threading.Channels" Version="8.0.0" />
```

### 2.3 客户端基类实现

```csharp
// MicroGenBIClient.cs

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace MicroGenBI.Client
{
    /// <summary>
    /// Micro-GenBI API 客户端 (.NET)
    /// </summary>
    public class MicroGenBIClient : IDisposable
    {
        private readonly HttpClient _httpClient;
        private readonly string _baseUrl;
        private string? _accessToken;
        private string? _apiKey;
        private DateTime _tokenExpiry = DateTime.MinValue;

        public MicroGenBIClient(string baseUrl)
        {
            _baseUrl = baseUrl.TrimEnd('/');
            _httpClient = new HttpClient
            {
                BaseAddress = new Uri(_baseUrl),
                Timeout = TimeSpan.FromMinutes(5)
            };
        }

        /// <summary>
        /// 使用 API Key 初始化
        /// </summary>
        public void SetApiKey(string apiKey, string? userId = null, string? role = null)
        {
            _apiKey = apiKey;
            _httpClient.DefaultRequestHeaders.Clear();
            _httpClient.DefaultRequestHeaders.Add("X-API-Key", apiKey);

            if (!string.IsNullOrEmpty(userId))
                _httpClient.DefaultRequestHeaders.Add("X-User-Id", userId);

            if (!string.IsNullOrEmpty(role))
                _httpClient.DefaultRequestHeaders.Add("X-User-Role", role);
        }

        /// <summary>
        /// 登录获取 Token
        /// </summary>
        public async Task<LoginResponse> LoginAsync(string username, string password)
        {
            var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/login")
            {
                Content = JsonContent.Create(new { username, password })
            };

            var response = await _httpClient.SendAsync(request);
            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadFromJsonAsync<LoginResponse>();

            if (result != null)
            {
                _accessToken = result.AccessToken;
                _tokenExpiry = DateTime.UtcNow.AddSeconds(result.ExpiresIn - 60);
                _httpClient.DefaultRequestHeaders.Authorization =
                    new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _accessToken);
            }

            return result!;
        }

        /// <summary>
        /// 同步执行查询
        /// </summary>
        public async Task<QueryResponse> QueryAsync(string query, string? sessionId = null)
        {
            var request = new
            {
                query,
                session_id = sessionId,
                generate_chart = true
            };

            return await PostAsync<QueryResponse>("/api/v1/query", request);
        }

        /// <summary>
        /// 异步执行查询
        /// </summary>
        public async Task<TaskInfo> QueryAsyncStart(string query)
        {
            var request = new { query };
            return await PostAsync<TaskInfo>("/api/v1/query/async", request);
        }

        /// <summary>
        /// 获取异步任务状态
        /// </summary>
        public async Task<TaskStatus> QueryStatusAsync(string taskId)
        {
            return await GetAsync<TaskStatus>($"/api/v1/query/async/{taskId}");
        }

        /// <summary>
        /// SSE 流式接收任务进度
        /// </summary>
        public async Task StreamTaskProgressAsync(
            string taskId,
            Action<TaskProgressEvent> onProgress,
            CancellationToken cancellationToken = default)
        {
            using var request = new HttpRequestMessage(
                HttpMethod.Get,
                $"/api/v1/query/async/{taskId}/stream");

            using var response = await _httpClient.SendAsync(
                request,
                HttpResponseMessageExtensions.EnsureSuccessStatusCode,
                cancellationToken);

            using var stream = await response.Content.ReadAsStreamAsync(cancellationToken);
            using var reader = new StreamReader(stream);

            while (!reader.EndOfStream && !cancellationToken.IsCancellationRequested)
            {
                var line = await reader.ReadLineAsync(cancellationToken);

                if (line?.StartsWith("event:") == true)
                {
                    var eventType = line.Substring(6).Trim();
                    var dataLine = await reader.ReadLineAsync(cancellationToken);

                    if (dataLine?.StartsWith("data:") == true)
                    {
                        var json = dataLine.Substring(5).Trim();
                        var progress = JsonSerializer.Deserialize<TaskProgressEvent>(json);
                        onProgress(progress!);
                    }
                }
            }
        }

        /// <summary>
        /// 获取 Schema
        /// </summary>
        public async Task<SchemaResponse> GetSchemaAsync(bool includeRelationships = false)
        {
            return await GetAsync<SchemaResponse>(
                $"/api/v1/schema?include_relationships={includeRelationships}");
        }

        /// <summary>
        /// 导出数据
        /// </summary>
        public async Task<ExportResponse> ExportAsync(
            string queryId,
            string format = "csv",
            bool maskSensitive = true)
        {
            var request = new
            {
                query_id = queryId,
                format,
                mask_sensitive = maskSensitive
            };

            return await PostAsync<ExportResponse>("/api/v1/export", request);
        }

        /// <summary>
        /// 获取健康状态
        /// </summary>
        public async Task<HealthResponse> GetHealthAsync()
        {
            return await GetAsync<HealthResponse>("/api/v1/health");
        }

        #region 内部方法

        private async Task<T> GetAsync<T>(string url)
        {
            await EnsureTokenValidAsync();
            var response = await _httpClient.GetAsync(url);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<T>()!;
        }

        private async Task<T> PostAsync<T>(string url, object body)
        {
            await EnsureTokenValidAsync();
            var response = await _httpClient.PostAsJsonAsync(url, body);
            response.EnsureSuccessStatusCode();
            return await response.Content.ReadFromJsonAsync<T>()!;
        }

        private async Task EnsureTokenValidAsync()
        {
            if (!string.IsNullOrEmpty(_accessToken) && DateTime.UtcNow >= _tokenExpiry)
            {
                await RefreshTokenAsync();
            }
        }

        private async Task RefreshTokenAsync()
        {
            if (string.IsNullOrEmpty(_accessToken))
                throw new InvalidOperationException("未登录或 Token 已过期");

            var request = new HttpRequestMessage(HttpMethod.Post, "/api/v1/auth/refresh");
            request.Headers.Authorization =
                new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _accessToken);

            var response = await _httpClient.SendAsync(request);
            response.EnsureSuccessStatusCode();

            var result = await response.Content.ReadFromJsonAsync<TokenRefreshResponse>();
            _accessToken = result!.AccessToken;
            _tokenExpiry = DateTime.UtcNow.AddSeconds(result.ExpiresIn - 60);

            _httpClient.DefaultRequestHeaders.Authorization =
                new System.Net.Http.Headers.AuthenticationHeaderValue("Bearer", _accessToken);
        }

        public void Dispose()
        {
            _httpClient.Dispose();
        }

        #endregion
    }

    #region 响应模型

    public class LoginResponse
    {
        public string AccessToken { get; set; } = "";
        public string RefreshToken { get; set; } = "";
        public int ExpiresIn { get; set; }
        public UserInfo User { get; set; } = new();
    }

    public class UserInfo
    {
        public string Id { get; set; } = "";
        public string Username { get; set; } = "";
        public string Role { get; set; } = "";
        public string TenantId { get; set; } = "";
    }

    public class QueryResponse
    {
        public string Sql { get; set; } = "";
        public List<Dictionary<string, object?>> Data { get; set; } = new();
        public List<ColumnInfo> Columns { get; set; } = new();
        public int RowCount { get; set; }
        public ChartInfo? Chart { get; set; }
        public string? Summary { get; set; }
    }

    public class ColumnInfo
    {
        public string Name { get; set; } = "";
        public string Type { get; set; } = "";
    }

    public class ChartInfo
    {
        public string Type { get; set; } = "";
        public Dictionary<string, object> Options { get; set; } = new();
    }

    public class TaskInfo
    {
        public string TaskId { get; set; } = "";
        public string Status { get; set; } = "";
    }

    public class TaskStatus
    {
        public string TaskId { get; set; } = "";
        public string Status { get; set; } = "";
        public int Progress { get; set; }
        public QueryResponse? Result { get; set; }
        public ErrorInfo? Error { get; set; }
    }

    public class TaskProgressEvent
    {
        public string? Event { get; set; }
        public string? Step { get; set; }
        public int? Progress { get; set; }
        public string? Message { get; set; }
    }

    public class ErrorInfo
    {
        public string Code { get; set; } = "";
        public string Message { get; set; } = "";
        public string? Phase { get; set; }
    }

    public class SchemaResponse
    {
        public List<DatabaseInfo> Databases { get; set; } = new();
    }

    public class DatabaseInfo
    {
        public string Id { get; set; } = "";
        public string Name { get; set; } = "";
        public string DisplayName { get; set; } = "";
        public List<TableInfo> Tables { get; set; } = new();
    }

    public class TableInfo
    {
        public string Name { get; set; } = "";
        public string DisplayName { get; set; } = "";
        public string? Description { get; set; }
        public List<ColumnDetail> Columns { get; set; } = new();
    }

    public class ColumnDetail
    {
        public string Name { get; set; } = "";
        public string DisplayName { get; set; } = "";
        public string Type { get; set; } = "";
        public string? Description { get; set; }
    }

    public class ExportResponse
    {
        public string ExportId { get; set; } = "";
        public string Status { get; set; } = "";
        public string? DownloadUrl { get; set; }
    }

    public class HealthResponse
    {
        public string Status { get; set; } = "";
        public Dictionary<string, CheckInfo> Checks { get; set; } = new();
    }

    public class CheckInfo
    {
        public string Status { get; set; } = "";
        public int? LatencyMs { get; set; }
    }

    public class TokenRefreshResponse
    {
        public string AccessToken { get; set; } = "";
        public int ExpiresIn { get; set; }
    }

    #endregion
}
```

### 2.4 WinForms 对接示例

```csharp
// MainForm.cs

using System;
using System.Threading.Tasks;
using System.Windows.Forms;
using MicroGenBI.Client;

namespace OilDepotDesktop
{
    public partial class MainForm : Form
    {
        private readonly MicroGenBIClient _client;
        private string? _currentSessionId;

        public MainForm()
        {
            InitializeComponent();

            // 初始化客户端
            _client = new MicroGenBIClient("https://api.oildepot.example.com");
            _client.SetApiKey("your-api-key-here");
        }

        private async void BtnQuery_Click(object sender, EventArgs e)
        {
            var query = txtQuery.Text.Trim();
            if (string.IsNullOrEmpty(query))
            {
                MessageBox.Show("请输入查询内容", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            try
            {
                BtnQuery.Enabled = false;
                lblStatus.Text = "正在查询...";

                // 执行查询
                var result = await _client.QueryAsync(query, _currentSessionId);

                // 显示结果
                dgvResult.DataSource = result.Data;
                _currentSessionId = result.SessionId;

                lblStatus.Text = $"查询成功，返回 {result.RowCount} 条数据";
            }
            catch (Exception ex)
            {
                MessageBox.Show($"查询失败: {ex.Message}", "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
            finally
            {
                BtnQuery.Enabled = true;
            }
        }

        private async void BtnQueryAsync_Click(object sender, EventArgs e)
        {
            try
            {
                // 启动异步查询
                var taskInfo = await _client.QueryAsyncStart(txtQuery.Text);
                lblStatus.Text = "查询中...";
                progressBar.Value = 0;

                // 监听进度
                await _client.StreamTaskProgressAsync(taskInfo.TaskId, progress =>
                {
                    this.Invoke(() =>
                    {
                        if (progress.Progress.HasValue)
                            progressBar.Value = progress.Progress.Value;

                        if (!string.IsNullOrEmpty(progress.Message))
                            lblStatus.Text = progress.Message;
                    });
                });

                // 获取结果
                var status = await _client.QueryStatusAsync(taskInfo.TaskId);
                if (status.Result != null)
                {
                    dgvResult.DataSource = status.Result.Data;
                    lblStatus.Text = $"完成，返回 {status.Result.RowCount} 条";
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"查询失败: {ex.Message}", "错误");
            }
        }

        private async void BtnExport_Click(object sender, EventArgs e)
        {
            // 获取最近的查询 ID
            var schema = await _client.GetSchemaAsync();

            // 导出示例
            var export = await _client.ExportAsync("query_001", "csv");
            MessageBox.Show($"导出任务已创建: {export.ExportId}", "导出");
        }
    }
}
```

### 2.5 WPF 对接示例

```csharp
// MainViewModel.cs

using System;
using System.Collections.ObjectModel;
using System.Threading.Tasks;
using System.Windows.Input;
using MicroGenBI.Client;
using CommunityToolkit.Mvvm.ComponentModel;
using CommunityToolkit.Mvvm.Input;

namespace OilDepotDesktop.ViewModels
{
    public partial class MainViewModel : ObservableObject
    {
        private readonly MicroGenBIClient _client;

        [ObservableProperty]
        private string _queryText = "";

        [ObservableProperty]
        private string _statusMessage = "就绪";

        [ObservableProperty]
        private bool _isLoading;

        [ObservableProperty]
        private int _progress;

        public ObservableCollection<Dictionary<string, object?>> QueryResults { get; } = new();

        public MainViewModel()
        {
            _client = new MicroGenBIClient("https://api.oildepot.example.com");
            _client.SetApiKey("your-api-key-here");
        }

        [RelayCommand]
        private async Task ExecuteQueryAsync()
        {
            if (string.IsNullOrWhiteSpace(QueryText))
                return;

            try
            {
                IsLoading = true;
                StatusMessage = "正在查询...";
                Progress = 0;

                var result = await _client.QueryAsync(QueryText);

                QueryResults.Clear();
                foreach (var row in result.Data)
                {
                    QueryResults.Add(row);
                }

                StatusMessage = $"查询成功，返回 {result.RowCount} 条数据";
            }
            catch (Exception ex)
            {
                StatusMessage = $"查询失败: {ex.Message}";
            }
            finally
            {
                IsLoading = false;
            }
        }

        [RelayCommand]
        private async Task ExportDataAsync()
        {
            try
            {
                var export = await _client.ExportAsync("query_001", "excel");
                StatusMessage = $"导出任务已创建: {export.ExportId}";

                // 轮询导出状态
                while (export.Status == "processing")
                {
                    await Task.Delay(1000);
                    // 获取最新状态
                }
            }
            catch (Exception ex)
            {
                StatusMessage = $"导出失败: {ex.Message}";
            }
        }
    }
}
```

---

## 三、Java Web 项目对接指南

### 3.1 环境要求

- Java 17 或更高版本
- Spring Boot 3.x（推荐）或 Jakarta EE

### 3.2 Maven 依赖

```xml
<!-- Spring Boot Web -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<!-- Spring Boot Security -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>

<!-- HTTP Client (Java 11+) -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>

<!-- JSON -->
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>

<!-- Lombok (可选) -->
<dependency>
    <groupId>org.projectlombok</groupId>
    <artifactId>lombok</artifactId>
    <optional>true</optional>
</dependency>
```

### 3.3 客户端配置

```java
// MicroGenBIProperties.java
package com.example.oildepot.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@ConfigurationProperties(prefix = "microgenbi")
public class MicroGenBIProperties {

    private String baseUrl = "https://api.oildepot.example.com";
    private String apiKey;
    private String userId;
    private String role = "user";
    private Duration connectTimeout = Duration.ofSeconds(30);
    private Duration readTimeout = Duration.ofMinutes(5);

    // Getters and Setters
    public String getBaseUrl() { return baseUrl; }
    public void setBaseUrl(String baseUrl) { this.baseUrl = baseUrl; }

    public String getApiKey() { return apiKey; }
    public void setApiKey(String apiKey) { this.apiKey = apiKey; }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }

    public String getRole() { return role; }
    public void setRole(String role) { this.role = role; }
}
```

### 3.4 客户端实现

```java
// MicroGenBIClient.java
package com.example.oildepot.client;

import com.example.oildepot.config.MicroGenBIProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.*;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.client.WebClientResponseException;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.time.Duration;
import java.time.Instant;
import java.util.*;

@Slf4j
@Component
@RequiredArgsConstructor
public class MicroGenBIClient {

    private final MicroGenBIProperties properties;
    private final ObjectMapper objectMapper;
    private WebClient webClient;

    private String accessToken;
    private Instant tokenExpiry = Instant.MIN;

    private WebClient getClient() {
        if (webClient == null) {
            webClient = WebClient.builder()
                    .baseUrl(properties.getBaseUrl())
                    .defaultHeader("Content-Type", "application/json")
                    .defaultHeader("X-API-Key", properties.getApiKey())
                    .defaultHeader("X-User-Id", properties.getUserId())
                    .defaultHeader("X-User-Role", properties.getRole())
                    .build();
        }
        return webClient;
    }

    /**
     * 登录获取 Token
     */
    public Mono<LoginResponse> login(String username, String password) {
        Map<String, String> body = Map.of(
                "username", username,
                "password", password
        );

        return getClient()
                .post()
                .uri("/api/v1/auth/login")
                .bodyValue(body)
                .retrieve()
                .bodyToMono(LoginResponse.class)
                .doOnNext(response -> {
                    this.accessToken = response.getAccessToken();
                    this.tokenExpiry = Instant.now()
                            .plusSeconds(response.getExpiresIn() - 60);
                });
    }

    /**
     * 同步执行查询
     */
    public Mono<QueryResponse> query(String query, String sessionId) {
        Map<String, Object> body = new HashMap<>();
        body.put("query", query);
        if (sessionId != null) {
            body.put("session_id", sessionId);
        }
        body.put("generate_chart", true);

        return ensureValidToken()
                .flatMap(token -> getClient()
                        .post()
                        .uri("/api/v1/query")
                        .header("Authorization", "Bearer " + token)
                        .bodyValue(body)
                        .retrieve()
                        .bodyToMono(QueryResponse.class));
    }

    /**
     * 异步执行查询 - 启动
     */
    public Mono<TaskInfo> queryAsyncStart(String query) {
        Map<String, String> body = Map.of("query", query);

        return ensureValidToken()
                .flatMap(token -> getClient()
                        .post()
                        .uri("/api/v1/query/async")
                        .header("Authorization", "Bearer " + token)
                        .bodyValue(body)
                        .retrieve()
                        .bodyToMono(TaskInfo.class));
    }

    /**
     * 获取异步任务状态
     */
    public Mono<TaskStatus> queryStatus(String taskId) {
        return ensureValidToken()
                .flatMap(token -> getClient()
                        .get()
                        .uri("/api/v1/query/async/{taskId}", taskId)
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .bodyToMono(TaskStatus.class));
    }

    /**
     * SSE 流式接收任务进度
     */
    public Flux<TaskProgressEvent> streamTaskProgress(String taskId) {
        return ensureValidToken()
                .flatMapMany(token -> getClient()
                        .get()
                        .uri("/api/v1/query/async/{taskId}/stream", taskId)
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .bodyToFlux(String.class)
                        .filter(line -> line.startsWith("data:"))
                        .map(line -> line.substring(5).trim())
                        .map(json -> {
                            try {
                                return objectMapper.readValue(json, TaskProgressEvent.class);
                            } catch (JsonProcessingException e) {
                                log.warn("解析 SSE 数据失败: {}", json);
                                return null;
                            }
                        })
                        .filter(Objects::nonNull));
    }

    /**
     * 获取 Schema
     */
    public Mono<SchemaResponse> getSchema(boolean includeRelationships) {
        return ensureValidToken()
                .flatMap(token -> getClient()
                        .get()
                        .uri(uriBuilder -> uriBuilder
                                .path("/api/v1/schema")
                                .queryParam("include_relationships", includeRelationships)
                                .build())
                        .header("Authorization", "Bearer " + token)
                        .retrieve()
                        .bodyToMono(SchemaResponse.class));
    }

    /**
     * 导出数据
     */
    public Mono<ExportResponse> export(String queryId, String format) {
        Map<String, Object> body = Map.of(
                "query_id", queryId,
                "format", format,
                "mask_sensitive", true
        );

        return ensureValidToken()
                .flatMap(token -> getClient()
                        .post()
                        .uri("/api/v1/export")
                        .header("Authorization", "Bearer " + token)
                        .bodyValue(body)
                        .retrieve()
                        .bodyToMono(ExportResponse.class));
    }

    /**
     * 获取健康状态
     */
    public Mono<HealthResponse> getHealth() {
        return getClient()
                .get()
                .uri("/api/v1/health")
                .retrieve()
                .bodyToMono(HealthResponse.class);
    }

    /**
     * 刷新 Token
     */
    public Mono<String> refreshToken() {
        return getClient()
                .post()
                .uri("/api/v1/auth/refresh")
                .header("Authorization", "Bearer " + accessToken)
                .retrieve()
                .bodyToMono(TokenRefreshResponse.class)
                .doOnNext(response -> {
                    this.accessToken = response.getAccessToken();
                    this.tokenExpiry = Instant.now()
                            .plusSeconds(response.getExpiresIn() - 60);
                })
                .map(TokenRefreshResponse::getAccessToken);
    }

    private Mono<String> ensureValidToken() {
        if (accessToken != null && Instant.now().isBefore(tokenExpiry)) {
            return Mono.just(accessToken);
        }
        return refreshToken();
    }

    // ========== 响应模型 ==========

    @lombok.Data
    public static class LoginResponse {
        private String accessToken;
        private String refreshToken;
        private int expiresIn;
        private UserInfo user;
    }

    @lombok.Data
    public static class UserInfo {
        private String id;
        private String username;
        private String role;
        private String tenantId;
    }

    @lombok.Data
    public static class QueryResponse {
        private String sql;
        private List<Map<String, Object>> data;
        private List<ColumnInfo> columns;
        private int rowCount;
        private ChartInfo chart;
        private String summary;
        private String sessionId;
    }

    @lombok.Data
    public static class ColumnInfo {
        private String name;
        private String type;
    }

    @lombok.Data
    public static class ChartInfo {
        private String type;
        private Map<String, Object> options;
    }

    @lombok.Data
    public static class TaskInfo {
        private String taskId;
        private String status;
    }

    @lombok.Data
    public static class TaskStatus {
        private String taskId;
        private String status;
        private int progress;
        private QueryResponse result;
        private ErrorInfo error;
    }

    @lombok.Data
    public static class TaskProgressEvent {
        private String event;
        private String step;
        private Integer progress;
        private String message;
    }

    @lombok.Data
    public static class ErrorInfo {
        private String code;
        private String message;
        private String phase;
    }

    @lombok.Data
    public static class SchemaResponse {
        private List<DatabaseInfo> databases;
    }

    @lombok.Data
    public static class DatabaseInfo {
        private String id;
        private String name;
        private String displayName;
        private List<TableInfo> tables;
    }

    @lombok.Data
    public static class TableInfo {
        private String name;
        private String displayName;
        private String description;
        private List<ColumnDetail> columns;
    }

    @lombok.Data
    public static class ColumnDetail {
        private String name;
        private String displayName;
        private String type;
        private String description;
    }

    @lombok.Data
    public static class ExportResponse {
        private String exportId;
        private String status;
        private String downloadUrl;
    }

    @lombok.Data
    public static class HealthResponse {
        private String status;
        private Map<String, CheckInfo> checks;
    }

    @lombok.Data
    public static class CheckInfo {
        private String status;
        private Integer latencyMs;
    }

    @lombok.Data
    public static class TokenRefreshResponse {
        private String accessToken;
        private int expiresIn;
    }
}
```

### 3.5 Spring Boot 集成示例

```java
// MicroGenBIService.java
package com.example.oildepot.service;

import com.example.oildepot.client.MicroGenBIClient;
import com.example.oildepot.client.MicroGenBIClient.*;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

import java.util.List;
import java.util.Map;

@Slf4j
@Service
@RequiredArgsConstructor
public class MicroGenBIService {

    private final MicroGenBIClient client;

    /**
     * 同步查询
     */
    public Mono<QueryResponse> executeQuery(String query) {
        return client.query(query, null)
                .doOnNext(response -> {
                    log.info("查询成功: SQL={}, 行数={}",
                            response.getSql(), response.getRowCount());
                })
                .onErrorResume(e -> {
                    log.error("查询失败: {}", e.getMessage());
                    return Mono.error(new RuntimeException("查询执行失败", e));
                });
    }

    /**
     * 带会话的查询
     */
    public Mono<QueryResponse> executeQueryWithSession(String query, String sessionId) {
        return client.query(query, sessionId);
    }

    /**
     * 异步查询并监听进度
     */
    public Flux<TaskProgressEvent> executeQueryWithProgress(String query,
            java.util.function.Consumer<TaskProgressEvent> onProgress) {
        return client.queryAsyncStart(query)
                .flatMapMany(taskInfo -> {
                    log.info("异步任务已启动: {}", taskInfo.getTaskId());

                    // 监听进度
                    Flux<TaskProgressEvent> progressFlux = client.streamTaskProgress(taskInfo.getTaskId())
                            .doOnNext(onProgress);

                    // 等待完成
                    Mono<TaskStatus> statusMono = waitForCompletion(taskInfo.getTaskId());

                    return Flux.merge(progressFlux, statusMono.toFlux());
                });
    }

    private Mono<TaskStatus> waitForCompletion(String taskId) {
        return client.queryStatus(taskId)
                .filter(status -> !"pending".equals(status.getStatus())
                        && !"running".equals(status.getStatus()))
                .switchIfEmpty(
                        Mono.delay(java.time.Duration.ofSeconds(1))
                                .flatMapMany(t -> waitForCompletion(taskId))
                )
                .next();
    }

    /**
     * 获取数据库 Schema
     */
    public Mono<SchemaResponse> getDatabaseSchema() {
        return client.getSchema(true);
    }

    /**
     * 导出数据
     */
    public Mono<ExportResponse> exportData(String queryId, String format) {
        return client.export(queryId, format);
    }

    /**
     * 健康检查
     */
    public Mono<Boolean> healthCheck() {
        return client.getHealth()
                .map(health -> "healthy".equals(health.getStatus()));
    }
}
```

### 3.6 Vue.js 前端对接示例

```typescript
// microgenbi.ts

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'https://api.oildepot.example.com';

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  user: UserInfo;
}

interface QueryResponse {
  sql: string;
  data: Record<string, any>[];
  columns: ColumnInfo[];
  row_count: number;
  chart?: ChartInfo;
  summary?: string;
  session_id?: string;
}

class MicroGenBIClient {
  private accessToken: string | null = null;

  // ========== 认证 ==========

  async login(username: string, password: string): Promise<LoginResponse> {
    const response = await fetch(`${API_BASE}/api/v1/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });

    if (!response.ok) {
      throw new Error('登录失败');
    }

    const result: LoginResponse = await response.json();
    this.accessToken = result.access_token;
    return result;
  }

  // ========== 查询 ==========

  async query(query: string, sessionId?: string): Promise<QueryResponse> {
    const response = await fetch(`${API_BASE}/api/v1/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.accessToken}`,
      },
      body: JSON.stringify({ query, session_id: sessionId }),
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || '查询失败');
    }

    return response.json();
  }

  async queryAsync(query: string): Promise<string> {
    const response = await fetch(`${API_BASE}/api/v1/query/async`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.accessToken}`,
      },
      body: JSON.stringify({ query }),
    });

    const result = await response.json();
    return result.task_id;
  }

  async getTaskStatus(taskId: string): Promise<TaskStatus> {
    const response = await fetch(
      `${API_BASE}/api/v1/query/async/${taskId}`,
      { headers: { 'Authorization': `Bearer ${this.accessToken}` } }
    );
    return response.json();
  }

  // SSE 流式监听
  streamTaskProgress(
    taskId: string,
    onProgress: (event: TaskProgressEvent) => void
  ): EventSource {
    const eventSource = new EventSource(
      `${API_BASE}/api/v1/query/async/${taskId}/stream`,
      {
        // SSE 不支持自定义 Header，需要通过 Cookie 或 Query 传递 Token
        // 或者使用 WebSocket 替代
      }
    );

    eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      onProgress(data);
    };

    return eventSource;
  }

  // ========== Schema ==========

  async getSchema(includeRelationships = false): Promise<SchemaResponse> {
    const response = await fetch(
      `${API_BASE}/api/v1/schema?include_relationships=${includeRelationships}`,
      { headers: { 'Authorization': `Bearer ${this.accessToken}` } }
    );
    return response.json();
  }

  // ========== 导出 ==========

  async export(queryId: string, format = 'csv'): Promise<ExportResponse> {
    const response = await fetch(`${API_BASE}/api/v1/export`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${this.accessToken}`,
      },
      body: JSON.stringify({ query_id: queryId, format }),
    });
    return response.json();
  }
}

export const apiClient = new MicroGenBIClient();
export default apiClient;
```

```vue
<!-- QueryPanel.vue -->
<template>
  <div class="query-panel">
    <textarea v-model="queryText" placeholder="输入您的查询..."></textarea>

    <div class="actions">
      <button @click="executeQuery" :disabled="loading">
        {{ loading ? '查询中...' : '查询' }}
      </button>
    </div>

    <div v-if="result" class="result">
      <div class="summary">{{ result.summary }}</div>
      <pre>{{ JSON.stringify(result.data, null, 2) }}</pre>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import apiClient from '@/api/microgenbi';

const queryText = ref('');
const loading = ref(false);
const result = ref<QueryResponse | null>(null);

async function executeQuery() {
  if (!queryText.value.trim()) return;

  loading.value = true;
  try {
    result.value = await apiClient.query(queryText.value);
  } catch (error) {
    console.error('查询失败:', error);
    alert('查询失败: ' + (error as Error).message);
  } finally {
    loading.value = false;
  }
}
</script>
```

---

## 四、对接检查清单

### 4.1 集成前检查

| 检查项 | 说明 |
|-------|------|
| [ ] API 服务已部署并可访问 | `GET /api/v1/health` |
| [ ] 已获取 API Key 或用户凭证 | 联系管理员 |
| [ ] 确认对接环境（生产/预发/测试） | 不同环境不同 URL |
| [ ] 确认目标数据库已注册 | Schema 已配置 |
| [ ] 确认网络策略 | 防火墙白名单（如需要） |

### 4.2 功能验证

| 检查项 | 说明 |
|-------|------|
| [ ] 认证接口可用 | 登录/Token 刷新 |
| [ ] 查询接口可用 | 同步/异步查询 |
| [ ] Schema 接口可用 | 获取数据库结构 |
| [ ] 导出接口可用 | CSV/Excel 导出 |
| [ ] 错误处理正常 | SQL 错误、权限错误等 |
| [ ] SSE 流式接收正常（如使用） | 进度实时更新 |

### 4.3 性能验证

| 检查项 | 说明 |
|-------|------|
| [ ] 响应时间正常 | < 5s（简单查询）|
| [ ] 大结果集处理正常 | > 1000 行 |
| [ ] 并发请求正常 | 5+ 并发 |
| [ ] 长时间查询不超时 | > 30s 查询 |

---

## 五、常见问题

### Q1: Token 过期如何处理？

**A:** 实现 Token 自动刷新机制：
- 在请求前检查 Token 过期时间
- 如果即将过期（剩余 < 60s），先调用 `/auth/refresh`
- 使用过期 Token 请求返回 401，及时刷新重试

### Q2: SSE 连接断开怎么办？

**A:** 实现自动重连：
```javascript
function createSSEWithReconnect(url, onMessage, maxRetries = 3) {
  let retries = 0;

  function connect() {
    const eventSource = new EventSource(url);

    eventSource.onmessage = onMessage;

    eventSource.onerror = () => {
      eventSource.close();
      if (retries < maxRetries) {
        retries++;
        setTimeout(connect, 1000 * retries); // 指数退避
      }
    };

    return eventSource;
  }

  return connect();
}
```

### Q3: 如何处理中文乱码？

**A:** 确保：
1. 请求/响应 Header 设置 `Content-Type: application/json; charset=utf-8`
2. HTTP Client 配置 UTF-8 编码
3. 数据库连接使用 UTF-8 字符集

### Q4: 如何处理大文件导出？

**A:** 使用分页导出：
```python
# 服务端分页导出
for page in range(1, total_pages + 1):
    data = query_page(page)
    write_to_csv(data, append=True)
```

---

## 六、SDK 客户端库（待开发）

计划提供官方 SDK 客户端库：

| 语言 | 仓库 | 状态 |
|------|------|------|
| Python | `pip install microgenbi` | 规划中 |
| .NET | `dotnet add package MicroGenBI.Client` | 规划中 |
| Java | `com.microgenbi:microgenbi-client` | 规划中 |
| TypeScript | `npm install microgenbi-client` | 规划中 |

---

*本文档为 Micro-GenBI 完整的 RESTful API 规范，涵盖所有已规划的功能接口。*


### 1.1 认证接口

#### POST /auth/login
用户登录

**请求体：**
```json
{
  "username": "string",
  "password": "string"
}
```

**响应：**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "expires_in": 3600,
  "user": {
    "id": "string",
    "username": "string",
    "role": "admin|user|readonly",
    "tenant_id": "string"
  }
}
```

---

#### POST /auth/refresh
刷新 Token

**请求头：** `Authorization: Bearer {refresh_token}`

**响应：**
```json
{
  "access_token": "string",
  "expires_in": 3600
}
```

---

#### POST /auth/logout
登出

**请求头：** `Authorization: Bearer {access_token}`

**响应：** `204 No Content`

---

### 1.2 API Key 管理

#### GET /auth/api-keys
获取当前用户的 API Key 列表

**响应：**
```json
{
  "keys": [
    {
      "id": "string",
      "name": "string",
      "scope": "readonly|readwrite",
      "created_at": "2026-05-25T10:00:00Z",
      "expires_at": "2027-05-25T10:00:00Z",
      "last_used_at": "2026-05-25T12:00:00Z",
      "is_active": true
    }
  ]
}
```

---

#### POST /auth/api-keys
创建新的 API Key

**请求体：**
```json
{
  "name": "string",
  "scope": "readonly",
  "expires_in_days": 365,
  "allowed_ips": ["192.168.1.1", "10.0.0.0/8"]
}
```

**响应：**
```json
{
  "id": "string",
  "name": "string",
  "key": "mgbi_sk_xxxx...",  // 仅在此响应中返回一次
  "scope": "readonly",
  "created_at": "2026-05-25T10:00:00Z",
  "expires_at": "2027-05-25T10:00:00Z"
}
```

---

#### DELETE /auth/api-keys/{key_id}
删除 API Key

**响应：** `204 No Content`

---

## 二、核心查询接口

### 2.1 查询执行

#### POST /query
同步提交查询

**请求头：**
- `X-API-Key: {api_key}`
- `X-User-Id: {user_id}` (可选)
- `X-User-Role: {role}` (可选)

**请求体：**
```json
{
  "query": "统计各部门上月报销总额",
  "session_id": "string",           // 可选，用于多轮对话
  "user_id": "string",              // 可选
  "role": "admin|user|readonly",   // 可选
  "generate_chart": true,           // 是否生成图表，默认 true
  "chart_type": "auto|bar|line|pie|table",  // 强制图表类型
  "dialect": "mysql|postgresql|sqlite",      // 目标数据库方言
  "timeout_seconds": 60
}
```

**响应（成功）：**
```json
{
  "sql": "SELECT \"dept_name\" AS \"部门\", SUM(\"amount\") AS \"报销总额\" FROM \"dept_expense\" WHERE ... GROUP BY \"dept_name\" LIMIT 1000",
  "data": [
    {"部门": "销售部", "报销总额": 125000},
    {"部门": "技术部", "报销总额": 98000}
  ],
  "columns": [
    {"name": "部门", "type": "VARCHAR"},
    {"name": "报销总额", "type": "DECIMAL"}
  ],
  "row_count": 2,
  "chart": {
    "type": "bar",
    "options": {}
  },
  "summary": "查询成功，共返回 2 条数据",
  "steps": {
    "intent_classification_ms": 45,
    "schema_retrieval_ms": 120,
    "sql_generation_ms": 850,
    "sql_validation_ms": 15,
    "sql_execution_ms": 230,
    "chart_generation_ms": 45
  },
  "session_id": "sess_abc123",
  "execution_time_ms": 1305
}
```

**响应（错误）：**
```json
{
  "error": {
    "code": "SQL_EXECUTION_ERROR",
    "message": "表不存在: unknown_table",
    "phase": "sql_execution"
  }
}
```

---

#### POST /query/async
异步提交查询

**请求体：** 同 `/query`

**响应：**
```json
{
  "task_id": "task_a1b2c3d4e5f6",
  "status": "pending",
  "created_at": "2026-05-25T10:00:00Z"
}
```

---

#### GET /query/async/{task_id}
查询异步任务状态

**响应：**
```json
{
  "task_id": "task_a1b2c3d4e5f6",
  "status": "success|pending|running|failed|cancelled|timeout",
  "current_step": "sql_execution",
  "progress": 80,
  "result": {
    // 同 /query 的成功响应
  },
  "error": null,
  "created_at": "2026-05-25T10:00:00Z",
  "started_at": "2026-05-25T10:00:01Z",
  "completed_at": "2026-05-25T10:00:05Z"
}
```

---

#### GET /query/async/{task_id}/stream
SSE 流式获取任务进度

**响应（SSE）：**
```
event: step_start
data: {"step": "intent_classification", "timestamp": "2026-05-25T10:00:00Z"}

event: step_complete
data: {"step": "intent_classification", "duration_ms": 45}

event: step_start
data: {"step": "schema_retrieval", "timestamp": "2026-05-25T10:00:00Z"}

event: progress
data: {"progress": 50, "message": "正在执行 SQL..."}

event: complete
data: {"task_id": "task_a1b2c3d4e5f6", "status": "success"}
```

---

#### DELETE /query/async/{task_id}
取消正在执行的任务

**响应：** `204 No Content`

---

### 2.2 查询预览

#### POST /query/preview
实时预览查询结果

**请求体：**
```json
{
  "query": "各部门报销",
  "limit": 5
}
```

**响应：**
```json
{
  "sql": "SELECT ... LIMIT 5",
  "preview_data": [
    {"部门": "销售部", "报销总额": 125000}
  ],
  "total_hint": "完整查询将返回约 15 行数据",
  "intent": "count_aggregate",
  "confidence": 0.92
}
```

---

### 2.3 SQL 版本管理

#### GET /query/history
获取查询历史

**查询参数：**
- `session_id` - 会话 ID
- `limit` - 返回数量，默认 20
- `offset` - 偏移量
- `keyword` - 搜索关键词

**响应：**
```json
{
  "items": [
    {
      "id": "q_001",
      "query": "统计各部门上月报销总额",
      "sql": "SELECT ...",
      "tables_used": ["dept_expense"],
      "execution_time_ms": 1305,
      "row_count": 2,
      "timestamp": "2026-05-25T10:00:00Z",
      "is_favorite": true
    }
  ],
  "total": 150,
  "has_more": true
}
```

---

#### POST /query/history/{query_id}/favorite
收藏查询

**响应：** `204 No Content`

---

#### DELETE /query/history/{query_id}/favorite
取消收藏

**响应：** `204 No Content`

---

#### GET /query/history/{query_id}/versions
获取 SQL 版本历史

**响应：**
```json
{
  "versions": [
    {
      "id": "v_003",
      "sql": "SELECT ... (最新版本)",
      "created_at": "2026-05-25T12:00:00Z",
      "is_current": true,
      "note": "优化 JOIN 顺序"
    },
    {
      "id": "v_002",
      "sql": "SELECT ... (旧版本)",
      "created_at": "2026-05-25T10:00:00Z",
      "is_current": false,
      "note": ""
    }
  ]
}
```

---

#### POST /query/history/{query_id}/rollback
回滚到指定版本

**请求体：**
```json
{
  "version_id": "v_002"
}
```

**响应：**
```json
{
  "new_version_id": "v_004",
  "sql": "SELECT ...",
  "rolled_back_from": "v_003",
  "rolled_back_to": "v_002"
}
```

---

### 2.4 查询建议

#### GET /query/suggestions
获取查询建议

**查询参数：**
- `q` - 用户输入的部分查询

**响应：**
```json
{
  "suggestions": [
    {
      "text": "各储罐当前液位",
      "type": "template",
      "confidence": 0.95,
      "icon": "📊"
    },
    {
      "text": "统计部门分布",
      "type": "field_based",
      "confidence": 0.7,
      "metadata": {"table": "dept", "column": "name"}
    }
  ]
}
```

---

## 三、Schema 管理

### 3.1 Schema 查询

#### GET /schema
获取 Schema 信息

**查询参数：**
- `include_relationships` - 是否包含关系，默认 false
- `include_columns` - 是否包含列信息，默认 true
- `table_filter` - 表名过滤（可选）

**响应：**
```json
{
  "databases": [
    {
      "id": "db_001",
      "name": "oil_depot",
      "display_name": "油库数据库",
      "tables": [
        {
          "name": "tank_inventory",
          "display_name": "储罐库存",
          "description": "各储罐的实时库存数据",
          "columns": [
            {
              "name": "tank_id",
              "display_name": "储罐编号",
              "type": "VARCHAR(20)",
              "description": "储罐唯一标识",
              "is_primary_key": true
            },
            {
              "name": "tank_level",
              "display_name": "液位",
              "type": "DECIMAL(10,2)",
              "description": "当前液位高度(米)"
            }
          ]
        }
      ],
      "relationships": [
        {
          "from_table": "tank_inventory",
          "from_column": "tank_id",
          "to_table": "tank_info",
          "to_column": "tank_id",
          "type": "many-to-one"
        }
      ]
    }
  ]
}
```

---

#### POST /schema/test-connection
测试数据库连接

**请求体：**
```json
{
  "type": "mysql|postgresql|sqlite",
  "host": "localhost",
  "port": 3306,
  "database": "oil_depot",
  "username": "readonly_user",
  "password": "xxx"
}
```

**响应：**
```json
{
  "success": true,
  "latency_ms": 45,
  "tables_count": 25,
  "version": "8.0.32"
}
```

---

#### POST /schema/extract
自动抽取数据库 Schema

**请求体：**
```json
{
  "connection_id": "conn_001",
  "exclude_tables": ["sys_log", "temp_.*"],
  "include_sample_values": true,
  "sample_size": 10
}
```

**响应：**
```json
{
  "yaml_content": "database:\n  name: oil_depot\n  tables:\n    - name: tank_inventory\n      columns:\n        ...",
  "preview": {
    "tables_count": 25,
    "columns_count": 180,
    "relationships_count": 12
  }
}
```

---

#### PUT /schema
保存 Schema 配置

**请求体：** 同 GET /schema 的格式

**响应：** `204 No Content`

---

#### POST /schema/refresh
刷新 Schema

**响应：** `204 No Content`

---

### 3.2 业务字典

#### GET /groups/{group_id}/dictionary
获取业务字典

**响应：**
```json
{
  "group_id": "group_001",
  "tables": [
    {
      "name": "orders",
      "display_name": "订单",
      "columns": [
        {
          "name": "status",
          "display_name": "订单状态",
          "enum_values": [
            {"db_value": "0", "display_value": "待支付"},
            {"db_value": "1", "display_value": "已支付"},
            {"db_value": "2", "display_value": "已完成"}
          ],
          "source": "comment"
        }
      ]
    }
  ],
  "version": 5,
  "updated_at": "2026-05-25T10:00:00Z"
}
```

---

#### PUT /groups/{group_id}/dictionary/columns/{table}/{column}
更新列字典映射

**请求体：**
```json
{
  "display_name": "订单状态",
  "enum_values": [
    {"db_value": "0", "display_value": "待支付"},
    {"db_value": "1", "display_value": "已支付"},
    {"db_value": "2", "display_value": "已完成"},
    {"db_value": "3", "display_value": "已取消"}
  ]
}
```

**响应：** `204 No Content`

---

#### POST /groups/{group_id}/dictionary/rebuild
重建业务字典

**响应：**
```json
{
  "task_id": "task_rebuild_001",
  "status": "pending"
}
```

---

### 3.3 枚举推断

#### GET /groups/{group_id}/enum/inference
获取待确认的枚举推断

**查询参数：**
- `status` - pending|confirmed|rejected
- `limit` - 返回数量

**响应：**
```json
{
  "items": [
    {
      "id": "enum_001",
      "table": "orders",
      "column": "payment_method",
      "inferred_values": [
        {"db_value": "alipay", "display_value": "支付宝", "confidence": 0.95},
        {"db_value": "wxpay", "display_value": "微信支付", "confidence": 0.95},
        {"db_value": "bank", "display_value": "银行转账", "confidence": 0.90}
      ],
      "sample_values": ["alipay", "wxpay", "bank"],
      "status": "pending",
      "created_at": "2026-05-25T10:00:00Z"
    }
  ]
}
```

---

#### POST /groups/{group_id}/enum/confirm-batch
批量确认枚举推断

**请求体：**
```json
{
  "confirmations": [
    {
      "id": "enum_001",
      "action": "confirm",
      "enum_values": [
        {"db_value": "alipay", "display_value": "支付宝"},
        {"db_value": "wxpay", "display_value": "微信支付"},
        {"db_value": "bank", "display_value": "银行转账"}
      ]
    },
    {
      "id": "enum_002",
      "action": "reject",
      "reason": "此字段不是枚举类型"
    }
  ]
}
```

**响应：**
```json
{
  "confirmed": 1,
  "rejected": 1,
  "errors": []
}
```

---

## 四、数据导出

### 4.1 导出执行

#### POST /export
导出查询结果

**请求体：**
```json
{
  "query_id": "q_001",
  "format": "csv|excel|json|sql|pdf",
  "include_headers": true,
  "mask_sensitive": true,
  "max_rows": 10000
}
```

**响应：**
```json
{
  "export_id": "exp_001",
  "status": "processing",
  "download_url": null,
  "expires_at": null
}
```

---

#### GET /export/{export_id}
查询导出状态

**响应：**
```json
{
  "export_id": "exp_001",
  "status": "completed",
  "download_url": "/api/v1/export/exp_001/download?token=xxx",
  "file_size": 102400,
  "row_count": 5000,
  "format": "csv",
  "expires_at": "2026-05-26T10:00:00Z"
}
```

---

#### GET /export/{export_id}/download
下载导出文件

**响应：** 文件流

**查询参数：**
- `token` - 下载 Token

---

## 五、会话管理

### 5.1 会话操作

#### GET /sessions
获取会话列表

**查询参数：**
- `limit` - 返回数量，默认 20
- `offset` - 偏移量

**响应：**
```json
{
  "items": [
    {
      "id": "sess_001",
      "title": "油库库存分析",
      "message_count": 15,
      "created_at": "2026-05-25T10:00:00Z",
      "updated_at": "2026-05-25T12:00:00Z"
    }
  ],
  "total": 50
}
```

---

#### GET /sessions/{session_id}
获取会话详情

**查询参数：**
- `limit` - 消息数量，默认 50

**响应：**
```json
{
  "id": "sess_001",
  "title": "油库库存分析",
  "messages": [
    {
      "id": "msg_001",
      "role": "user",
      "content": "各部门报销总额是多少？",
      "timestamp": "2026-05-25T10:00:00Z"
    },
    {
      "id": "msg_002",
      "role": "assistant",
      "content": "查询成功，共返回 5 条数据",
      "sql": "SELECT ...",
      "data": [],
      "timestamp": "2026-05-25T10:00:05Z"
    }
  ],
  "created_at": "2026-05-25T10:00:00Z"
}
```

---

#### POST /sessions/{session_id}/continue
继续多轮对话

**请求体：**
```json
{
  "query": "环比呢？"
}
```

**响应：** 同 `/query`

---

### 5.2 历史导出

#### POST /sessions/{session_id}/export
导出会话

**请求体：**
```json
{
  "format": "markdown|pdf"
}
```

**响应：**
```json
{
  "export_id": "sess_exp_001",
  "download_url": "/api/v1/export/sess_exp_001/download"
}
```

---

## 六、管理接口

### 6.1 用户管理

#### GET /admin/users
获取用户列表（管理员）

**查询参数：**
- `role` - 角色过滤
- `status` - 状态过滤

**响应：**
```json
{
  "items": [
    {
      "id": "user_001",
      "username": "zhangsan",
      "email": "zhangsan@example.com",
      "role": "user",
      "tenant_id": "tenant_001",
      "is_active": true,
      "last_login_at": "2026-05-25T10:00:00Z",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ],
  "total": 100
}
```

---

#### POST /admin/users
创建用户

**请求体：**
```json
{
  "username": "lisi",
  "email": "lisi@example.com",
  "password": "secure_password",
  "role": "user",
  "tenant_id": "tenant_001"
}
```

**响应：** `201 Created`

---

#### PUT /admin/users/{user_id}
更新用户信息

**请求体：**
```json
{
  "role": "analyst",
  "is_active": true
}
```

**响应：** `204 No Content`

---

### 6.2 角色管理

#### GET /admin/roles
获取角色列表

**响应：**
```json
{
  "roles": [
    {
      "name": "admin",
      "display_name": "管理员",
      "permissions": ["*"],
      "description": "完全控制权限"
    },
    {
      "name": "user",
      "display_name": "普通用户",
      "permissions": ["query:execute", "schema:view", "history:view"],
      "description": "基本查询权限"
    },
    {
      "name": "readonly",
      "display_name": "只读用户",
      "permissions": ["query:execute", "schema:view"],
      "description": "仅能查看，不能导出"
    }
  ]
}
```

---

### 6.3 分组管理

#### GET /groups
获取用户所属分组

**响应：**
```json
{
  "items": [
    {
      "id": "group_001",
      "name": "油库运营部",
      "description": "油库日常运营数据分析",
      "member_count": 25,
      "role": "admin",
      "created_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

---

#### POST /groups
创建分组（管理员）

**请求体：**
```json
{
  "name": "新分组",
  "description": "分组描述",
  "schema_ids": ["schema_001", "schema_002"]
}
```

**响应：** `201 Created`

---

#### GET /groups/{group_id}/members
获取组成员

**响应：**
```json
{
  "members": [
    {
      "user_id": "user_001",
      "username": "zhangsan",
      "role": "admin",
      "joined_at": "2026-01-01T00:00:00Z"
    }
  ]
}
```

---

#### POST /groups/{group_id}/members
添加成员

**请求体：**
```json
{
  "user_id": "user_002",
  "role": "member"
}
```

**响应：** `204 No Content`

---

### 6.4 审计日志

#### GET /admin/audit/logs
获取审计日志

**查询参数：**
- `event_type` - 事件类型过滤
- `user_id` - 用户 ID 过滤
- `start_date` - 开始日期
- `end_date` - 结束日期
- `limit` - 返回数量
- `offset` - 偏移量

**响应：**
```json
{
  "items": [
    {
      "id": "audit_001",
      "timestamp": "2026-05-25T10:00:00Z",
      "event_type": "query.submitted",
      "user_id": "user_001",
      "tenant_id": "tenant_001",
      "ip_address": "192.168.1.100",
      "resource": "query",
      "action": "execute",
      "result": "success",
      "metadata": {
        "sql": "SELECT ...",
        "tables_used": ["tank_inventory"],
        "row_count": 100
      }
    }
  ],
  "total": 10000,
  "has_more": true
}
```

---

#### GET /admin/audit/stats
获取审计统计

**查询参数：**
- `period` - day|week|month

**响应：**
```json
{
  "period": "day",
  "total_queries": 500,
  "successful_queries": 480,
  "failed_queries": 20,
  "blocked_injections": 3,
  "top_users": [
    {"user_id": "user_001", "query_count": 100},
    {"user_id": "user_002", "query_count": 80}
  ],
  "queries_by_hour": [
    {"hour": 9, "count": 50},
    {"hour": 10, "count": 75}
  ]
}
```

---

### 6.5 安全告警

#### GET /admin/audit/alerts
获取安全告警

**响应：**
```json
{
  "alerts": [
    {
      "id": "alert_001",
      "type": "sql_injection_blocked",
      "severity": "high",
      "user_id": "user_003",
      "ip_address": "1.2.3.4",
      "message": "检测到 SQL 注入尝试",
      "details": {
        "query": "'; DROP TABLE users; --",
        "action": "blocked"
      },
      "status": "pending",
      "created_at": "2026-05-25T10:00:00Z"
    }
  ]
}
```

---

#### POST /admin/audit/alerts/{alert_id}/acknowledge
确认告警

**请求体：**
```json
{
  "note": "确认为测试流量"
}
```

**响应：** `204 No Content`

---

### 6.6 LLM 成本统计

#### GET /admin/llm/cost
获取 LLM 成本统计

**查询参数：**
- `period` - day|week|month|all
- `group_by` - provider|model|user

**响应：**
```json
{
  "period": "month",
  "total_calls": 5000,
  "total_tokens": 2500000,
  "total_cost_usd": 12.50,
  "by_provider": {
    "deepseek": 8.00,
    "openai": 4.50
  },
  "by_model": {
    "deepseek-chat": 8.00,
    "gpt-4o-mini": 4.50
  },
  "daily_trend": [
    {"date": "2026-05-01", "cost": 0.50},
    {"date": "2026-05-02", "cost": 0.45}
  ]
}
```

---

#### GET /admin/llm/cost/export
导出成本报告

**查询参数：**
- `period` - day|week|month

**响应：** CSV 文件流

---

## 七、健康与监控

### 7.1 健康检查

#### GET /health
综合健康检查

**响应：**
```json
{
  "status": "healthy|degraded|unhealthy",
  "timestamp": "2026-05-25T10:00:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 15
    },
    "llm": {
      "status": "healthy",
      "latency_ms": 850
    },
    "disk": {
      "status": "healthy",
      "used_percent": 45.2
    },
    "memory": {
      "status": "healthy",
      "used_percent": 62.8
    }
  }
}
```

---

### 7.2 缓存管理

#### GET /groups/{group_id}/cache/stats
获取组级缓存统计

**响应：**
```json
{
  "sql_cache": {
    "entries": 150,
    "hits": 500,
    "misses": 50,
    "hit_rate": 0.91
  },
  "schema_cache": {
    "entries": 5,
    "last_refresh": "2026-05-25T09:00:00Z"
  }
}
```

---

#### POST /groups/{group_id}/cache/invalidate
手动失效缓存

**请求体：**
```json
{
  "type": "sql|schema|all",
  "pattern": "*"  // 可选，匹配模式
}
```

**响应：** `204 No Content`

---

### 7.3 系统指标

#### GET /metrics
获取系统指标

**响应：**
```json
{
  "timestamp": "2026-05-25T10:00:00Z",
  "metrics": {
    "requests_total": 10000,
    "requests_success": 9800,
    "requests_failed": 200,
    "avg_response_time_ms": 250,
    "p95_response_time_ms": 800,
    "p99_response_time_ms": 1500,
    "active_connections": 25,
    "queue_depth": 0
  }
}
```

---

## 八、Webhook 与回调

### 8.1 Webhook 配置

#### GET /webhooks
获取 Webhook 配置

**响应：**
```json
{
  "webhooks": [
    {
      "id": "wh_001",
      "url": "https://example.com/webhook",
      "events": ["query.completed", "alert.triggered"],
      "secret": "whsec_xxx",
      "is_active": true,
      "created_at": "2026-05-01T00:00:00Z"
    }
  ]
}
```

---

#### POST /webhooks
创建 Webhook

**请求体：**
```json
{
  "url": "https://example.com/webhook",
  "events": ["query.completed", "alert.triggered"],
  "secret": "auto_generated"
}
```

**响应：** `201 Created`

---

### 8.2 Webhook 事件

```json
// query.completed
{
  "event": "query.completed",
  "timestamp": "2026-05-25T10:00:00Z",
  "data": {
    "task_id": "task_001",
    "user_id": "user_001",
    "row_count": 100,
    "execution_time_ms": 500
  }
}

// alert.triggered
{
  "event": "alert.triggered",
  "timestamp": "2026-05-25T10:00:00Z",
  "data": {
    "alert_type": "sql_injection_blocked",
    "severity": "high",
    "user_id": "user_003",
    "message": "检测到 SQL 注入尝试"
  }
}
```

---

## 九、错误码定义

| 错误码 | 说明 | HTTP 状态码 |
|--------|------|-------------|
| `INVALID_REQUEST` | 请求参数错误 | 400 |
| `UNAUTHORIZED` | 未认证 | 401 |
| `FORBIDDEN` | 权限不足 | 403 |
| `NOT_FOUND` | 资源不存在 | 404 |
| `RATE_LIMITED` | 请求过于频繁 | 429 |
| `QUERY_TIMEOUT` | 查询超时 | 504 |
| `SQL_SYNTAX_ERROR` | SQL 语法错误 | 422 |
| `SQL_INJECTION_BLOCKED` | SQL 注入被拦截 | 422 |
| `PERMISSION_DENIED` | 权限不足 | 403 |
| `TENANT_VIOLATION` | 租户越权访问 | 403 |
| `INTERNAL_ERROR` | 服务器内部错误 | 500 |

---

## 十、速率限制

| 接口类型 | 限制 | 窗口 |
|---------|------|------|
| 查询接口 | 30 | 每分钟 |
| 查询接口 | 500 | 每小时 |
| 导出接口 | 10 | 每天 |
| 认证接口 | 5 | 每分钟 |

**响应头：**
```
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1621929600
```

---

## 十一、OpenAPI 完整规格

完整的 OpenAPI 3.0 规范请参考 `Micro-GenBI-Integration.md` 中的第 2.2 节。

---

*本文档为 Micro-GenBI 完整的 RESTful API 规范，涵盖所有已规划的功能接口。*
