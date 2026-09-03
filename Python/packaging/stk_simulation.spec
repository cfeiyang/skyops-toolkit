from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files


project_root = Path(SPEC).resolve().parents[1]
source_root = project_root / "src"

stk_datas, stk_binaries, stk_hiddenimports = collect_all("agi.stk12")
datas = list(stk_datas)
datas += collect_data_files("mpl_toolkits.basemap_data")

a = Analysis(
    [str(source_root / "stk_simulation" / "__main__.py")],
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
    name="STKSimulation",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)

