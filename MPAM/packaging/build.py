"""在 SkyOps 环境构建月度项目分配 Windows 程序。"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"


def build() -> Path:
    output = ROOT.parent / "dist"
    output.mkdir(exist_ok=True)
    script = ROOT / "main.py"
    icon = ASSETS / "allocation.ico"
    data = [(str(ASSETS / name), "assets") for name in ("allocation.ico", "Lucide-LICENSE.txt", "style.qss")]
    name = "MonthlyAllocation"
    deliverable = output / "月度项目分配.exe"

    with TemporaryDirectory(prefix=".skyops-build-", dir=output) as directory:
        staging = Path(directory)
        os.environ["PYINSTALLER_CONFIG_DIR"] = str(staging / "cache")
        from PyInstaller.__main__ import run

        spec = staging / f"{name}.spec"
        spec.write_text(f"""from pathlib import Path

a = Analysis([{str(script)!r}], pathex=[{str(ROOT)!r}], datas={data!r}, excludes=['numpy'])
# Qt's wheel uses Windows' ICU entry points. Conda's same-name DLL exports versioned symbols.
a.binaries = [entry for entry in a.binaries
              if Path(entry[0]).name.lower() != 'icuuc.dll'
              and not Path(entry[0]).name.lower().startswith('icudt')]
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name={name!r}, console=False,
          icon={str(icon)!r}, upx=False)
""", encoding="utf-8")
        run(["--noconfirm", "--distpath", str(staging), "--workpath", str(staging / "work"), str(spec)])
        os.replace(staging / f"{name}.exe", deliverable)
    return deliverable


if __name__ == "__main__":
    print(f"已生成 {build()}")
