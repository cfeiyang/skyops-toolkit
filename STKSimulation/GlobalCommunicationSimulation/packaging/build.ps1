$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot

# 优先使用 conda 的 stk 环境（含 PySide6/matplotlib/basemap），找不到再退回系统 python
$py = "D:\Software\Anaconda3\envs\stk\python.exe"
if (-not (Test-Path $py)) { $py = "python" }

function Test-PythonModule([string]$name) {
    & $py -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('$name') else 1)" 2>$null
    return ($LASTEXITCODE -eq 0)
}

Write-Host ("[依赖检查] 使用 Python: " + $py) -ForegroundColor Cyan
Write-Host "[依赖检查] 正在检查打包所需模块..." -ForegroundColor Cyan
$required = @(
    "numpy", "pandas", "scipy", "matplotlib", "PySide6",
    "mpl_toolkits.basemap", "skyfield", "sgp4", "PyInstaller"
)
$missing = @()
foreach ($module in $required) {
    if (-not (Test-PythonModule $module)) { $missing += $module }
}
if ($missing.Count -gt 0) {
    Write-Host ("[依赖检查] 缺少: " + ($missing -join ", ")) -ForegroundColor Yellow
    Write-Host "[依赖检查] 正在通过 pip 安装..." -ForegroundColor Yellow
    & $py -m pip install numpy "scipy<2.0" matplotlib "PySide6>=6.5,<7.0" basemap skyfield sgp4 pyinstaller
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[依赖检查] 安装失败，请检查网络或 Python 环境后重试。" -ForegroundColor Red
        exit 1
    }
}
Write-Host "[依赖检查] 全部就绪。" -ForegroundColor Green
Write-Host "[打包提示] 未安装 STK COM API (agi.stk12) 时，打包过程会自动降级为纯 Python 引擎版本。" -ForegroundColor DarkGray

Push-Location $projectRoot
try {
    & $py -m PyInstaller "packaging\stk_simulation.spec" --clean --noconfirm
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 打包失败。" }
    Write-Host ("[打包完成] " + (Join-Path $projectRoot "dist\SkyOpsSim.exe")) -ForegroundColor Green
}
finally {
    Pop-Location
}
