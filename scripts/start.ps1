# Micro-GenBI 快速启动脚本 (Windows PowerShell)
# 使用方法: .\scripts\start.ps1
# 每个服务在独立窗口中运行，可单独停止

$ErrorActionPreference = "Continue"

$ProjectRoot = Split-Path -Parent $PSScriptRoot

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Micro-GenBI 快速启动" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检测虚拟环境
$VenvPython = "$ProjectRoot\venv\Scripts\python.exe"

if (Test-Path $VenvPython) {
    $Python = $VenvPython
    Write-Host "[VENV] 使用虚拟环境" -ForegroundColor Green
} else {
    $Python = "python"
    Write-Host "[SYS] 使用系统 Python" -ForegroundColor Yellow
}

# 检查前端依赖
$FrontendDir = "$ProjectRoot\fronted"
$NodeModules = "$FrontendDir\node_modules"

if (-not (Test-Path $NodeModules)) {
    Write-Host ""
    Write-Host "安装前端依赖..." -ForegroundColor Cyan
    Push-Location $FrontendDir
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  前端依赖安装失败" -ForegroundColor Red
        Pop-Location
        exit 1
    }
    Pop-Location
    Write-Host "  前端依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "  前端依赖已安装" -ForegroundColor Green
}

# 检查后端依赖
Write-Host ""
Write-Host "检查后端依赖..." -ForegroundColor Cyan
$depCheck = & $Python -c "import fastapi, uvicorn" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  正在安装依赖..." -ForegroundColor Yellow
    & $Python -m pip install -e ".[all]" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  依赖安装失败，请手动运行: pip install -e '.[all]'" -ForegroundColor Red
        exit 1
    }
    Write-Host "  依赖安装完成" -ForegroundColor Green
} else {
    Write-Host "  依赖已安装" -ForegroundColor Green
}

# 启动 API 服务
Write-Host ""
Write-Host "启动 API 服务 (端口 8000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    Write-Host ''
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host '  Micro-GenBI API 服务' -ForegroundColor Cyan
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host '  API 文档: http://localhost:8000/docs' -ForegroundColor White
    Write-Host ''
    Write-Host '  按 Ctrl+C 停止服务' -ForegroundColor Yellow
    Write-Host ''
    Set-Location '$ProjectRoot'
    & '$Python' -m uvicorn micro_genbi.api.main:app --reload --host 0.0.0.0 --port 8000
"

Start-Sleep -Seconds 2

# 启动 React 前端
Write-Host "启动前端 (端口 3000)..." -ForegroundColor Cyan
Start-Process powershell -ArgumentList "-NoExit", "-Command", "
    Write-Host ''
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host '  Micro-GenBI React 前端' -ForegroundColor Cyan
    Write-Host '========================================' -ForegroundColor Cyan
    Write-Host '  用户界面: http://localhost:3000' -ForegroundColor White
    Write-Host '  (开发模式，API 代理到 localhost:8000)' -ForegroundColor White
    Write-Host ''
    Write-Host '  按 Ctrl+C 停止服务' -ForegroundColor Yellow
    Write-Host ''
    Set-Location '$FrontendDir'
    npm run dev
"

# 提示信息
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  服务已全部启动!" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  前端界面: http://localhost:3000" -ForegroundColor White
Write-Host "  API 文档:  http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "  停止服务: 在各窗口中按 Ctrl+C，或运行 .\scripts\stop.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  关闭窗口即可停止对应服务" -ForegroundColor Gray
Write-Host ""
