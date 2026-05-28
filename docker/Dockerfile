# =============================================================================
# Micro-GenBI Dockerfile
# =============================================================================

FROM python:3.11-slim

# 防止中文乱码
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

# 设置工作目录
WORKDIR /app

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY pyproject.toml* ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -e .

# 复制应用代码
COPY src/ ./src/
COPY schema.yaml* ./

# 创建非 root 用户
RUN useradd -m -u 1000 microgenbi && \
    chown -R microgenbi:microgenbi /app

USER microgenbi

# 暴露端口
EXPOSE 8000

# 环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["uvicorn", "micro_genbi.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
