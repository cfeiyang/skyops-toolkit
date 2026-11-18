from pathlib import Path
from PyInstaller.utils.hooks import collect_all, collect_data_files

project_root = Path(SPEC).resolve().parents[1]
source_root = project_root / "src"
app_icon = source_root / "stk_simulation" / "assets" / "app_icon.ico"

datas = []
binaries = []
hiddenimports = ["scipy.spatial.transform._rotation_groups", "skyfield", "sgp4"]

try:
    stk_datas, stk_binaries, stk_hiddenimports = collect_all("agi.stk12")
    datas += list(stk_datas)
    binaries += list(stk_binaries)
    hiddenimports += list(stk_hiddenimports)
except Exception:
    print("[打包提示] 当前环境未检测到 agi.stk12，将仅打包纯 Python 引擎支持。")

for pkg in ("mpl_toolkits.basemap_data", "skyfield", "sgp4"):
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

datas.append((str(app_icon), "stk_simulation/assets"))
datas.append((str(app_icon.with_name("world.json")), "stk_simulation/assets"))

a = Analysis(
    [str(source_root / "stk_simulation" / "__main__.py")],
    pathex=[str(source_root)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
# Qt 使用 Windows ICU 的入口，避免打包 Conda 环境中的同名库。
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() != "icuuc.dll"
              and not Path(entry[0]).name.lower().startswith("icudt")]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="SkyOpsSim",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    icon=str(app_icon),
)
