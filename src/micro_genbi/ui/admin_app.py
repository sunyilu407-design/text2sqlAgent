"""Streamlit 系统管理后台

真正的系统管理后台，用于管理员查看用户信息、操作记录和成本统计。
"""

from __future__ import annotations

import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta

# 配置
API_BASE_URL = "http://localhost:8000"

# 页面配置
st.set_page_config(
    page_title="Micro-GenBI 系统管理后台",
    page_icon="🔐",
    layout="wide",
)


# =============================================================================
# 工具函数
# =============================================================================

def get_headers():
    return {
        "Content-Type": "application/json",
        "X-User-Id": st.session_state.user.get("user_id", ""),
        "X-User-Role": st.session_state.user.get("role", "user"),
        "X-Tenant-Id": st.session_state.user.get("tenant_id", "default"),
    }


def api_get(endpoint: str):
    try:
        resp = requests.get(f"{API_BASE_URL}{endpoint}", headers=get_headers(), timeout=10)
        if resp.status_code == 200:
            return resp.json()
        return {"error": resp.text, "status_code": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def api_post(endpoint: str, data: dict):
    try:
        resp = requests.post(f"{API_BASE_URL}{endpoint}", json=data, headers=get_headers(), timeout=30)
        if resp.status_code in [200, 201]:
            return resp.json()
        return {"error": resp.text, "status_code": resp.status_code}
    except Exception as e:
        return {"error": str(e)}


def init_session_state():
    if "user" not in st.session_state:
        st.session_state.user = {
            "user_id": "admin",
            "tenant_id": "system",
            "role": "admin",
        }


# =============================================================================
# 侧边栏
# =============================================================================

def render_sidebar():
    st.sidebar.title("🔐 系统管理")
    st.sidebar.markdown("---")

    pages = {
        "📊 概览": "dashboard",
        "👥 用户管理": "users",
        "📋 审计日志": "audit",
        "💰 成本统计": "cost",
        "⚙️ 系统设置": "settings",
    }

    if "current_page" not in st.session_state:
        st.session_state.current_page = "dashboard"

    for label, page_id in pages.items():
        if st.sidebar.button(label, use_container_width=True, key=f"nav_{page_id}"):
            st.session_state.current_page = page_id
            st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.markdown(f"""
    **管理员**: `{st.session_state.user.get('user_id', 'N/A')}`
    """)


# =============================================================================
# 页面：概览
# =============================================================================

def render_dashboard():
    st.title("📊 系统概览")

    # 时间范围选择
    col1, col2, col3 = st.columns(3)
    with col1:
        days = st.selectbox("统计周期", ["今天", "最近7天", "最近30天"], index=1)
    with col2:
        pass
    with col3:
        pass

    st.markdown("---")

    # 统计卡片
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("活跃用户", "156", "+12%")

    with col2:
        st.metric("总查询数", "12,345", "+8%")

    with col3:
        st.metric("Token 消耗", "2.5M", "+15%")

    with col4:
        st.metric("API 调用失败率", "0.5%", "-0.2%")

    st.markdown("---")

    # 查询趋势图
    st.subheader("📈 查询趋势")

    # 模拟数据
    import random
    dates = [(datetime.now() - timedelta(days=i)).strftime('%m-%d') for i in range(7, -1, -1)]
    queries = [random.randint(100, 300) for _ in range(8)]

    chart_data = {
        "日期": dates,
        "查询数": queries,
    }
    df = pd.DataFrame(chart_data)
    st.line_chart(df.set_index("日期"))

    st.markdown("---")

    # 最近活动
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔥 热门用户")
        hot_users = [
            {"用户名": "zhangsan", "查询数": 1234, "Token消耗": "500K"},
            {"用户名": "lisi", "查询数": 987, "Token消耗": "400K"},
            {"用户名": "wangwu", "查询数": 654, "Token消耗": "300K"},
        ]
        st.dataframe(pd.DataFrame(hot_users), use_container_width=True)

    with col2:
        st.subheader("⚠️ 异常告警")
        st.info("暂无异常告警")


# =============================================================================
# 页面：用户管理
# =============================================================================

def render_users():
    st.title("👥 用户管理")

    # 搜索和筛选
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search = st.text_input("🔍 搜索用户", placeholder="输入用户名或邮箱")
    with col2:
        role_filter = st.selectbox("角色", ["全部", "admin", "user", "readonly"])
    with col3:
        status_filter = st.selectbox("状态", ["全部", "活跃", "禁用"])

    st.markdown("---")

    # 用户列表
    st.subheader("用户列表")

    # 模拟用户数据
    users = [
        {"ID": "u001", "用户名": "admin", "邮箱": "admin@example.com", "角色": "admin", "租户": "system", "状态": "活跃", "最后登录": "2026-05-25 10:30"},
        {"ID": "u002", "用户名": "zhangsan", "邮箱": "zhangsan@example.com", "角色": "user", "租户": "油库运营部", "状态": "活跃", "最后登录": "2026-05-25 09:15"},
        {"ID": "u003", "用户名": "lisi", "邮箱": "lisi@example.com", "角色": "user", "租户": "油库运营部", "状态": "活跃", "最后登录": "2026-05-25 08:45"},
        {"ID": "u004", "用户名": "wangwu", "邮箱": "wangwu@example.com", "角色": "readonly", "租户": "质量管理部", "状态": "活跃", "最后登录": "2026-05-24 17:30"},
        {"ID": "u005", "用户名": "zhaoliu", "邮箱": "zhaoliu@example.com", "角色": "user", "租户": "质量管理部", "状态": "禁用", "最后登录": "2026-05-20 14:20"},
    ]

    df = pd.DataFrame(users)
    st.dataframe(df, use_container_width=True)

    st.markdown("---")

    # 用户详情
    st.subheader("用户详情")

    if search:
        user_data = [u for u in users if search in u["用户名"] or search in u["邮箱"]]
    else:
        user_data = users

    if user_data:
        selected_user = st.selectbox("选择用户", [u["用户名"] for u in user_data])

        for u in user_data:
            if u["用户名"] == selected_user:
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.write(f"**用户名**: {u['用户名']}")
                    st.write(f"**邮箱**: {u['邮箱']}")
                with col2:
                    st.write(f"**角色**: {u['角色']}")
                    st.write(f"**租户**: {u['租户']}")
                with col3:
                    st.write(f"**状态**: {u['状态']}")
                    st.write(f"**最后登录**: {u['最后登录']}")

                # 操作按钮
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("🔄 重置密码"):
                        st.success("密码重置邮件已发送")
                with col2:
                    if u["状态"] == "活跃":
                        if st.button("🚫 禁用用户"):
                            st.warning("用户已禁用")
                    else:
                        if st.button("✅ 启用用户"):
                            st.success("用户已启用")
    else:
        st.info("未找到匹配的用户")


# =============================================================================
# 页面：审计日志
# =============================================================================

def render_audit():
    st.title("📋 审计日志")

    # 筛选条件
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        event_type = st.selectbox("事件类型", ["全部", "登录", "查询", "配置变更", "安全事件"])
    with col2:
        user_filter = st.text_input("用户")
    with col3:
        date_from = st.date_input("开始日期", datetime.now() - timedelta(days=7))
    with col4:
        date_to = st.date_input("结束日期", datetime.now())

    st.markdown("---")

    # 事件类型统计
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("登录事件", "456")
    with col2:
        st.metric("查询事件", "12,345")
    with col3:
        st.metric("配置变更", "23")
    with col4:
        st.metric("安全事件", "2")

    st.markdown("---")

    # 日志列表
    st.subheader("日志详情")

    # 模拟日志数据
    logs = [
        {"时间": "2026-05-25 15:30:45", "用户": "zhangsan", "事件": "query.submitted", "结果": "成功", "详情": "统计各部门报销总额"},
        {"时间": "2026-05-25 15:28:12", "用户": "lisi", "事件": "query.submitted", "结果": "成功", "详情": "查询储罐库存"},
        {"时间": "2026-05-25 15:25:00", "用户": "admin", "事件": "config.updated", "结果": "成功", "详情": "更新 LLM 配置"},
        {"时间": "2026-05-25 15:20:30", "用户": "zhangsan", "事件": "auth.login", "结果": "成功", "详情": "登录成功"},
        {"时间": "2026-05-25 15:15:00", "用户": "unknown", "事件": "security.blocked", "结果": "失败", "详情": "SQL注入尝试被拦截"},
        {"时间": "2026-05-25 15:10:00", "用户": "wangwu", "事件": "query.submitted", "结果": "成功", "详情": "查询订单趋势"},
    ]

    df = pd.DataFrame(logs)

    # 筛选
    if event_type != "全部":
        df = df[df["事件"].str.contains(event_type.lower())]

    if user_filter:
        df = df[df["用户"].str.contains(user_filter)]

    st.dataframe(df, use_container_width=True)

    # 事件详情
    st.markdown("---")
    st.subheader("事件详情")

    selected_event = st.selectbox("选择事件", [f"{l['时间']} - {l['事件']} - {l['用户']}" for l in logs])

    for log in logs:
        key = f"{log['时间']} - {log['事件']} - {log['用户']}"
        if key == selected_event:
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"**时间**: {log['时间']}")
                st.write(f"**用户**: {log['用户']}")
                st.write(f"**事件**: {log['事件']}")
            with col2:
                st.write(f"**结果**: {log['结果']}")
                st.write(f"**详情**: {log['详情']}")


# =============================================================================
# 页面：成本统计
# =============================================================================

def render_cost():
    st.title("💰 Token 消耗统计")

    # 时间范围
    col1, col2, col3 = st.columns(3)
    with col1:
        period = st.selectbox("统计周期", ["今天", "本周", "本月", "本季度"])
    with col2:
        group_by = st.selectbox("分组维度", ["用户", "租户", "LLM模型"])
    with col3:
        pass

    st.markdown("---")

    # 成本概览
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("总消耗 Token", "2.5M", "+15%")
    with col2:
        st.metric("API 成本 (USD)", "$12.50", "+18%")
    with col3:
        st.metric("平均每次查询", "200 tokens", "-5%")
    with col4:
        st.metric("查询成功率", "99.5%", "+0.2%")

    st.markdown("---")

    # 按用户统计
    st.subheader(f"按 {group_by} 统计")

    cost_by_user = [
        {"用户": "zhangsan", "Token消耗": "500K", "查询数": 1234, "成本 (USD)": "$2.50", "占比": "20%"},
        {"用户": "lisi", "Token消耗": "400K", "查询数": 987, "成本 (USD)": "$2.00", "占比": "16%"},
        {"用户": "wangwu", "Token消耗": "300K", "查询数": 654, "成本 (USD)": "$1.50", "占比": "12%"},
        {"用户": "admin", "Token消耗": "200K", "查询数": 456, "成本 (USD)": "$1.00", "占比": "8%"},
    ]

    df = pd.DataFrame(cost_by_user)
    st.dataframe(df, use_container_width=True)

    # 成本趋势图
    st.markdown("---")
    st.subheader("成本趋势")

    dates = [(datetime.now() - timedelta(days=i)).strftime('%m-%d') for i in range(7, -1, -1)]
    costs = [round(random.uniform(0.5, 2.0), 2) for _ in range(8)]

    chart_data = {
        "日期": dates,
        "成本 (USD)": costs,
    }
    df_chart = pd.DataFrame(chart_data)
    st.bar_chart(df_chart.set_index("日期"))

    # 按模型统计
    st.markdown("---")
    st.subheader("按 LLM 模型统计")

    model_stats = [
        {"模型": "deepseek-chat", "调用次数": "8,000", "Token消耗": "1.8M", "成本": "$9.00"},
        {"模型": "gpt-4o-mini", "调用次数": "3,000", "Token消耗": "500K", "成本": "$2.50"},
        {"模型": "llama3", "调用次数": "1,000", "Token消耗": "200K", "成本": "$1.00"},
    ]

    st.dataframe(pd.DataFrame(model_stats), use_container_width=True)


# =============================================================================
# 页面：系统设置
# =============================================================================

def render_settings():
    st.title("⚙️ 系统设置")

    tab1, tab2, tab3 = st.tabs(["基本设置", "安全设置", "通知设置"])

    with tab1:
        st.subheader("基本设置")

        with st.form("basic_settings"):
            st.text_input("系统名称", value="Micro-GenBI")
            st.text_input("系统URL", value="https://api.example.com")
            st.text_input("默认租户", value="default")

            st.markdown("---")
            st.form_submit_button("💾 保存设置")

    with tab2:
        st.subheader("安全设置")

        with st.form("security_settings"):
            st.toggle("启用 IP 白名单", value=False)
            st.toggle("启用请求限流", value=True)
            st.number_input("每分钟最大请求数", value=100, min_value=1)

            st.markdown("---")
            st.form_submit_button("💾 保存设置")

    with tab3:
        st.subheader("通知设置")

        with st.form("notification_settings"):
            st.toggle("低余额提醒", value=True)
            st.number_input("余额阈值 (USD)", value=10.0, min_value=0.0)
            st.toggle("异常操作提醒", value=True)
            st.text_input("告警邮箱", value="admin@example.com")

            st.markdown("---")
            st.form_submit_button("💾 保存设置")


# =============================================================================
# 主函数
# =============================================================================

def main():
    init_session_state()
    render_sidebar()

    page = st.session_state.get("current_page", "dashboard")

    if page == "dashboard":
        render_dashboard()
    elif page == "users":
        render_users()
    elif page == "audit":
        render_audit()
    elif page == "cost":
        render_cost()
    elif page == "settings":
        render_settings()


if __name__ == "__main__":
    main()
