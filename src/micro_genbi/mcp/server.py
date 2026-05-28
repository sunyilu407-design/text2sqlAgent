"""MCP Server - JSON-RPC 2.0 实现

支持 Claude Desktop、Claude Code 等 AI Agent 的集成。
"""

from __future__ import annotations

import json
import asyncio
from typing import Any, Optional
from dataclasses import dataclass
from enum import Enum

from micro_genbi import get_logger
from micro_genbi.models import QueryRequest

logger = get_logger(__name__)


class JSONRPCErrorCode(int, Enum):
    """JSON-RPC 错误码"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class JSONRPCRequest:
    """JSON-RPC 请求"""
    jsonrpc: str = "2.0"
    method: str = ""
    params: Optional[dict] = None
    id: Optional[Any] = None


@dataclass
class JSONRPCResponse:
    """JSON-RPC 响应"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[dict] = None
    id: Optional[Any] = None


class MCPError(Exception):
    """MCP 错误"""
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


class MCPServer:
    """
    MCP Server

    实现 JSON-RPC 2.0 协议的 MCP Server。
    支持 tools/list、tools/call 等核心方法。
    """

    def __init__(self, name: str = "Micro-GenBI", version: str = "1.0.0"):
        self.name = name
        self.version = version
        self.tools: dict[str, dict] = {}
        self._register_core_tools()

    def _register_core_tools(self):
        """注册核心工具"""
        self.tools = {
            "execute_data_analysis": {
                "name": "execute_data_analysis",
                "description": "执行自然语言数据分析查询",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "自然语言查询",
                        },
                        "session_id": {
                            "type": "string",
                            "description": "会话 ID（可选）",
                        },
                        "user_id": {
                            "type": "string",
                            "description": "用户 ID（可选）",
                        },
                    },
                    "required": ["query"],
                },
            },
            "get_database_schema": {
                "name": "get_database_schema",
                "description": "获取数据库 Schema 信息",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "include_columns": {
                            "type": "boolean",
                            "description": "是否包含列信息",
                            "default": True,
                        },
                        "table_filter": {
                            "type": "string",
                            "description": "表名过滤（正则）",
                        },
                    },
                },
            },
            "get_query_history": {
                "name": "get_query_history",
                "description": "获取查询历史",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "会话 ID",
                        },
                        "limit": {
                            "type": "integer",
                            "description": "返回数量",
                            "default": 20,
                        },
                    },
                },
            },
            "cancel_task": {
                "name": "cancel_task",
                "description": "取消正在执行的查询任务",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "task_id": {
                            "type": "string",
                            "description": "任务 ID",
                        },
                    },
                    "required": ["task_id"],
                },
            },
        }

    async def handle_request(self, request: JSONRPCRequest) -> JSONRPCResponse:
        """处理 JSON-RPC 请求"""
        try:
            method = request.method

            if method == "tools/list":
                result = await self._list_tools()
            elif method == "tools/call":
                result = await self._call_tool(request.params or {})
            elif method == "initialize":
                result = await self._initialize(request.params or {})
            elif method == "ping":
                result = {"pong": True}
            else:
                raise MCPError(
                    JSONRPCErrorCode.METHOD_NOT_FOUND,
                    f"方法不存在: {method}",
                )

            return JSONRPCResponse(
                jsonrpc="2.0",
                result=result,
                id=request.id,
            )

        except MCPError as e:
            return JSONRPCResponse(
                jsonrpc="2.0",
                error={
                    "code": e.code,
                    "message": e.message,
                    "data": e.data,
                },
                id=request.id,
            )

        except Exception as e:
            logger.error(f"MCP 请求处理失败: {e}")
            return JSONRPCResponse(
                jsonrpc="2.0",
                error={
                    "code": JSONRPCErrorCode.INTERNAL_ERROR,
                    "message": str(e),
                },
                id=request.id,
            )

    async def _initialize(self, params: dict) -> dict:
        """初始化"""
        return {
            "protocolVersion": "2024-11-05",
            "serverInfo": {
                "name": self.name,
                "version": self.version,
            },
            "capabilities": {
                "tools": True,
                "resources": True,
            },
        }

    async def _list_tools(self) -> dict:
        """列出所有工具"""
        return {
            "tools": list(self.tools.values()),
        }

    async def _call_tool(self, params: dict) -> dict:
        """调用工具"""
        tool_name = params.get("name")
        tool_args = params.get("arguments", {})

        if tool_name not in self.tools:
            raise MCPError(
                JSONRPCErrorCode.METHOD_NOT_FOUND,
                f"工具不存在: {tool_name}",
            )

        # 根据工具名称调用
        if tool_name == "execute_data_analysis":
            return await self._execute_data_analysis(tool_args)
        elif tool_name == "get_database_schema":
            return await self._get_database_schema(tool_args)
        elif tool_name == "get_query_history":
            return await self._get_query_history(tool_args)
        elif tool_name == "cancel_task":
            return await self._cancel_task(tool_args)

        raise MCPError(
            JSONRPCErrorCode.METHOD_NOT_FOUND,
            f"工具处理未实现: {tool_name}",
        )

    async def _execute_data_analysis(self, args: dict) -> dict:
        """执行数据分析"""
        query = args.get("query")
        if not query:
            raise MCPError(
                JSONRPCErrorCode.INVALID_PARAMS,
                "缺少必需参数: query",
            )

        try:
            from micro_genbi.service.ask_service import AskService

            service = AskService()
            result = await service.ask(
                query=query,
                user_id=args.get("user_id"),
                session_id=args.get("session_id"),
            )

            text_parts = [
                f"查询: {query}",
                f"\n生成的 SQL:\n{result.sql}",
                f"\n返回 {result.row_count} 行数据",
            ]
            if result.summary:
                text_parts.append(f"\n摘要: {result.summary}")

            return {
                "content": [
                    {
                        "type": "text",
                        "text": "\n".join(text_parts),
                    }
                ],
            }
        except Exception as e:
            logger.error(f"MCP 数据分析失败: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"查询失败: {e}",
                    }
                ],
            }

    async def _get_database_schema(self, args: dict) -> dict:
        """获取数据库 Schema"""
        try:
            from micro_genbi.semantic.schema_registry import SchemaRegistry

            registry = SchemaRegistry()
            registry.load()

            lines = []
            for db in registry.get_all_databases():
                lines.append(f"\n## 数据库: {db.display_name}")
                for table in db.tables:
                    col_lines = []
                    for col in table.columns:
                        col_lines.append(
                            f"  - {col.name}({col.col_type})"
                            + (f": {col.description}" if col.description else "")
                        )
                    lines.append(f"\n### {table.name}")
                    if table.description:
                        lines.append(f"描述: {table.description}")
                    lines.extend(col_lines)

            return {
                "content": [
                    {
                        "type": "text",
                        "text": "\n".join(lines) if lines else "Schema 为空",
                    }
                ],
            }
        except Exception as e:
            logger.error(f"MCP 获取 Schema 失败: {e}")
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"获取 Schema 失败: {e}",
                    }
                ],
            }

    async def _get_query_history(self, args: dict) -> dict:
        """获取查询历史"""
        limit = args.get("limit", 20)
        session_id = args.get("session_id")
        try:
            # 简化实现，实际应从数据库读取
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"最近 {limit} 条查询记录 (session: {session_id or 'all'})",
                    }
                ],
            }
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"获取历史失败: {e}",
                    }
                ],
            }

    async def _cancel_task(self, args: dict) -> dict:
        """取消任务"""
        task_id = args.get("task_id")
        if not task_id:
            raise MCPError(
                JSONRPCErrorCode.INVALID_PARAMS,
                "缺少必需参数: task_id",
            )

        # TODO: 调用 TaskTracker 取消任务
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"任务已取消: {task_id}",
                }
            ],
        }

    async def process_jsonrpc(self, request_text: str) -> str:
        """处理 JSON-RPC 请求文本"""
        try:
            request_dict = json.loads(request_text)
            request = JSONRPCRequest(**request_dict)
            response = await self.handle_request(request)
            return json.dumps(response.__dict__)
        except json.JSONDecodeError as e:
            error_response = JSONRPCResponse(
                jsonrpc="2.0",
                error={
                    "code": JSONRPCErrorCode.PARSE_ERROR,
                    "message": f"JSON 解析失败: {e}",
                },
            )
            return json.dumps(error_response.__dict__)


class StdioMCPServer:
    """
    STDIO 传输的 MCP Server

    用于 Claude Desktop 等桌面应用集成。
    """

    def __init__(self, server: Optional[MCPServer] = None):
        self.server = server or MCPServer()

    async def run(self):
        """运行 Server"""
        logger.info("MCP Server 启动 (stdio 模式)")

        while True:
            try:
                # 从 stdin 读取请求
                line = await asyncio.get_event_loop().run_in_executor(
                    None, input
                )

                if not line:
                    break

                # 处理请求
                response = await self.server.process_jsonrpc(line)
                print(response, flush=True)

            except EOFError:
                break
            except Exception as e:
                logger.error(f"处理失败: {e}")
                error_response = JSONRPCResponse(
                    jsonrpc="2.0",
                    error={
                        "code": JSONRPCErrorCode.INTERNAL_ERROR,
                        "message": str(e),
                    },
                )
                print(json.dumps(error_response.__dict__), flush=True)

        logger.info("MCP Server 关闭")


class SSEMCPServer:
    """
    SSE 传输的 MCP Server

    用于 Claude Code 等命令行工具集成。
    """

    def __init__(self, server: Optional[MCPServer] = None):
        self.server = server or MCPServer()
        self.connections: dict[str, asyncio.Queue] = {}

    async def handle_sse_request(
        self,
        request_id: str,
        request_text: str,
    ):
        """处理 SSE 请求"""
        response = await self.server.process_jsonrpc(request_text)
        return response

    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        for queue in self.connections.values():
            await queue.put(message)


# =============================================================================
# 便捷函数
# =============================================================================

def create_mcp_server() -> MCPServer:
    """创建 MCP Server"""
    return MCPServer(name="Micro-GenBI", version="1.0.0")


async def run_stdio_server():
    """运行 stdio 模式的 MCP Server"""
    server = create_mcp_server()
    stdio_server = StdioMCPServer(server)
    await stdio_server.run()


if __name__ == "__main__":
    asyncio.run(run_stdio_server())
