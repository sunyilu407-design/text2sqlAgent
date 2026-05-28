"""Streamlit 用户端

给普通用户使用的查询界面和配置页面。
"""

from __future__ import annotations

import streamlit as st
import time
import uuid
import requests
import pandas as pd
from typing import Optional

from micro_genbi import __version__
from micro_genbi.ui.schema_browser import (
    render_schema_browser_page,
    render_cross_db_relations_page,
)

# API 配置
API_BASE_URL = "http://localhost:8000"


def init_session_state():
    """初始化会话状态"""
    if "session_id" not in st.session_state:
        st.session_state.session_id = str(uuid.uuid4())

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if "query_history" not in st.session_state:
        st.session_state.query_history = []

    # 用户信息
    if "user" not in st.session_state:
        st.session_state.user = {
            "user_id": "dev_user",
            "tenant_id": "default",
            "role": "user",
        }

    # 当前选中的项目和数据源
    if "current_project" not in st.session_state:
        st.session_state.current_project = None

    if "current_connection" not in st.session_state:
        st.session_state.current_connection = None

    if "current_page" not in st.session_state:
        st.session_state.current_page = "query"

    if "selected_conn_for_schema" not in st.session_state:
        st.session_state.selected_conn_for_schema = None


def get_headers():
    """获取请求头"""
    return {
        "Content-Type": "application/json",
        "X-User-Id": st.session_state.user.get("user_id", ""),
        "X-User-Role": st.session_state.user.get("role", "user"),
        "X-Tenant-Id": st.session_state.user.get("tenant_id", "default"),
    }


def api_get(endpoint: str):
    """GET 请求"""
    try:
        resp = requests.get(f"{API_BASE_URL}{endpoint}", headers=get_headers(), timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text}
    except Exception as e:
        return {"error": str(e)}


def api_post(endpoint: str, data: dict):
    """POST 请求"""
    try:
        resp = requests.post(f"{API_BASE_URL}{endpoint}", json=data, headers=get_headers(), timeout=60)
        if resp.status_code in [200, 201]:
            return resp.json()
        return {"error": resp.text, "status_code": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def api_delete(endpoint: str):
    """DELETE 请求"""
    try:
        resp = requests.delete(f"{API_BASE_URL}{endpoint}", headers=get_headers(), timeout=10)
        return {"success": resp.status_code in [200, 204]}
    except Exception as e:
        return {"error": str(e)}


def call_api_query(query: str) -> dict:
    """调用多库感知 API 执行查询"""
    try:
        payload = {
            "query": query,
            "connection_id": st.session_state.current_connection,
        }
        resp = requests.post(
            f"{API_BASE_URL}/api/v1/query/multi",
            json=payload,
            headers=get_headers(),
            timeout=60,
        )
        if resp.status_code == 200:
            return resp.json()
        return {"error": f"API 错误: {resp.status_code}", "detail": resp.text}
    except requests.exceptions.ConnectionError:
        return {"error": "无法连接到 API 服务", "detail": "请确保 FastAPI 服务正在运行"}
    except Exception as e:
        return {"error": str(e)}


# =============================================================================
# 侧边栏
# =============================================================================

def render_sidebar():
    """渲染侧边栏"""
    with st.sidebar:
        st.header("📱 功能菜单")

        pages = {
            "🔍 数据查询": "query",
            "🗂️ Schema 浏览器": "schema",
            "🌐 跨库关联": "cross_db_relations",
            "📁 项目管理": "projects",
            "🔌 LLM 配置": "llm_config",
            "🗄️ 数据源": "datasource",
            "🔑 API Key": "apikey",
            "📊 我的消耗": "cost",
            "📝 查询历史": "history",
            "⭐ 收藏查询": "favorites",
            "📤 导出": "export",
            "⚙️ 设置": "settings",
            "❓ 帮助": "help",
        }

        for label, page_id in pages.items():
            if st.button(label, use_container_width=True, key=f"nav_{page_id}"):
                st.session_state.current_page = page_id
                st.rerun()

        st.markdown("---")

        # 用户信息
        st.header("👤 当前用户")
        st.write(f"用户: `{st.session_state.user.get('user_id', 'N/A')}`")
        st.write(f"租户: `{st.session_state.user.get('tenant_id', 'N/A')}`")
        st.write(f"角色: `{st.session_state.user.get('role', 'N/A')}`")

        st.markdown("---")

        # 快速链接
        st.header("🔗 链接")
        st.markdown("- [API 文档](/docs)")
        st.markdown("- [Swagger UI](/docs)")
        st.markdown("- [管理后台](#)")


# =============================================================================
# 页面：数据查询
# =============================================================================

def render_query_page():
    """数据查询页面"""
    st.title("🔍 智能数据分析")

    # 获取项目和连接列表
    projects_data = api_get("/api/v1/admin/projects/with-connections")

    # 项目和数据源选择
    col1, col2 = st.columns(2)

    with col1:
        # 项目选择
        if isinstance(projects_data, list) and projects_data:
            project_options = {p["name"]: p["id"] for p in projects_data}
            selected_project_name = st.selectbox(
                "📁 选择项目",
                options=["全部项目"] + list(project_options.keys()),
                index=0
            )
            if selected_project_name == "全部项目":
                st.session_state.current_project = None
            else:
                st.session_state.current_project = project_options[selected_project_name]
        else:
            st.selectbox("📁 选择项目", options=["暂无项目，请先添加数据源"], disabled=True)
            st.session_state.current_project = None

    with col2:
        # 数据源选择
        if isinstance(projects_data, list) and projects_data:
            connections = []
            if st.session_state.current_project:
                for p in projects_data:
                    if p["id"] == st.session_state.current_project:
                        connections = p.get("connections", [])
                        break
            else:
                for p in projects_data:
                    connections.extend(p.get("connections", []))

            if connections:
                conn_options = {c["name"]: c["id"] for c in connections}
                selected_conn_name = st.selectbox(
                    "🗄️ 选择数据源",
                    options=["全部数据源"] + list(conn_options.keys()),
                    index=0
                )
                if selected_conn_name == "全部数据源":
                    st.session_state.current_connection = None
                else:
                    st.session_state.current_connection = conn_options[selected_conn_name]
            else:
                st.selectbox("🗄️ 选择数据源", options=["当前项目暂无数据源"], disabled=True)
        else:
            st.selectbox("🗄️ 选择数据源", options=["暂无数据源"], disabled=True)

    # 显示当前选择
    if st.session_state.current_project or st.session_state.current_connection:
        st.info(f"当前: 项目={st.session_state.current_project or '全部'}, 数据源={st.session_state.current_connection or '全部'}")

    st.markdown("---")

    # 查询输入
    query = st.chat_input("输入您的数据分析问题...")

    # 显示历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if "sql" in msg:
                st.code(msg["sql"], language="sql")
            if "data" in msg and msg["data"]:
                st.dataframe(msg["data"], use_container_width=True)
            if "chart" in msg and msg["chart"]:
                st.info("图表渲染中...")

    # 处理查询
    if query:
        handle_query(query)


def handle_query(query: str):
    """处理查询"""
    st.session_state.messages.append({
        "role": "user",
        "content": query,
    })

    with st.chat_message("user"):
        st.markdown(query)

    with st.chat_message("assistant"):
        with st.spinner("正在分析..."):
            try:
                result = call_api_query(query)

                if "error" not in result:
                    # ── 多库模式指示器 ──────────────────────────────────────
                    query_mode = result.get("query_mode")
                    if query_mode:
                        mode_emoji = result.get("query_mode_emoji", "")
                        mode_label = result.get("query_mode_label", query_mode)
                        mode_color = result.get("query_mode_color", "#3E6AE1")

                        if result.get("is_multi_db"):
                            if result.get("rejected_reason"):
                                # 拒绝查询
                                st.warning(
                                    f"{mode_emoji} **{mode_label}** — 查询被拒绝\n\n"
                                    f"**原因**: {result.get('rejected_reason', '未知原因')}\n\n"
                                    f"请在「跨库关联」页面配置所需的关联关系后重试。"
                                )
                                st.session_state.messages.append({
                                    "role": "assistant",
                                    "content": f"[拒绝] {result.get('rejected_reason', '')}",
                                })
                                return
                            else:
                                st.info(
                                    f"{mode_emoji} **{mode_label}** — "
                                    f"涉及 {len(result.get('sub_results', []))} 个数据源"
                                )
                        else:
                            st.caption(
                                f"{mode_emoji} {mode_label}"
                            )

                    # ── 子查询结果详情（多库场景）───────────────────────────
                    sub_results = result.get("sub_results", [])
                    if sub_results and len(sub_results) > 1:
                        with st.expander("📡 各数据源执行详情", expanded=False):
                            for sub in sub_results:
                                status_icon = "OK" if sub.get("status") == "OK" else "FAIL"
                                st.markdown(
                                    f"- **{sub.get('connection_name', 'Unknown')}**: "
                                    f"{status_icon} | "
                                    f"{sub.get('row_count', 0)} 行 | "
                                    f"{sub.get('latency_ms', 0)}ms"
                                )
                                if sub.get("error"):
                                    st.error(f"  错误: {sub['error']}")

                    # 显示 SQL
                    st.markdown("**📊 生成的 SQL：**")
                    st.code(result.get("sql", ""), language="sql")

                    # 显示数据
                    if result.get("data"):
                        st.markdown(f"**📋 查询结果：** ({len(result['data'])} 行)")
                        st.dataframe(result["data"], use_container_width=True)

                    # 显示摘要
                    if result.get("summary"):
                        st.success(result["summary"])

                    # 保存到历史
                    st.session_state.query_history.append({
                        "query": query,
                        "sql": result.get("sql", ""),
                        "timestamp": time.time(),
                        "query_mode": query_mode,
                    })

                    # 保存消息
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": result.get("summary", "查询完成"),
                        "sql": result.get("sql", ""),
                        "data": result.get("data", []),
                        "query_mode": query_mode,
                    })
                else:
                    st.error(f"查询失败: {result.get('error')}")
                    st.session_state.messages.append({
                        "role": "assistant",
                        "content": f"查询失败: {result.get('error')}",
                    })

            except Exception as e:
                error_msg = f"发生错误: {str(e)}"
                st.error(error_msg)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_msg,
                })


# =============================================================================
# 页面：LLM 配置
# =============================================================================

def render_llm_config_page():
    """LLM 配置页面"""
    st.title("🔌 LLM 配置")

    st.info("配置您使用的 LLM 模型，可以添加多个配置并设置默认模型。")

    tab1, tab2 = st.tabs(["📋 我的配置", "➕ 添加配置"])

    with tab1:
        st.subheader("LLM 配置列表")

        configs = api_get("/api/v1/admin/llm-configs")

        if isinstance(configs, list):
            if not configs:
                st.info("暂无配置，点击「添加配置」添加您的第一个 LLM 配置")
            else:
                for config in configs:
                    with st.expander(f"**{config.get('name', '未命名')}** - {config.get('provider', '').upper()}"):
                        col1, col2 = st.columns([3, 1])

                        with col1:
                            st.write(f"**提供商**: {config.get('provider', '')}")
                            st.write(f"**模型**: {config.get('model', '')}")
                            st.write(f"**温度**: {config.get('temperature', 0.7)}")
                            st.write(f"**最大 Token**: {config.get('max_tokens', 2000)}")
                            st.write(f"**默认**: {'✅ 是' if config.get('is_default') else '否'}")

                        with col2:
                            if st.button("🧪 测试", key=f"test_llm_{config.get('id')}"):
                                result = api_post(f"/api/v1/admin/llm-configs/{config.get('id')}/test", {})
                                if result.get("success"):
                                    st.success(f"测试成功! 延迟: {result.get('latency_ms')}ms")
                                else:
                                    st.error(f"测试失败: {result.get('error')}")

                            if st.button("🗑️ 删除", key=f"del_llm_{config.get('id')}"):
                                api_delete(f"/api/v1/admin/llm-configs/{config.get('id')}")
                                st.rerun()

    with tab2:
        st.subheader("添加 LLM 配置")

        with st.form("llm_form"):
            name = st.text_input("配置名称", placeholder="例如: DeepSeek 生产环境")
            provider = st.selectbox("提供商", ["deepseek", "openai", "ollama"])

            api_key = st.text_input("API Key", type="password", placeholder="sk-xxxx")

            if provider == "deepseek":
                base_url = "https://api.deepseek.com"
                model = st.selectbox("模型", ["deepseek-chat", "deepseek-coder"])
            elif provider == "openai":
                base_url = "https://api.openai.com/v1"
                model = st.selectbox("模型", ["gpt-4o-mini", "gpt-4o"])
            else:
                base_url = st.text_input("Ollama 地址", value="http://localhost:11434")
                model = st.selectbox("模型", ["llama3", "qwen2", "mistral"])

            col1, col2 = st.columns(2)
            with col1:
                temperature = st.slider("温度", 0.0, 2.0, 0.7, 0.1)
            with col2:
                max_tokens = st.number_input("最大 Token", 100, 32000, 2000, 100)

            is_default = st.checkbox("设为默认配置")

            if st.form_submit_button("💾 保存配置"):
                if not name or not api_key:
                    st.error("请填写配置名称和 API Key")
                else:
                    data = {
                        "name": name,
                        "provider": provider,
                        "api_key": api_key,
                        "base_url": base_url,
                        "model": model,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                        "is_default": is_default,
                    }
                    result = api_post("/api/v1/admin/llm-configs", data)
                    if "error" not in result:
                        st.success("配置保存成功!")
                        st.rerun()
                    else:
                        st.error(f"保存失败: {result.get('error')}")


# =============================================================================
# 页面：项目管理
# =============================================================================

def render_projects_page():
    """项目管理页面"""
    st.title("📁 项目管理")

    st.info("项目用于对数据源进行分组管理，方便按业务线组织数据。")

    tab1, tab2 = st.tabs(["📋 项目列表", "➕ 新建项目"])

    with tab1:
        st.subheader("我的项目")

        projects_data = api_get("/api/v1/admin/projects")

        if isinstance(projects_data, list):
            if not projects_data:
                st.info("暂无项目，点击「新建项目」创建")
            else:
                for proj in projects_data:
                    with st.expander(f"{proj.get('icon', '📁')} **{proj.get('name', '未命名')}**"):
                        col1, col2 = st.columns([3, 1])
                        with col1:
                            st.write(f"**描述**: {proj.get('description', '无')}")
                            st.write(f"**创建时间**: {proj.get('created_at', 'N/A')}")
                        with col2:
                            if st.button("🗑️ 删除", key=f"del_proj_{proj.get('id')}"):
                                api_delete(f"/api/v1/admin/projects/{proj.get('id')}")
                                st.rerun()

    with tab2:
        st.subheader("新建项目")

        with st.form("project_form"):
            name = st.text_input("项目名称", placeholder="例如: 油库生产系统")
            description = st.text_area("项目描述", placeholder="简要描述项目用途")

            col1, col2 = st.columns(2)
            with col1:
                icon = st.selectbox(
                    "图标",
                    options=["📁", "🏭", "💼", "📊", "🔬", "🎯", "🚀", "💡"],
                    index=0
                )
            with col2:
                color = st.color_picker("主题颜色", value="#4CAF50")

            if st.form_submit_button("💾 创建项目"):
                if not name:
                    st.error("请填写项目名称")
                else:
                    data = {
                        "name": name,
                        "description": description,
                        "icon": icon,
                        "color": color,
                    }
                    result = api_post("/api/v1/admin/projects", data)
                    if "error" not in result:
                        st.success("项目创建成功!")
                        st.rerun()
                    else:
                        st.error(f"创建失败: {result.get('error')}")


# =============================================================================
# 页面：数据源管理
# =============================================================================

def render_datasource_page():
    """数据源管理页面"""
    st.title("🗄️ 数据源管理")

    st.info("配置您要查询的业务数据库，可以添加多个数据源。")

    tab1, tab2 = st.tabs(["📋 我的数据源", "➕ 添加数据源"])

    with tab1:
        st.subheader("数据库连接列表")

        # 获取所有连接和关联数据
        connections = api_get("/api/v1/admin/connections")
        rel_resp = requests.get(
            f"{API_BASE_URL}/api/v1/schema/relations",
            headers=get_headers(),
            timeout=10,
        )
        all_relations = rel_resp.json() if rel_resp.status_code == 200 else []

        if isinstance(connections, list):
            if not connections:
                st.info("暂无数据源，点击「添加数据源」配置您的第一个数据库")
            else:
                # 统计概览
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("数据源总数", len(connections))
                with col2:
                    # 跨库关联数
                    db_types = {}
                    for c in connections:
                        t = c.get("db_type", "unknown")
                        db_types[t] = db_types.get(t, 0) + 1
                    type_str = " / ".join(f"{k.upper()}: {v}" for k, v in db_types.items())
                    st.metric("类型分布", type_str or "—")
                with col3:
                    cross_count = len(set(
                        r.get("source_connection_id") for r in all_relations
                    ))
                    st.metric("已配置跨库关联", cross_count)

                st.markdown("---")

                for conn in connections:
                    conn_id = conn.get("id", "")
                    conn_name = conn.get("name", "未命名")
                    conn_type = conn.get("db_type", "").upper()

                    # 计算该连接涉及多少跨库关联
                    my_rels = [r for r in all_relations
                               if r.get("source_connection_id") == conn_id
                               or r.get("target_connection_id") == conn_id]

                    with st.expander(
                        f"**{conn_name}**  "
                        + f"`{conn_type}`  "
                        + (f"| 🔗 {len(my_rels)} 个跨库关联" if my_rels else ""),
                    ):
                        col1, col2, col3 = st.columns([2, 2, 1])

                        with col1:
                            st.write(f"**类型**: {conn_type}")
                            if conn.get("host"):
                                st.write(f"**地址**: {conn.get('host')}:{conn.get('port')}")
                            st.write(f"**数据库**: `{conn.get('database_name', '')}`")
                            st.write(f"**默认**: {'✅ 是' if conn.get('is_default') else '否'}")

                            if my_rels:
                                st.write(f"**跨库关联**: {len(my_rels)} 个")
                                for r in my_rels[:3]:
                                    other = (r.get("target_connection_id") if
                                             r.get("source_connection_id") == conn_id
                                             else r.get("source_connection_id"))
                                    other_name = next(
                                        (c.get("name", "") for c in connections
                                         if c.get("id") == other), other
                                    )
                                    st.write(
                                        f"  → {other_name}: "
                                        f"{r.get('source_table', '')}."
                                        f"{r.get('source_column', '')} "
                                        f"↔ {r.get('target_table', '')}."
                                        f"{r.get('target_column', '')}"
                                    )
                                if len(my_rels) > 3:
                                    st.write(f"  ... 还有 {len(my_rels) - 3} 个")

                        with col2:
                            # Schema 快速预览
                            cache_key = f"schema_preview_{conn_id}"
                            if st.button("🔄 抽取 Schema", key=f"extract_{conn_id}", use_container_width=True):
                                with st.spinner("正在抽取..."):
                                    resp = requests.get(
                                        f"{API_BASE_URL}/api/v1/schema/extract/{conn_id}",
                                        headers=get_headers(),
                                        timeout=60,
                                    )
                                if resp.status_code == 200:
                                    schema = resp.json()
                                    tables = schema.get("tables", [])
                                    st.session_state[cache_key] = schema
                                    st.success(
                                        f"成功！发现 {len(tables)} 张表"
                                    )
                                else:
                                    st.error(f"抽取失败: {resp.text}")

                            # 显示 Schema 预览
                            if cache_key in st.session_state:
                                schema = st.session_state[cache_key]
                                tables = schema.get("tables", [])
                                if tables:
                                    table_names = [t.get("name", "") for t in tables[:10]]
                                    if len(tables) > 10:
                                        table_names.append(f"...还有 {len(tables) - 10} 张")
                                    st.write("**表列表**: " + ", ".join(f"`{n}`" for n in table_names))

                            # 查看 ER 图按钮
                            if st.button("🔗 查看 ER 图", key=f"er_{conn_id}", use_container_width=True):
                                st.session_state.current_page = "schema"
                                st.session_state.selected_conn_for_schema = conn_id
                                st.rerun()

                            # 导出 YAML
                            if st.button("📄 导出 YAML", key=f"yaml_{conn_id}", use_container_width=True):
                                resp = requests.get(
                                    f"{API_BASE_URL}/api/v1/schema/extract/{conn_id}/yaml",
                                    headers=get_headers(),
                                    timeout=30,
                                )
                                if resp.status_code == 200:
                                    yaml_content = resp.json().get("yaml_content", "")
                                    st.download_button(
                                        "💾 下载 YAML",
                                        data=yaml_content,
                                        file_name=f"schema_{conn_name}.yaml",
                                        mime="text/yaml",
                                        key=f"dl_yaml_{conn_id}",
                                    )
                                else:
                                    st.error(f"导出失败: {resp.text}")

                        with col3:
                            if st.button("🔗 测试连接", key=f"test_ds_{conn_id}", use_container_width=True):
                                with st.spinner("正在测试连接..."):
                                    result = api_post(f"/api/v1/admin/connections/{conn_id}/test", {})
                                if result.get("success"):
                                    st.success(
                                        f"✅ 连接成功！\n\n"
                                        f"- 延迟: {result.get('latency_ms', 0)}ms\n"
                                        f"- 表数量: {result.get('tables_count', '?')}"
                                    )
                                else:
                                    st.error(f"❌ 连接失败: {result.get('error', '未知错误')}")

                            if st.button("🌐 跨库关联", key=f"cross_{conn_id}", use_container_width=True):
                                st.session_state.current_page = "cross_db_relations"
                                st.rerun()

                            if st.button("🗑️ 删除", key=f"del_ds_{conn_id}", use_container_width=True):
                                api_delete(f"/api/v1/admin/connections/{conn_id}")
                                st.rerun()

    with tab2:
        st.subheader("添加数据源")

        with st.form("datasource_form"):
            name = st.text_input("连接名称", placeholder="例如: 油库生产数据库")

            # 项目选择
            projects_data = api_get("/api/v1/admin/projects")
            if isinstance(projects_data, list) and projects_data:
                project_options = {p["name"]: p["id"] for p in projects_data}
                selected_project = st.selectbox(
                    "📁 所属项目",
                    options=["不指定项目"] + list(project_options.keys()),
                    index=0
                )
                project_id = project_options.get(selected_project) if selected_project != "不指定项目" else None
            else:
                st.info("暂无项目，数据源将不关联任何项目")
                project_id = None

            db_type = st.selectbox("数据库类型", ["postgresql", "mysql", "sqlite"])

            if db_type != "sqlite":
                col1, col2 = st.columns(2)
                with col1:
                    host = st.text_input("主机", value="localhost")
                with col2:
                    port = st.number_input("端口", value=5432 if db_type == "postgresql" else 3306)
            else:
                host, port = None, None

            database_name = st.text_input("数据库名称/文件路径", placeholder="oil_depot.db 或 oil_depot")

            if db_type != "sqlite":
                col1, col2 = st.columns(2)
                with col1:
                    username = st.text_input("用户名")
                with col2:
                    password = st.text_input("密码", type="password")
            else:
                username, password = None, None

            is_default = st.checkbox("设为默认数据源")

            if st.form_submit_button("🔗 测试并保存"):
                if not name or not database_name:
                    st.error("请填写必填项")
                else:
                    data = {
                        "name": name,
                        "project_id": project_id,
                        "db_type": db_type,
                        "host": host,
                        "port": port,
                        "database_name": database_name,
                        "username": username,
                        "password": password,
                        "is_default": is_default,
                    }
                    result = api_post("/api/v1/admin/connections", data)
                    if "error" not in result:
                        st.success("数据源保存成功!")
                        st.rerun()
                    else:
                        st.error(f"保存失败: {result.get('error')}")


# =============================================================================
# 页面：API Key
# =============================================================================

def render_apikey_page():
    """API Key 页面"""
    st.title("🔑 API Key")

    st.info("API Key 用于程序化访问 Micro-GenBI，适合对接其他系统。")

    tab1, tab2 = st.tabs(["📋 我的 Key", "➕ 创建 Key"])

    with tab1:
        st.subheader("API Key 列表")

        keys = api_get("/api/v1/admin/api-keys")

        if isinstance(keys, list):
            if not keys:
                st.info("暂无 API Key，点击「创建 Key」生成")
            else:
                for key in keys:
                    with st.expander(f"**{key.get('name', '未命名')}**"):
                        st.write(f"**前缀**: `{key.get('key_prefix', '')}***`")
                        st.write(f"**权限**: {key.get('scope', 'readonly')}")
                        st.write(f"**创建时间**: {key.get('created_at', 'N/A')}")

        # 显示新创建的 Key
        if "new_key" in st.session_state:
            st.success("✅ API Key 创建成功！请妥善保管，以下是您的 Key：")
            st.code(st.session_state.new_key)
            st.warning("⚠️ 此 Key 只显示一次，请立即复制保存！")
            if st.button("✅ 我已保存"):
                del st.session_state.new_key
                st.rerun()

    with tab2:
        st.subheader("创建 API Key")

        with st.form("apikey_form"):
            name = st.text_input("Key 名称", placeholder="例如: 对接财务系统")
            scope = st.selectbox("权限范围", ["readonly", "readwrite"], help="readonly: 只读，readwrite: 读写")
            expires_days = st.number_input("有效期（天）", 0, 365, 365, help="0 表示永不过期")

            st.info(f"有效期: {'永不过期' if expires_days == 0 else f'{expires_days} 天后过期'}")

            if st.form_submit_button("🔑 生成 Key"):
                if not name:
                    st.error("请填写 Key 名称")
                else:
                    data = {
                        "name": name,
                        "scope": scope,
                        "expires_in_days": expires_days if expires_days > 0 else None,
                    }
                    result = api_post("/api/v1/admin/api-keys", data)
                    if "error" not in result:
                        new_key = result.get("key", result.get("key_prefix", "mgbi_sk") + "xxxxxxxxxx")
                        st.session_state.new_key = new_key
                        st.rerun()
                    else:
                        st.error(f"创建失败: {result.get('error')}")


# =============================================================================
# 页面：我的消耗
# =============================================================================

def render_cost_page():
    """消耗统计页面"""
    st.title("📊 我的 Token 消耗")

    # 时间范围
    col1, col2 = st.columns([1, 3])
    with col1:
        period = st.selectbox("统计周期", ["今天", "本周", "本月", "本季度"])

    st.markdown("---")

    # 概览
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("总 Token", "156K", "+12%")
    with col2:
        st.metric("查询次数", "456", "+8%")
    with col3:
        st.metric("平均每次", "342 tokens", "-5%")
    with col4:
        st.metric("预估成本", "$0.78", "+10%")

    st.markdown("---")

    # 趋势图
    st.subheader("📈 消耗趋势")

    from datetime import datetime, timedelta
    import random

    dates = [(datetime.now() - timedelta(days=i)).strftime('%m-%d') for i in range(7, -1, -1)]
    tokens = [random.randint(10000, 30000) for _ in range(8)]

    chart_data = {"日期": dates, "Token": tokens}
    st.line_chart(pd.DataFrame(chart_data).set_index("日期"))

    st.markdown("---")

    # 按模型统计
    st.subheader("📊 按模型统计")

    model_stats = [
        {"模型": "deepseek-chat", "调用次数": "300", "Token": "100K", "成本": "$0.50"},
        {"模型": "gpt-4o-mini", "调用次数": "150", "Token": "50K", "成本": "$0.25"},
    ]
    st.dataframe(pd.DataFrame(model_stats), use_container_width=True)


# =============================================================================
# 页面：查询历史
# =============================================================================

def render_history_page():
    """查询历史页面"""
    st.title("📝 查询历史")

    # 搜索
    search = st.text_input("🔍 搜索历史查询", placeholder="输入关键词搜索")

    st.markdown("---")

    if st.session_state.query_history:
        for i, item in enumerate(reversed(st.session_state.query_history[-20:])):
            with st.expander(f"**{item.get('query', '')[:50]}...**"):
                st.write(f"**时间**: {datetime.fromtimestamp(item.get('timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S')}")
                st.code(item.get('sql', ''), language="sql")

                if st.button("🔄 重新执行", key=f"rerun_{i}"):
                    handle_query(item.get('query', ''))
    else:
        st.info("暂无查询历史，开始您的第一个查询吧！")


# =============================================================================
# 页面：收藏查询
# =============================================================================

def render_favorites_page():
    """收藏查询页面"""
    st.title("⭐ 收藏查询")

    st.info("保存常用的查询，方便快速执行。")

    tab1, tab2 = st.tabs(["📋 我的收藏", "➕ 添加收藏"])

    with tab1:
        st.subheader("收藏列表")

        # 模拟收藏数据
        favorites = [
            {"名称": "各部门报销统计", "查询": "统计各部门上月报销总额", "执行次数": 25, "最后执行": "2026-05-25"},
            {"名称": "储罐库存查询", "查询": "查看所有储罐当前液位", "执行次数": 18, "最后执行": "2026-05-24"},
            {"名称": "订单趋势", "查询": "近30天订单数量趋势", "执行次数": 12, "最后执行": "2026-05-23"},
        ]

        for fav in favorites:
            with st.expander(f"**{fav['名称']}**"):
                st.write(f"**查询**: {fav['查询']}")
                st.write(f"**执行次数**: {fav['执行次数']} | **最后执行**: {fav['最后执行']}")

                col1, col2, col3 = st.columns(3)
                with col1:
                    if st.button("▶️ 执行", key=f"run_{fav['名称']}"):
                        handle_query(fav['查询'])
                with col2:
                    if st.button("✏️ 编辑", key=f"edit_{fav['名称']}"):
                        st.info("编辑功能开发中...")
                with col3:
                    if st.button("🗑️ 删除", key=f"del_{fav['名称']}"):
                        st.warning("删除功能开发中...")

    with tab2:
        st.subheader("添加收藏")

        with st.form("add_favorite"):
            name = st.text_input("收藏名称", placeholder="例如: 月度报表")
            query = st.text_area("查询语句", placeholder="统计各部门上月报销总额")

            if st.form_submit_button("💾 保存收藏"):
                if not name or not query:
                    st.error("请填写完整信息")
                else:
                    st.success("收藏保存成功!")


# =============================================================================
# 页面：数据导出
# =============================================================================

def render_export_page():
    """数据导出页面"""
    st.title("📤 数据导出")

    tab1, tab2 = st.tabs(["📋 导出历史", "➕ 新建导出"])

    with tab1:
        st.subheader("导出历史")

        # 模拟导出历史
        exports = [
            {"文件名": "部门报销统计_20260525.csv", "格式": "CSV", "大小": "125KB", "时间": "2026-05-25 15:30"},
            {"文件名": "储罐库存_20260524.xlsx", "格式": "Excel", "大小": "256KB", "时间": "2026-05-24 10:20"},
            {"文件名": "订单趋势_20260523.json", "格式": "JSON", "大小": "45KB", "时间": "2026-05-23 14:15"},
        ]

        for exp in exports:
            col1, col2, col3, col4 = st.columns([2, 1, 1, 1])
            with col1:
                st.write(f"📄 {exp['文件名']}")
            with col2:
                st.write(f"类型: {exp['格式']}")
            with col3:
                st.write(f"大小: {exp['大小']}")
            with col4:
                st.write(f"时间: {exp['时间']}")

    with tab2:
        st.subheader("新建导出")

        with st.form("export_form"):
            export_type = st.selectbox("导出类型", ["查询结果导出", "历史查询导出"])

            if export_type == "查询结果导出":
                query_id = st.text_input("查询 ID", placeholder="从历史记录中获取")
            else:
                date_range = st.date_input("日期范围", value=(None, None))

            col1, col2 = st.columns(2)
            with col1:
                export_format = st.selectbox("导出格式", ["CSV", "Excel", "JSON", "PDF"])
            with col2:
                max_rows = st.number_input("最大行数", 100, 10000, 1000, 100)

            include_headers = st.checkbox("包含表头", value=True)
            mask_sensitive = st.checkbox("脱敏敏感数据", value=True)

            if st.form_submit_button("📤 开始导出"):
                if export_type == "查询结果导出" and not query_id:
                    st.error("请输入查询 ID")
                else:
                    st.success("导出任务已创建，请在导出历史中查看")


# =============================================================================
# 页面：用户设置
# =============================================================================

def render_settings_page():
    """用户设置页面"""
    st.title("⚙️ 个人设置")

    tab1, tab2, tab3 = st.tabs(["基本设置", "通知设置", "账户安全"])

    with tab1:
        st.subheader("基本设置")

        with st.form("basic_settings"):
            username = st.text_input("用户名", value="dev_user")
            email = st.text_input("邮箱", value="dev@example.com")

            st.markdown("---")
            if st.form_submit_button("💾 保存设置"):
                st.success("设置已保存!")

    with tab2:
        st.subheader("通知设置")

        with st.form("notification_settings"):
            st.toggle("查询完成通知", value=True)
            st.toggle("Token 余额提醒", value=True)
            st.number_input("余额提醒阈值", value=10, min_value=0)
            st.toggle("系统公告", value=True)

            st.markdown("---")
            if st.form_submit_button("💾 保存设置"):
                st.success("通知设置已保存!")

    with tab3:
        st.subheader("修改密码")

        with st.form("password_change"):
            current_password = st.text_input("当前密码", type="password")
            new_password = st.text_input("新密码", type="password")
            confirm_password = st.text_input("确认新密码", type="password")

            st.markdown("---")
            if st.form_submit_button("🔐 修改密码"):
                if new_password != confirm_password:
                    st.error("两次密码不一致")
                else:
                    st.success("密码修改成功!")


# =============================================================================
# 页面：帮助
# =============================================================================

def render_help_page():
    """帮助页面"""
    st.title("❓ 帮助与文档")

    # 使用指南
    st.subheader("📖 快速开始")

    with st.expander("1. 如何进行数据分析？"):
        st.write("""
        1. 在左侧菜单中选择「数据源」，配置您要查询的数据库
        2. 在「LLM 配置」中添加您的 LLM API Key
        3. 返回「数据查询」页面，输入您的自然语言问题
        4. 系统会自动生成 SQL 并执行，返回查询结果
        """)

    with st.expander("2. 如何配置数据库连接？"):
        st.write("""
        1. 进入「数据源」页面
        2. 点击「添加数据源」
        3. 选择数据库类型，填写连接信息
        4. 点击「测试并保存」
        """)

    with st.expander("3. 如何查看数据库结构（Schema）？"):
        st.write("""
        进入「Schema 浏览器」页面：
        1. 选择要查看的数据源
        2. 点击「抽取 Schema」，系统从数据库自动发现所有表结构
        3. 在「表列表」Tab 查看所有表及其列信息（主键/外键）
        4. 在「ER 关系图」Tab 查看表之间的外键关系
        5. 可以导出为 YAML 配置文件，在此基础上补充中文描述
        """)

    with st.expander("4. 如何配置跨库关联（异构多库场景）？"):
        st.write("""
        当您的项目有多个不同的数据库，需要进行跨库 JOIN 查询时：
        1. 进入「跨库关联」页面
        2. 点击「新建关联」
        3. 填写源端和目标端信息（数据库、表名、关联列）
        4. 选择基数类型（1:1 / 1:N / N:1）
        5. 保存后即可进行跨库查询

        注意：跨库关联必须手动配置，LLM 无法自动发现不同数据库之间的表关系！
        """)

    with st.expander("5. 如何配置同构多库聚合（大屏展示）？"):
        st.write("""
        当多个子系统的数据库 Schema 完全相同时（如省级大屏）：
        1. 进入「跨库关联」页面的「数据库分组」Tab
        2. 创建分组，选择「同构聚合」模式
        3. 向分组添加各子系统的数据库成员
        4. 查询时系统会自动向所有成员分发查询并汇总结果
        """)

    with st.expander("6. 如何获取 API Key？"):
        st.write("""
        1. 进入「API Key」页面
        2. 点击「创建 Key」
        3. 填写名称和有效期
        4. 创建后请立即复制保存，Key 只显示一次
        """)

    with st.expander("7. 如何查看 Token 消耗？"):
        st.write("""
        进入「我的消耗」页面，可以查看：
        - 总 Token 消耗
        - 查询次数
        - 消耗趋势图
        - 按模型分类的统计
        """)

    st.markdown("---")

    # 常见问题
    st.subheader("❓ 常见问题")

    with st.expander("Q: 为什么跨库 JOIN 查询失败？"):
        st.write("""
        跨库 JOIN 需要手动配置关联关系。进入「跨库关联」页面，检查是否已为涉及的
        两个数据库建立了关联关系。如果没有，点击「新建关联」进行配置。
        """)

    with st.expander("Q: Schema 抽取失败怎么办？"):
        st.write("请检查：1) 数据库连接是否正常；2) 用户是否有读取权限；3) 数据库是否允许外部访问")

    with st.expander("Q: 查询返回空结果怎么办？"):
        st.write("请检查：1) 数据库中是否有数据；2) 查询条件是否正确；3) Schema 是否配置正确")

    with st.expander("Q: SQL 生成错误怎么办？"):
        st.write("可以尝试：1) 简化查询描述；2) 检查 Schema 配置；3) 查看错误信息后重新描述问题")

    with st.expander("Q: 如何提高查询准确性？"):
        st.write("建议：1) 在 Schema 中配置表和列的中文描述；2) 添加业务术语映射；3) 描述问题时使用明确的业务术语；4) 导出 YAML 后补充 description 字段")

    with st.expander("Q: 多库模式下如何选择查询范围？"):
        st.write("""
        在「数据查询」页面选择数据源时：
        - 选择单个数据源：仅查询该库
        - 选择「全部数据源」：根据分组配置决定是单库查询还是跨库查询
        - 同构多库场景：自动向所有组内成员分发查询并汇总
        - 异构多库场景：必须配置跨库关联才能进行 JOIN 查询
        """)

    st.markdown("---")

    # 快捷键
    st.subheader("⌨️ 快捷键")

    shortcuts = [
        {"快捷键": "Ctrl + Enter", "功能": "执行查询"},
        {"快捷键": "Ctrl + L", "功能": "清空输入"},
        {"快捷键": "Ctrl + /", "功能": "显示/隐藏侧边栏"},
    ]
    st.dataframe(pd.DataFrame(shortcuts), use_container_width=True)

    st.markdown("---")

    # 联系方式
    st.subheader("📧 联系我们")
    st.write("""
    - 技术支持邮箱: support@example.com
    - 产品反馈: feedback@example.com
    - 文档中心: docs.example.com
    """)


# =============================================================================
# 主函数
# =============================================================================

def main():
    """主函数"""
    init_session_state()
    render_sidebar()

    page = st.session_state.get("current_page", "query")

    if page == "query":
        render_query_page()
    elif page == "schema":
        render_schema_browser_page()
    elif page == "cross_db_relations":
        render_cross_db_relations_page()
    elif page == "projects":
        render_projects_page()
    elif page == "llm_config":
        render_llm_config_page()
    elif page == "datasource":
        render_datasource_page()
    elif page == "apikey":
        render_apikey_page()
    elif page == "cost":
        render_cost_page()
    elif page == "history":
        render_history_page()
    elif page == "favorites":
        render_favorites_page()
    elif page == "export":
        render_export_page()
    elif page == "settings":
        render_settings_page()
    elif page == "help":
        render_help_page()


if __name__ == "__main__":
    main()
