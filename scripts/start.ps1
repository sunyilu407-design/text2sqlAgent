# Micro-GenBI 快速启动脚本 (Windows PowerShell)
# 使用方法: .\scripts\start.ps1

$ErrorActionPreference = "Stop"

Write-Host "========================================" -ForegroundColor Green
Write-Host "  Micro-GenBI 快速启动" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green

# 检查 Python
try {
    $pythonVersion = python --version 2>&1
    Write-Host "✓ Python: $pythonVersion" -ForegroundColor Green
} catch {
    Write-Host "错误: 未找到 Python" -ForegroundColor Red
    Write-Host "请安装 Python 3.11 或更高版本" -ForegroundColor Yellow
    exit 1
}

# 检查依赖
Write-Host ""
Write-Host "检查依赖..." -ForegroundColor Cyan

try {
    python -c "import fastapi" 2>$null
} catch {
    Write-Host "安装依赖中..." -ForegroundColor Yellow
    python -m pip install -e ".[all]" -q
}

Write-Host "✓ 依赖检查完成" -ForegroundColor Green

# 初始化数据库（如果需要）
Write-Host ""
if (-Not (Test-Path "microgenbi.db")) {
    Write-Host "首次运行，初始化数据库..." -ForegroundColor Yellow
    python scripts/init_db.py --all
} else {
    Write-Host "✓ 数据库已存在" -ForegroundColor Green
}

# 启动服务
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "启动服务..." -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "API 服务: http://localhost:8000" -ForegroundColor Cyan
Write-Host "API 文档: http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "用户界面: http://localhost:8501" -ForegroundColor Cyan
Write-Host "管理后台: http://localhost:8502" -ForegroundColor Cyan
Write-Host ""
Write-Host "按 Ctrl+C 停止服务" -ForegroundColor Yellow
Write-Host ""

# 启动 FastAPI
Write-Host "启动 API 服务..." -ForegroundColor Cyan
Start-Process python -ArgumentList "-m uvicorn micro_genbi.api.main:app --reload --port 8000" -WindowStyle Hidden

# 启动 Streamlit 用户界面
Write-Host "启动用户界面..." -ForegroundColor Cyan
Start-Process python -ArgumentList "-m streamlit run src/micro_genbi/ui/user_app.py --server.port 8501 --server.address localhost" -WindowStyle Normal

Write-Host ""
Write-Host "服务已启动!" -ForegroundColor Green
Write-Host "按任意键退出..."
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
