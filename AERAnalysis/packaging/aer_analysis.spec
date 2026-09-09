from pathlib import Path

from PyInstaller.utils.hooks import collect_all


project_root = Path(SPEC).resolve().parents[1]
source_root = project_root / "src"
app_icon = source_root / "stk_aer_analysis" / "assets" / "app_icon.ico"

stk_datas, stk_binaries, stk_hiddenimports = collect_all("agi.stk12")
datas = list(stk_datas)
datas.append((str(app_icon), "stk_aer_analysis/assets"))

a = Analysis(
    [str(source_root / "stk_aer_analysis" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=stk_binaries,
    datas=datas,
    hiddenimports=stk_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AERAnalysis",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(app_icon),
)
