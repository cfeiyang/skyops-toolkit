# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

project = Path(SPECPATH)
icon = project / "workbench.ico"
analysis = Analysis(
    [str(project / "main.py")],
    pathex=[str(project)],
    datas=[(str(icon), ".")],
)

# The Windows PySide6 wheel uses Windows' built-in ICU C interface.
# PyInstaller can collect Conda's same-named DLL, which exports versioned
# names instead. Keep Windows as the provider of ICU for this application.
analysis.binaries = [
    entry for entry in analysis.binaries
    if Path(entry[0]).name.lower() != "icuuc.dll"
    and not Path(entry[0]).name.lower().startswith("icudt")
]

exe = EXE(
    PYZ(analysis.pure),
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name="STK12Workbench",
    console=False,
    upx=False,
    icon=str(icon),
)
