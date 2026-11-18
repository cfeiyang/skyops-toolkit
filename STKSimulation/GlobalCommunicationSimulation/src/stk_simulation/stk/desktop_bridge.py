"""Run STK Desktop automation through Windows PowerShell and report each command."""

from pathlib import Path
import base64
import json
import os
import subprocess
import sys

# The command text travels as JSON over stdin. It is never evaluated as PowerShell.
SCRIPT = r"""
$ErrorActionPreference = 'Stop'
[Console]::InputEncoding = [Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$reply = @{version=''; scenario=''; satellites=@(); stations=@(); records=@(); error=''}
$progId = 'STK12.Application'

function Read-Result($result) {
    if ($null -ne $result) {
        for ($i = 0; $i -lt $result.Count; $i++) {
            [string]$result.Item($i)
        }
    }
}

try {
    $request = [Console]::In.ReadToEnd() | ConvertFrom-Json
    if ($null -eq [type]::GetTypeFromProgID($progId)) {
        throw '此电脑没有注册 STK 12 Desktop（STK12.Application）。请在装有 STK 12 Desktop 的电脑上连接。'
    }
    try {
        $app = [Runtime.InteropServices.Marshal]::GetActiveObject($progId)
    } catch {
        $cause = $_.Exception.GetBaseException()
        $code = '{0:X8}' -f $cause.HResult
        if ($code -notin @('800401E3', '800401E5')) {
            throw ("查找已运行的 STK 12 失败（0x{0}）。{1}" -f $code, $cause.Message)
        }
        throw '未找到可连接的 STK 12。请从开始菜单正常打开 STK 12，等主界面加载完，再点击「连接 STK」。请让两个程序使用相同的 Windows 用户和权限级别。'
    }
    try {
        $root = $app.Personality2
        $reply.version = @(Read-Result ($root.ExecuteCommand('GetSTKVersion /'))) -join ' '
        $current = $root.CurrentScenario
    } catch {
        throw "已经找到 STK 12，但读取其自动化接口失败。请确认 STK 主界面已加载并关闭启动提示。`n`n原始错误：$($_.Exception.Message)"
    }
    if ($null -ne $current) {
        $reply.scenario = [string]$current.InstanceName
    }
    if ($request.action -eq 'run') {
        if ($request.requires_scenario -and $null -eq $current) {
            throw 'STK 当前没有打开场景。请先创建或打开场景。'
        }
        if ($request.expected_scenario -and $reply.scenario -ne $request.expected_scenario) {
            throw 'STK 中的活动场景已切换。请核对窗口顶部显示的场景后再执行。'
        }
        foreach ($cmd in $request.commands) {
            try {
                if ($cmd -match '^(?:New\s+/\s+Scenario\b|Load\s+/\s+(?:Scenario(?:/\S*)?|VDF)\s)') {
                    if ($null -ne $root.CurrentScenario) {
                        throw 'STK 已有打开的场景。请先在 STK 中保存并关掉它，再新建或打开另一个场景。'
                    }
                }
                $response = @(Read-Result ($root.ExecuteCommand($cmd)))
                $reply.records += @{command=$cmd; output=$response; ok=$true}
            } catch {
                $reply.records += @{command=$cmd; output=@($_.Exception.Message); ok=$false}
                $reply.error = '已在出错命令处停止。前面成功的步骤已应用。'
                break
            }
        }
    }
    $current = $root.CurrentScenario
    $reply.scenario = ''
    if ($null -ne $current) {
        $reply.scenario = [string]$current.InstanceName
        $children = $current.Children
        for ($i = 0; $i -lt $children.Count; $i++) {
            $obj = $children.Item($i)
            switch ($obj.ClassName) {
                'Satellite' { $reply.satellites += [string]$obj.InstanceName }
                'Facility' { $reply.stations += [string]$obj.InstanceName }
            }
        }
    }
} catch {
    $reply.error = $_.Exception.Message
}
[Console]::WriteLine(($reply | ConvertTo-Json -Compress -Depth 6))
"""


def invoke(action, plan=None, expected_scenario=""):
    if plan:
        for value in plan.inputs:
            if not Path(value).is_file():
                raise ValueError(f"STK 所在电脑上找不到输入文件：{value}")
        for value in plan.outputs:
            output = Path(value)
            if not output.parent.is_dir():
                raise ValueError(f"导出目录不存在：{output.parent}")
            if output.exists():
                raise ValueError(f"导出目标已存在，请换一个文件名：{output.name}")
    ps = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    encoded = base64.b64encode(SCRIPT.encode("utf-16-le")).decode("ascii")
    request = {"action": action, "commands": list(plan.commands) if plan else [],
               "requires_scenario": bool(plan and plan.requires_scenario),
               "expected_scenario": expected_scenario}
    process = open_powershell(ps, encoded)
    stdout, stderr = process.communicate(json.dumps(request, ensure_ascii=False))
    try:
        return json.loads(stdout.strip().lstrip("\ufeff"))
    except ValueError as error:
        raise RuntimeError(stderr.strip() or "STK 控制进程未返回可读结果。") from error


def open_powershell(executable, encoded):
    args = [str(executable), "-NoProfile", "-NonInteractive", "-STA", "-EncodedCommand", encoded]
    options = dict(stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                   encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW)
    bundle = getattr(sys, "_MEIPASS", None)
    if not bundle:
        return subprocess.Popen(args, **options)

    # External applications should use their own DLLs, not the PyInstaller bundle.
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