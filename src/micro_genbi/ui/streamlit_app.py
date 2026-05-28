"""Micro-GenBI 启动器

这是一个启动器，用于选择运行用户端还是管理后台。
"""

import streamlit as st

st.set_page_config(
    page_title="Micro-GenBI",
    page_icon="🔍",
    layout="centered",
)

st.title("🔍 Micro-GenBI")
st.markdown("**企业级 Text2SQL 智能分析平台**")
st.markdown("---")

st.markdown("### 选择您要使用的界面")

col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    ### 👤 用户端

    适用于普通用户，包含：
    - 数据查询
    - LLM 配置
    - 数据源管理
    - API Key
    - Token 消耗
    - 查询历史
    """)
    if st.button("🚀 启动用户端", use_container_width=True):
        st.switch_page("src/micro_genbi/ui/user_app.py")

with col2:
    st.markdown("""
    ### 🔐 系统管理后台

    适用于系统管理员，包含：
    - 用户管理
    - 审计日志
    - 成本统计
    - 系统设置
    """)
    if st.button("🔧 启动管理后台", use_container_width=True):
        st.switch_page("src/micro_genbi/ui/admin_app.py")

st.markdown("---")
st.markdown("""
### 快速链接
- [API 文档](http://localhost:8000/docs) - Swagger UI
- [ReDoc](http://localhost:8000/redoc) - API 参考文档
""")
