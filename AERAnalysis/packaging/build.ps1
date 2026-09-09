$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m PyInstaller "packaging\aer_analysis.spec" --clean --noconfirm
}
finally {
    Pop-Location
}
