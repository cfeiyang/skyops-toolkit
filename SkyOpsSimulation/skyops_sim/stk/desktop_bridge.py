"""保持一个 Windows COM 会话，用同一 STK 实例计算、保存和导出。"""

import base64
from contextlib import suppress
import json
import os
from pathlib import Path
import subprocess
import sys

from skyops_sim.stk.link_commands import file_command

# Each request is data only. Connect commands are sent to STK, never evaluated by PowerShell.
SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$root = $null
$owned = $null
$token = ''
$accesses = @()

function Values($result, $name) {
    if ($result.DataSets.Count -gt 0) {
        $result.DataSets.GetDataSetByName($name).GetValues()
    }
}

while ($null -ne ($line = [Console]::ReadLine())) {
    $reply = @{}
    try {
        $request = $line | ConvertFrom-Json
        if ($request.action -eq 'connect') {
            if ($null -ne $root) {
                try { $null = $root.CurrentScenario } catch { $root = $null }
            }
            if ($null -eq $root) {
                $progId = 'STK12.Application'
                if ($null -eq [type]::GetTypeFromProgID($progId)) {
                    throw '此电脑未注册 STK 12 Desktop。请安装 STK 12，或选择 Python 引擎。'
                }
                try {
                    if ($request.mode -eq 'running') {
                        $app = [Runtime.InteropServices.Marshal]::GetActiveObject($progId)
                    } else {
                        $app = New-Object -ComObject $progId
                        $app.UserControl = $true
                        $app.Visible = $true
                    }
                    $root = $app.Personality2
                    if ($null -eq $root -and $request.mode -eq 'new') {
                        $app.LoadPersonality('STK')
                        $root = $app.Personality2
                    }
                } catch {
                    throw "无法连接 STK 12。请先正常打开 STK，再选择「连接已运行的 STK」。`n$($_.Exception.Message)"
                }
            }
            $reply.scenario = [string]$root.CurrentScenario.InstanceName
        } elseif ($request.action -eq 'prepare') {
            if ($null -ne $root.CurrentScenario) {
                throw "STK 已打开场景「$($root.CurrentScenario.InstanceName)」。请先在 STK 中保存并关闭该场景，再计算建链。"
            }
            try {
                foreach ($command in $request.commands) {
                    try { $null = $root.ExecuteCommand($command) }
                    catch { throw "STK 命令执行失败：$command`n$($_.Exception.Message)" }
                }
            } catch {
                if ([string]$root.CurrentScenario.InstanceName -eq $request.scenario) {
                    $null = $root.CloseScenario()
                }
                throw
            }
            $owned = $root.CurrentScenario
            $token = $request.scenario
            $units = $root.UnitPreferences
            $null = $units.Item('AngleUnit').SetCurrentUnit('deg')
            $null = $units.Item('DistanceUnit').SetCurrentUnit('km')
            $null = $units.Item('TimeUnit').SetCurrentUnit('sec')
            $null = $units.Item('DateFormat').SetCurrentUnit('UTCG')
            $null = $root.Rewind()
            $sat = $root.GetObjectFromPath($request.satellite)
            $accesses = @()
            $reply.intervals = @(
                foreach ($station in $request.facilities) {
                    $fac = $root.GetObjectFromPath($station)
                    $access = $fac.GetAccessToObject($sat)
                    $null = $access.ComputeAccess()
                    $accesses += ,$access
                    if ($access.ComputedAccessIntervalTimes.Count -eq 0) {
                        @{ starts = @(); stops = @() }
                    } else {
                        $result = $access.DataProviders.Item('Access Data').Exec($owned.StartTime, $owned.StopTime)
                        @{ starts = @(Values $result 'Start Time'); stops = @(Values $result 'Stop Time') }
                    }
                }
            )
        } else {
            $current = $root.CurrentScenario
            if ($null -eq $current -or $token -ne $request.scenario -or
                -not [object]::ReferenceEquals($owned, $current)) {
                throw 'STK 中已切换或关闭本次建链场景。请重新计算建链。'
            }
            if ($request.action -eq 'sample') {
                $reply.samples = @(
                    foreach ($item in $request.windows) {
                        $provider = $accesses[[int]$item.station].DataProviders.Item('AER Data').Group.Item('Default')
                        $result = $provider.Exec($item.start, $item.stop, [double]$request.step)
                        @{
                            time = @(Values $result 'Time')
                            azimuth = @(Values $result 'Azimuth')
                            elevation = @(Values $result 'Elevation')
                            range = @(Values $result 'Range')
                        }
                    }
                )
            } elseif ($request.action -eq 'file') {
                if (Test-Path -LiteralPath $request.destination) { throw '目标文件已存在，请选择新文件名。' }
                $null = $root.ExecuteCommand($request.command)
                if (-not (Test-Path -LiteralPath $request.destination -PathType Leaf)) {
                    throw 'STK 未在所选路径生成文件，请检查 STK 消息窗口。'
                }
            } else {
                throw '不支持的 STK 操作。'
            }
        }
    } catch {
        $reply = @{ error = $_.Exception.Message }
    }
    [Console]::WriteLine(($reply | ConvertTo-Json -Compress -Depth 7))
}
"""


class STKDesktopBridge:
    def __init__(self) -> None:
        self._process = None
        self._mode = ""
        self.satellite_name = ""

    def connect(self, mode: str) -> str:
        if mode not in ("new", "running"):
            raise ValueError("请选择 STK 会话方式。")
        if self._process is None or self._process.poll() is not None or mode != self._mode:
            self.close()
            ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
            encoded = base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii")
            self._process = _open_powershell(ps, encoded)
            self._mode = mode
        return self.request("connect", mode=mode)["scenario"]

    def request(self, action: str, **parameters):
        process = self._process
        if process is None or process.poll() is not None:
            raise RuntimeError("STK 会话已结束，请重新计算建链。")
        try:
            process.stdin.write(json.dumps({"action": action, **parameters}, ensure_ascii=False) + "\n")
            process.stdin.flush()
            reply = json.loads(process.stdout.readline().lstrip("\ufeff"))
        except (OSError, ValueError) as error:
            self.close()
            raise RuntimeError("STK 自动化进程未返回有效结果，请重新连接。") from error
        if reply.get("error"):
            raise RuntimeError(reply["error"])
        return reply

    def write_file(self, action: str, path: str, scenario: str) -> None:
        command = file_command(action, self.satellite_name, path)
        self.request("file", scenario=scenario, command=command, destination=path)

    def close(self) -> None:
        process, self._process = self._process, None
        if process is not None:
            try:
                with suppress(OSError):
                    process.stdin.close()
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            finally:
                process.stdout.close()


def _open_powershell(executable: Path, encoded: str):
    args = [str(executable), "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", encoded]
    options = dict(
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW,
    )
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return subprocess.Popen(args, **options)

    # External programs use Windows DLLs rather than the application's bundled copies.
    import ctypes
    from ctypes import wintypes

    bundle_path = Path(os.path.abspath(bundle))
    env = os.environ.copy()
    env["PATH"] = os.pathsep.join(
        entry for entry in env.get("PATH", "").split(os.pathsep)
        if entry and not Path(os.path.abspath(entry.strip('"'))).is_relative_to(bundle_path)
    )
    set_dll_directory = ctypes.WinDLL("kernel32", use_last_error=True).SetDllDirectoryW
    set_dll_directory.argtypes = [wintypes.LPCWSTR]
    set_dll_directory.restype = wintypes.BOOL
    if not set_dll_directory(None):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return subprocess.Popen(args, env=env, **options)
    finally:
        set_dll_directory(bundle)
