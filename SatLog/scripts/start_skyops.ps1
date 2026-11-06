$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$logDir = Join-Path $projectRoot "logs"
$port = 8501

Set-Location -LiteralPath $projectRoot
New-Item -ItemType Directory -Path $logDir -Force | Out-Null
$Host.UI.RawUI.WindowTitle = "SkyOps - Keep this window open"
$env:PYTHONDONTWRITEBYTECODE = "1"

function Test-SkyOpsPython([string]$candidate) {
    if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        return $false
    }
    & $candidate -c "import fastapi, uvicorn, pandas, openpyxl, skyfield, numpy" 2>$null
    return $LASTEXITCODE -eq 0
}

$pythonCandidates = @(
    "D:\Software\Anaconda3\envs\satlog\python.exe",
    "D:\Software\Anaconda3\envs\skyops\python.exe",
    $(if ($env:CONDA_PREFIX) { Join-Path $env:CONDA_PREFIX "python.exe" }),
    $(Join-Path $env:USERPROFILE "anaconda3\envs\satlog\python.exe"),
    $(Join-Path $env:USERPROFILE "anaconda3\envs\skyops\python.exe"),
    $(Join-Path $env:USERPROFILE "miniconda3\envs\satlog\python.exe"),
    $(Join-Path $env:USERPROFILE "miniconda3\envs\skyops\python.exe")
)

$python = $null
foreach ($candidate in $pythonCandidates) {
    if (Test-SkyOpsPython $candidate) {
        $python = $candidate
        break
    }
}

if (-not $python) {
    $pathPython = (Get-Command python.exe -ErrorAction SilentlyContinue).Source
    if (Test-SkyOpsPython $pathPython) {
        $python = $pathPython
    }
}

if (-not $python) {
    Write-Host "A usable SkyOps Python environment was not found." -ForegroundColor Red
    Write-Host "Install requirements.txt into the 'satlog'/'skyops' Conda environment first:"
    Write-Host "  python -m pip install -r requirements.txt"
    Read-Host "Press Enter to close"
    exit 1
}

$existing = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "SkyOps is already running. Opening the browser..." -ForegroundColor Yellow
    Start-Process "http://localhost:$port"
    exit 0
}

$cpolarProcess = $null
$cpolar = (Get-Command cpolar.exe -ErrorAction SilentlyContinue).Source
if (-not $cpolar -and (Test-Path -LiteralPath "D:\Software\cpolar\cpolar.exe")) {
    $cpolar = "D:\Software\cpolar\cpolar.exe"
}

if ($cpolar -and -not (Get-Process -Name cpolar -ErrorAction SilentlyContinue)) {
    try {
        $cpolarProcess = Start-Process -FilePath $cpolar `
            -ArgumentList @("start", "SkyOps") `
            -WindowStyle Hidden -PassThru `
            -RedirectStandardOutput (Join-Path $logDir "cpolar.stdout.log") `
            -RedirectStandardError (Join-Path $logDir "cpolar.stderr.log")
        Write-Host "The configured cpolar SkyOps tunnel has started." -ForegroundColor Green
    }
    catch {
        Write-Warning "cpolar could not start automatically; local access remains available: $($_.Exception.Message)"
    }
}
elseif (-not $cpolar) {
    Write-Warning "cpolar was not found; local and LAN access remain available."
}

Write-Host "Starting SkyOps..." -ForegroundColor Green
Write-Host "Computer: http://localhost:$port"
Write-Host "Phone: use the existing cpolar URL, or the computer LAN IP on port $port."
Write-Host "Keep this window open. Press Ctrl+C or close it to stop SkyOps."

$browserCommand = "Start-Sleep -Seconds 2; Start-Process 'http://localhost:$port'"
$browserCommandBytes = [System.Text.Encoding]::Unicode.GetBytes($browserCommand)
$browserCommandEncoded = [Convert]::ToBase64String($browserCommandBytes)
Start-Process -FilePath "powershell.exe" `
    -ArgumentList @("-NoLogo", "-NoProfile", "-EncodedCommand", $browserCommandEncoded) `
    -WindowStyle Hidden

try {
    & $python -m uvicorn app.main:app `
        --host 0.0.0.0 `
        --port $port `
        --reload `
        --reload-dir app
}
finally {
    if ($cpolarProcess -and -not $cpolarProcess.HasExited) {
        Stop-Process -Id $cpolarProcess.Id -ErrorAction SilentlyContinue
    }
}
