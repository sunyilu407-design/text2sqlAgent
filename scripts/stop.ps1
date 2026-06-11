# Micro-GenBI 停止脚本 (Windows PowerShell)
# 使用方法: .\scripts\stop.ps1

Write-Host ""
Write-Host "停止 Micro-GenBI 服务..." -ForegroundColor Yellow
Write-Host ""

# 停止 uvicorn API 服务
$api = Get-Process -Name python -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*uvicorn*" -and $_.CommandLine -like "*8000*"
}
if ($api) {
    Stop-Process -Id $api.Id -Force -ErrorAction SilentlyContinue
    Write-Host "  [x] API 服务已停止" -ForegroundColor Red
} else {
    Write-Host "  [-] API 服务未运行" -ForegroundColor Gray
}

# 停止 React 前端 (node 进程)
$ui = Get-Process -Name node -ErrorAction SilentlyContinue | Where-Object {
    $_.CommandLine -like "*vite*" -or $_.CommandLine -like "*react*"
}
if ($ui) {
    Stop-Process -Id $ui.Id -Force -ErrorAction SilentlyContinue
    Write-Host "  [x] React 前端已停止" -ForegroundColor Red
} else {
    Write-Host "  [-] React 前端未运行" -ForegroundColor Gray
}

Write-Host ""
Write-Host "所有服务已停止" -ForegroundColor Yellow
Write-Host ""
