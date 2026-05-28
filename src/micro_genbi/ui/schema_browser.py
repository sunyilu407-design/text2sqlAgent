"""Streamlit Schema 浏览器页面

展示数据库的表结构、主键、外键关系。
支持 ER 图可视化（使用 Mermaid.js）和跨库关联配置。
"""

from __future__ import annotations

import streamlit as st
import requests
import pandas as pd
from typing import Optional

from micro_genbi.ui.user_app import get_headers, API_BASE_URL, api_get, init_session_state


# =============================================================================
# 辅助函数
# =============================================================================

def get_connection_name(conn_id: str, connections: list) -> str:
    """根据连接 ID 获取连接名称"""
    for c in connections:
        if c.get("id") == conn_id:
            return c.get("name", conn_id)
    return conn_id


def build_mermaid_er(nodes: list[dict], edges: list[dict]) -> str:
    """
    将 ER 数据转换为 Mermaid ER 图代码。

    使用 Mermaid 的 erDiagram 语法。
    """
    lines = ["erDiagram"]

    # 添加表节点
    for node in nodes:
        table_name = node.get("label", node.get("id", "unknown"))

        # 收集所有列
        cols = node.get("columns", [])
        if isinstance(cols, int):
            cols = []

        # 为表生成 Mermaid 列定义
        if cols:
            lines.append(f'    "{table_name}" {{')
            for col in cols:
                col_name = col.get("name", "")
                col_type = col.get("type", "")
                nullable = "?" if col.get("nullable", True) else ""
                pk_marker = "PK" if col.get("is_primary_key", False) else ""
                fk_marker = "FK" if col.get("is_foreign_key", False) else ""
                marker = pk_marker or fk_marker
                lines.append(f'      {col_name}{nullable} {col_type} {marker}')
            lines.append("    }")
        else:
            lines.append(f'    "{table_name}" {{')
            lines.append("      id PK")
            lines.append("    }")

    # 添加关系
    for edge in edges:
        src = edge.get("source", "")
        tgt = edge.get("target", "")
        card = edge.get("cardinality", "")

        if "one_to_one" in card.lower() or "1:1" in card:
            lines.append(f'    "{src}" ||--|| "{tgt}"')
        elif "one_to_many" in card.lower() or "1:N" in card or "many" in card.lower():
            lines.append(f'    "{src}" ||--o{{ "{tgt}"')
        elif "many_to_one" in card.lower():
            lines.append(f'    "{src}" {{--|| "{tgt}"')
        else:
            lines.append(f'    "{src}" -- "{tgt}"')

    return "\n".join(lines)


def build_mermaid_rel_diag(nodes: list[dict], edges: list[dict]) -> str:
    """
    使用 Mermaid 的 flowchart 展示表关系图（更清晰）。

    每个表作为一个节点，关系作为连线。
    """
    lines = ["flowchart LR"]

    for node in nodes:
        nid = node.get("id", "unknown").replace("-", "_").replace(" ", "_")
        label = node.get("label", nid)
        cols = node.get("columns", [])
        col_count = node.get("columns", 0) if isinstance(node.get("columns"), int) else len(cols)
        lines.append(f'    {nid}["{label} ({col_count} 列)"]')

    for edge in edges:
        src = edge.get("source", "").replace("-", "_").replace(" ", "_")
        tgt = edge.get("target", "").replace("-", "_").replace(" ", "_")
        card = edge.get("cardinality", edge.get("card", "FK"))
        lines.append(f'    {src} -->|{card}| {tgt}')

    return "\n".join(lines)


def render_mermaid(mermaid_code: str, height: int = 500) -> str:
    """生成嵌入 Mermaid.js 的 HTML"""
    return f"""
<div class="mermaid" style="display: flex; justify-content: center; overflow-x: auto;">
{mermaid_code}
</div>
<script src="https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.min.js"></script>
<script>
mermaid.initialize({{
    startOnLoad: true,
    theme: 'base',
    themeVariables: {{
        primaryColor: '#3E6AE1',
        primaryTextColor: '#171A20',
        primaryBorderColor: '#D0D1D2',
        lineColor: '#5C5E62',
        secondaryColor: '#F4F4F4',
        tertiaryColor: '#EEEEEE',
        fontSize: '13px'
    }},
    er: {{
        entityPadding: 12,
        minEntityWidth: 100,
        entityHeight: 25
    }}
}});
</script>
<style>
.mermaid {{
    max-width: 100%;
    overflow-x: auto;
    padding: 16px;
}}
</style>
"""


# =============================================================================
# 页面：Schema 浏览器
# =============================================================================

def render_schema_browser_page():
    """Schema 浏览器页面"""
    st.title("🗂️ Schema 浏览器")
    st.caption("查看数据源的结构、主键、外键和表间关联关系")

    # 获取所有连接
    projects_data = api_get("/api/v1/admin/projects/with-connections")
    connections = []

    if isinstance(projects_data, list):
        for p in projects_data:
            connections.extend(p.get("connections", []))

    if not connections:
        st.warning("暂无数据源，请先在「数据源」页面添加数据库连接")
        return

    # 连接选择
    st.subheader("📡 选择数据源")
    col1, col2 = st.columns([2, 3])
    with col1:
        conn_options = {c["name"]: c["id"] for c in connections}
        options_list = list(conn_options.keys())

        # 如果有预选的连接，尝试选中它
        preselected_id = st.session_state.get("selected_conn_for_schema")
        preselected_name = None
        if preselected_id:
            preselected_name = next(
                (name for name, cid in conn_options.items() if cid == preselected_id), None
            )

        default_idx = 0
        if preselected_name and preselected_name in options_list:
            default_idx = options_list.index(preselected_name)

        selected_conn_name = st.selectbox(
            "数据源",
            options=options_list,
            index=default_idx,
            label_visibility="collapsed",
        )
        selected_conn_id = conn_options.get(selected_conn_name)

    if not selected_conn_id:
        return

    # 获取该连接的信息
    selected_conn = next((c for c in connections if c["id"] == selected_conn_id), None)

    # 操作按钮
    col1, col2, col3 = st.columns(3)
    with col1:
        extract_clicked = st.button("🔄 抽取 Schema", use_container_width=True)
    with col2:
        refresh_clicked = st.button("🔗 查看跨库关联", use_container_width=True)
    with col3:
        yaml_clicked = st.button("📄 导出 YAML", use_container_width=True)

    st.markdown("---")

    if yaml_clicked:
        with st.spinner("正在生成 YAML 配置..."):
            resp = requests.get(
                f"{API_BASE_URL}/api/v1/schema/extract/{selected_conn_id}/yaml",
                headers=get_headers(),
                timeout=30,
            )
        if resp.status_code == 200:
            data = resp.json()
            st.success(f"已生成 YAML 配置（连接：{data.get('connection_name', selected_conn_name)}）")
            st.code(data.get("yaml_content", ""), language="yaml")
            st.download_button(
                "💾 下载 YAML",
                data=data.get("yaml_content", ""),
                file_name=f"schema_{selected_conn_id}.yaml",
                mime="text/yaml",
            )
        else:
            st.error(f"导出失败: {resp.text}")

    if extract_clicked or refresh_clicked or "schema_cache" in st.session_state:
        # 缓存 Schema 数据
        cache_key = f"schema_{selected_conn_id}"
        if extract_clicked or cache_key not in st.session_state:
            with st.spinner("正在从数据库抽取 Schema..."):
                resp = requests.get(
                    f"{API_BASE_URL}/api/v1/schema/extract/{selected_conn_id}",
                    headers=get_headers(),
                    timeout=60,
                )
            if resp.status_code == 200:
                schema_data = resp.json()
                st.session_state[cache_key] = schema_data
            else:
                st.error(f"抽取失败: {resp.text}")
                return
        else:
            schema_data = st.session_state.get(cache_key, {})

        tables = schema_data.get("tables", [])
        relationships = schema_data.get("relationships", [])

        if not tables:
            st.warning("未发现任何表，请检查数据库连接")
            return

        # 概览信息
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("表数量", len(tables))
        with col2:
            fk_count = sum(1 for t in tables for _ in t.get("foreign_keys", []))
            st.metric("外键数量", fk_count)
        with col3:
            db_type = schema_data.get("database_type", "unknown")
            st.metric("数据库类型", db_type.upper())

        st.markdown("---")

        # Tab: 表列表 / ER 图 / 跨库关联
        tab1, tab2, tab3 = st.tabs([
            f"📋 表列表 ({len(tables)})",
            "🔗 ER 关系图",
            f"🌐 跨库关联",
        ])

        # ── Tab 1: 表列表 ────────────────────────────────────────────────
        with tab1:
            search = st.text_input(
                "🔍 搜索表名或列名",
                placeholder="输入表名或列名进行过滤...",
                label_visibility="collapsed",
            )
            search_lower = search.lower()

            for table in tables:
                table_name = table.get("name", "")
                columns = table.get("columns", [])
                pk_cols = table.get("primary_keys", [])
                fk_cols = []
                for col in columns:
                    if col.get("is_foreign_key"):
                        fk_cols.append(col.get("name"))

                # 过滤
                if search:
                    match = (
                        search_lower in table_name.lower() or
                        any(search_lower in c.get("name", "").lower() for c in columns)
                    )
                    if not match:
                        continue

                with st.expander(
                    f"**{table_name}**  "
                    f"({len(columns)} 列 | "
                    + (f"PK: {', '.join(pk_cols)}" if pk_cols else "无 PK")
                    + ")",
                    expanded=False,
                ):
                    # 表基本信息
                    row_count = table.get("row_count")
                    if row_count is not None:
                        st.caption(f"行数：{row_count:,} | 表名：`{table_name}`")

                    # 跨库关联
                    cross_db = table.get("cross_db_relations", [])
                    if cross_db:
                        st.info(f"跨库关联：{len(cross_db)} 个")

                    # 列详情
                    if columns:
                        col_data = []
                        for col in columns:
                            tags = []
                            if col.get("is_primary_key"):
                                tags.append("PK")
                            if col.get("is_foreign_key"):
                                tags.append("FK")
                            col_data.append({
                                "列名": col.get("name", ""),
                                "类型": col.get("type", ""),
                                "可空": "✅" if col.get("nullable", True) else "❌",
                                "标识": " ".join(tags) if tags else "—",
                                "说明": col.get("description", ""),
                            })
                        st.dataframe(
                            pd.DataFrame(col_data),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.info("该表无列信息")

        # ── Tab 2: ER 关系图 ────────────────────────────────────────────
        with tab2:
            # 构建 Mermaid 数据
            nodes = []
            for t in tables:
                pk_cols = t.get("primary_keys", [])
                fk_cols = []
                for col in t.get("columns", []):
                    if col.get("is_foreign_key"):
                        fk_cols.append(col.get("name"))
                nodes.append({
                    "id": t.get("name", ""),
                    "label": t.get("name", ""),
                    "pk": pk_cols,
                    "fk": fk_cols,
                    "columns": t.get("columns", []),
                })

            edges = []
            for t in tables:
                for fk in t.get("foreign_keys", []):
                    edges.append({
                        "source": t.get("name", ""),
                        "source_col": fk.get("constrained_columns", [""])[0],
                        "target": fk.get("referred_table", ""),
                        "target_col": fk.get("referred_columns", [""])[0],
                        "cardinality": "FK",
                        "type": "has_fk",
                    })

            if not edges:
                st.info("该数据库中没有发现外键关系（可能尚未配置外键）")
            else:
                # 使用 Mermaid 渲染
                st.subheader("表关系图（库内 FK）")
                st.caption("连线表示外键关系，箭头指向被引用的表")

                mermaid_code = build_mermaid_rel_diag(nodes, edges)
                st.markdown(render_mermaid(mermaid_code), unsafe_allow_html=True)

            # 如果表数量不多，也展示 ER 图
            if len(tables) <= 30 and edges:
                with st.expander("📊 ER 图（另一种视图）"):
                    er_code = build_mermaid_er(nodes, edges)
                    st.markdown(render_mermaid(er_code, height=400), unsafe_allow_html=True)

        # ── Tab 3: 跨库关联 ──────────────────────────────────────────────
        with tab3:
            st.subheader("跨库关联关系")
            st.info(
                "跨库关联需要手动配置。只有配置了跨库关联，两个不同数据库之间才能进行 JOIN 查询。"
            )

            # 获取跨库关联列表
            rel_resp = requests.get(
                f"{API_BASE_URL}/api/v1/schema/relations",
                headers=get_headers(),
                timeout=10,
            )
            if rel_resp.status_code == 200:
                relations = rel_resp.json()
                # 只显示涉及当前连接的关联
                my_relations = [
                    r for r in relations
                    if r.get("source_connection_id") == selected_conn_id
                    or r.get("target_connection_id") == selected_conn_id
                ]
            else:
                my_relations = []

            if my_relations:
                st.write(f"当前数据源有 **{len(my_relations)}** 个跨库关联：")
                rel_data = []
                for r in my_relations:
                    src_name = get_connection_name(r.get("source_connection_id", ""), connections)
                    tgt_name = get_connection_name(r.get("target_connection_id", ""), connections)
                    rel_data.append({
                        "名称": r.get("name", ""),
                        "源数据库": src_name if r.get("source_connection_id") != selected_conn_id else "当前库",
                        "源表.列": f"{r.get('source_table', '')}.{r.get('source_column', '')}",
                        "目标数据库": tgt_name if r.get("target_connection_id") != selected_conn_id else "当前库",
                        "目标表.列": f"{r.get('target_table', '')}.{r.get('target_column', '')}",
                        "基数": r.get("cardinality", "one_to_one"),
                        "状态": "✅ 已验证" if r.get("status") == "verified" else "⏳ 待验证",
                    })
                st.dataframe(pd.DataFrame(rel_data), use_container_width=True, hide_index=True)
            else:
                st.warning("当前数据源暂无跨库关联配置")

            # 跳转到跨库关联配置页面
            st.markdown("")
            if st.button("➕ 配置跨库关联", use_container_width=True):
                st.session_state.current_page = "cross_db_relations"
                st.rerun()


# =============================================================================
# 页面：跨库关联配置
# =============================================================================

def render_cross_db_relations_page():
    """跨库关联配置页面"""
    st.title("🌐 跨库关联配置")
    st.caption("配置不同数据库之间的关联关系，才能进行跨库 JOIN 查询")

    # 获取所有连接
    projects_data = api_get("/api/v1/admin/projects/with-connections")
    connections = []
    if isinstance(projects_data, list):
        for p in projects_data:
            connections.extend(p.get("connections", []))

    if len(connections) < 2:
        st.warning("至少需要配置 2 个数据源才能建立跨库关联")
        if st.button("← 返回 Schema 浏览器"):
            st.session_state.current_page = "schema"
            st.rerun()
        return

    tab1, tab2, tab3 = st.tabs(["📋 关联列表", "➕ 新建关联", "📦 数据库分组"])

    # ── Tab 1: 关联列表 ──────────────────────────────────────────────
    with tab1:
        rel_resp = requests.get(
            f"{API_BASE_URL}/api/v1/schema/relations",
            headers=get_headers(),
            timeout=10,
        )
        if rel_resp.status_code == 200:
            relations = rel_resp.json()
        else:
            relations = []
            st.error(f"获取关联列表失败: {rel_resp.text}")

        if relations:
            # 为每个关联查找连接名
            rel_data = []
            for r in relations:
                src_name = get_connection_name(r.get("source_connection_id", ""), connections)
                tgt_name = get_connection_name(r.get("target_connection_id", ""), connections)
                rel_data.append({
                    "id": r.get("id"),
                    "名称": r.get("name", ""),
                    "源库": src_name,
                    "源表": f"{r.get('source_table', '')}.{r.get('source_column', '')}",
                    "目标库": tgt_name,
                    "目标表": f"{r.get('target_table', '')}.{r.get('target_column', '')}",
                    "基数": r.get("cardinality", ""),
                    "描述": r.get("description", ""),
                })

            df = pd.DataFrame(rel_data)
            st.dataframe(
                df.drop(columns=["id"]),
                use_container_width=True,
                hide_index=True,
            )

            # 删除功能
            st.markdown("---")
            with st.expander("🗑️ 删除关联", expanded=False):
                del_id = st.selectbox(
                    "选择要删除的关联",
                    options=[""] + [r.get("id", "") for r in relations],
                    format_func=lambda x: next(
                        (f"{get_connection_name(r['source_connection_id'], connections)} → "
                         f"{get_connection_name(r['target_connection_id'], connections)} "
                         f"({r['source_table']}.{r['source_column']})"
                         for r in relations if r["id"] == x), x
                    ) if x else "",
                    label_visibility="collapsed",
                )
                if del_id and st.button("确认删除", type="secondary"):
                    del_resp = requests.delete(
                        f"{API_BASE_URL}/api/v1/schema/relations/{del_id}",
                        headers=get_headers(),
                        timeout=10,
                    )
                    if del_resp.status_code == 200:
                        st.success("关联已删除")
                        st.rerun()
                    else:
                        st.error(f"删除失败: {del_resp.text}")
        else:
            st.info("暂无跨库关联配置，点击「新建关联」开始配置")

    # ── Tab 2: 新建关联 ─────────────────────────────────────────────
    with tab2:
        st.subheader("新建跨库关联")
        st.warning(
            "⚠️ 跨库关联必须手动配置！LLM 无法自动发现不同数据库之间的表关系。"
        )

        with st.form("new_relation_form"):
            name = st.text_input("关联名称", placeholder="例如：订单-支付关联")

            col1, col2 = st.columns(2)
            with col1:
                st.markdown("**源端（发起方）**")
                src_conn_options = {c["name"]: c["id"] for c in connections}
                src_conn_name = st.selectbox("源数据库", list(src_conn_options.keys()))
                src_conn_id = src_conn_options[src_conn_name]
                src_table = st.text_input("源表名", placeholder="例如：orders")
                src_column = st.text_input("源列名（关联键）", placeholder="例如：order_id")

            with col2:
                st.markdown("**目标端（被引用方）**")
                tgt_conn_options = {c["name"]: c["id"] for c in connections}
                tgt_conn_name = st.selectbox("目标数据库", list(tgt_conn_options.keys()))
                tgt_conn_id = tgt_conn_options[tgt_conn_name]
                tgt_table = st.text_input("目标表名", placeholder="例如：payments")
                tgt_column = st.text_input("目标列名（关联键）", placeholder="例如：order_id")

            cardinality = st.selectbox(
                "基数类型",
                options=["one_to_one", "one_to_many", "many_to_one"],
                format_func=lambda x: {
                    "one_to_one": "1:1（一一对应）",
                    "one_to_many": "1:N（一对多）",
                    "many_to_one": "N:1（多对一）",
                }[x],
            )
            description = st.text_area("关系描述（可选）", placeholder="说明这个关联的业务含义...")

            submitted = st.form_submit_button("💾 保存关联", use_container_width=True)

            if submitted:
                if not name or not src_table or not src_column or not tgt_table or not tgt_column:
                    st.error("请填写所有必填项")
                elif src_conn_id == tgt_conn_id:
                    st.error("源数据库和目标数据库不能相同")
                else:
                    payload = {
                        "name": name,
                        "source_connection_id": src_conn_id,
                        "source_table": src_table,
                        "source_column": src_column,
                        "target_connection_id": tgt_conn_id,
                        "target_table": tgt_table,
                        "target_column": tgt_column,
                        "cardinality": cardinality,
                        "description": description,
                    }
                    resp = requests.post(
                        f"{API_BASE_URL}/api/v1/schema/relations",
                        json=payload,
                        headers=get_headers(),
                        timeout=10,
                    )
                    if resp.status_code == 200:
                        st.success("跨库关联创建成功！现在可以进行跨库查询了")
                        st.rerun()
                    else:
                        st.error(f"创建失败: {resp.text}")

    # ── Tab 3: 数据库分组 ───────────────────────────────────────────
    with tab3:
        st.subheader("数据库分组（同构多库聚合）")
        st.info(
            "数据库分组用于同构多库场景。例如：将杭州、宁波、温州的同构库分到「浙江省子系统」组，"
            "查询时系统会自动向所有组内数据库分发查询并汇总结果。"
        )

        # 获取分组列表
        group_resp = requests.get(
            f"{API_BASE_URL}/api/v1/schema/groups",
            headers=get_headers(),
            timeout=10,
        )
        if group_resp.status_code == 200:
            groups = group_resp.json()
        else:
            groups = []

        if groups:
            for g in groups:
                with st.expander(f"**{g['display_name']}** ({g.get('member_count', 0)} 个成员)"):
                    st.write(f"分组名：{g['name']}")
                    st.write(f"模式：{g['mode']}")
                    st.write(f"描述：{g.get('description', '无')}")

                    # 获取成员
                    member_resp = requests.get(
                        f"{API_BASE_URL}/api/v1/schema/groups/{g['id']}/members",
                        headers=get_headers(),
                        timeout=10,
                    )
                    if member_resp.status_code == 200:
                        members = member_resp.json()
                        if members:
                            for m in members:
                                st.write(f"  - {m.get('connection_name', '')} "
                                        + (f"({m.get('city_code', '')})" if m.get("city_code") else ""))
                        else:
                            st.write("  （暂无成员）")
                    else:
                        st.write("  （获取成员失败）")
        else:
            st.info("暂无数据库分组，点击下方按钮创建第一个分组")

        st.markdown("---")
        with st.expander("➕ 创建数据库分组", expanded=False):
            with st.form("new_group_form"):
                group_name = st.text_input("分组标识（英文，用于代码引用）", placeholder="例如：province_cities")
                group_display = st.text_input("分组显示名（中文）", placeholder="例如：浙江省各地市子系统")
                group_mode = st.selectbox(
                    "分组模式",
                    options=["aggregate", "federated"],
                    format_func=lambda x: {
                        "aggregate": "同构聚合（Schema 完全相同）",
                        "federated": "异构联邦（Schema 不同）",
                    }[x],
                )
                group_desc = st.text_area("描述（可选）")

                if st.form_submit_button("💾 创建分组"):
                    if not group_name or not group_display:
                        st.error("请填写分组标识和显示名")
                    else:
                        resp = requests.post(
                            f"{API_BASE_URL}/api/v1/schema/groups",
                            json={
                                "name": group_name,
                                "display_name": group_display,
                                "mode": group_mode,
                                "description": group_desc,
                            },
                            headers=get_headers(),
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success("分组创建成功！现在可以添加成员了")
                            st.rerun()
                        else:
                            st.error(f"创建失败: {resp.text}")

        # 添加分组成员
        if groups:
            st.markdown("---")
            with st.expander("➕ 向分组添加数据库", expanded=False):
                with st.form("add_member_form"):
                    sel_group = st.selectbox(
                        "选择分组",
                        options=[g["id"] for g in groups],
                        format_func=lambda x: next(g["display_name"] for g in groups if g["id"] == x),
                    )
                    member_conn_options = {c["name"]: c["id"] for c in connections}
                    member_conn_name = st.selectbox("选择数据库", list(member_conn_options.keys()))
                    city_code = st.text_input("编码（可选，用于结果标识）", placeholder="例如：HZ（杭州）")

                    if st.form_submit_button("➕ 添加"):
                        resp = requests.post(
                            f"{API_BASE_URL}/api/v1/schema/groups/{sel_group}/members",
                            json={
                                "connection_id": member_conn_options[member_conn_name],
                                "city_code": city_code if city_code else None,
                            },
                            headers=get_headers(),
                            timeout=10,
                        )
                        if resp.status_code == 200:
                            st.success("成员添加成功！")
                            st.rerun()
                        else:
                            st.error(f"添加失败: {resp.text}")
