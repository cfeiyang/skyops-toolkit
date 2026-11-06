$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    python -m PyInstaller "packaging\stk_simulation.spec" --clean --noconfirm
}
finally {
    Pop-Location
}

