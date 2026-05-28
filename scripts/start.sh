#!/bin/bash
# Micro-GenBI 启动脚本

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Micro-GenBI 快速启动${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查 Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo -e "${RED}错误: 未找到 Python${NC}"
    echo "请安装 Python 3.11 或更高版本"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)
echo -e "${GREEN}✓${NC} 使用 Python: $($PYTHON --version)"

# 检查依赖
echo ""
echo "检查依赖..."
if ! $PYTHON -c "import fastapi" 2>/dev/null; then
    echo -e "${YELLOW}安装依赖...${NC}"
    $PYTHON -m pip install -e ".[all]" -q
fi

echo -e "${GREEN}✓${NC} 依赖检查完成"

# 初始化数据库（如果需要）
echo ""
if [ ! -f "microgenbi.db" ]; then
    echo -e "${YELLOW}首次运行，初始化数据库...${NC}"
    $PYTHON scripts/init_db.py --all
else
    echo -e "${GREEN}✓${NC} 数据库已存在"
fi

# 启动服务
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}启动服务...${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "API 服务: http://localhost:8000"
echo "API 文档: http://localhost:8000/docs"
echo "用户界面: http://localhost:8501"
echo "管理后台: http://localhost:8502"
echo ""
echo "按 Ctrl+C 停止服务"
echo ""

# 启动 FastAPI
$PYTHON -m uvicorn micro_genbi.api.main:app --reload --port 8000 &
API_PID=$!

# 等待一下
sleep 2

# 启动 Streamlit 用户界面
$PYTHON -m streamlit run src/micro_genbi/ui/user_app.py --server.port 8501 --server.address localhost &
ST_PID=$!

# 等待 Ctrl+C
wait
