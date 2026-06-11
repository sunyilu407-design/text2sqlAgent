#!/bin/bash
# Micro-GenBI 快速启动脚本 (Linux/macOS)
# 使用方法: ./scripts/start.sh
# 会在后台启动 API 和 React 前端

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="$PROJECT_ROOT/fronted"

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Micro-GenBI 快速启动${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# 检测虚拟环境
if [ -f "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/venv/bin/python"
    echo -e "${GREEN}[VENV] 使用虚拟环境${NC}"
elif [ -f "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON="$PROJECT_ROOT/.venv/bin/python"
    echo -e "${GREEN}[VENV] 使用虚拟环境${NC}"
else
    PYTHON=$(command -v python3 || command -v python)
    echo -e "${YELLOW}[SYS] 使用系统 Python${NC}"
fi

echo -e "${GREEN}  Python: $($PYTHON --version)${NC}"

# 检查后端依赖
echo ""
echo "检查后端依赖..."
if ! $PYTHON -c "import fastapi, uvicorn" 2>/dev/null; then
    echo -e "${YELLOW}  正在安装依赖...${NC}"
    $PYTHON -m pip install -e ".[all]" -q
    if [ $? -ne 0 ]; then
        echo -e "${RED}  依赖安装失败，请手动运行: pip install -e '.[all]'${NC}"
        exit 1
    fi
    echo -e "${GREEN}  依赖安装完成${NC}"
else
    echo -e "${GREEN}  依赖已安装${NC}"
fi

# 检查前端依赖
echo ""
echo "检查前端依赖..."
if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    echo -e "${YELLOW}  正在安装前端依赖...${NC}"
    (cd "$FRONTEND_DIR" && npm install)
    if [ $? -ne 0 ]; then
        echo -e "${RED}  前端依赖安装失败${NC}"
        exit 1
    fi
    echo -e "${GREEN}  前端依赖安装完成${NC}"
else
    echo -e "${GREEN}  前端依赖已安装${NC}"
fi

# 启动 API 服务
echo ""
echo -e "${CYAN}启动 API 服务 (端口 8000)...${NC}"
cd "$PROJECT_ROOT"
$PYTHON -m uvicorn micro_genbi.api.main:app --reload --host 0.0.0.0 --port 8000 > /dev/null 2>&1 &
API_PID=$!
echo "  PID: $API_PID"

# 等待 API 启动
sleep 2

# 启动 React 前端
echo -e "${CYAN}启动 React 前端 (端口 3000)...${NC}"
cd "$FRONTEND_DIR"
npm run dev > /dev/null 2>&1 &
UI_PID=$!
echo "  PID: $UI_PID"

# 提示信息
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  服务已全部启动!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "  ${CYAN}前端界面:${NC}   http://localhost:3000"
echo -e "  ${CYAN}API 文档:${NC}   http://localhost:8000/docs"
echo ""
echo -e "${YELLOW}  停止服务: kill $API_PID $UI_PID${NC}"
echo ""

# 等待用户 Ctrl+C
trap "echo ''; echo -e '${YELLOW}停止服务...${NC}'; kill $API_PID $UI_PID 2>/dev/null; exit 0" SIGINT SIGTERM

wait
