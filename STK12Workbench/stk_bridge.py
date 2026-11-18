"""Run STK Desktop automation through Windows PowerShell and report each command."""

from pathlib import Path
import base64
import json
import os
import subprocess

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
        throw '此电脑没有注册 STK 12 Desktop（STK12.Application）。可继续预览、复制和保存命令。'
    }
    try {
        $app = [Runtime.InteropServices.Marshal]::GetActiveObject($progId)
    } catch {
        if ($request.action -ne 'start') {
            throw '未找到正在运行的 STK 12。请从这里点击“启动 / 连接 STK”，或在同一 Windows 用户下手动启动 STK。'
        }
        $app = New-Object -ComObject $progId
    }
    if ($request.action -eq 'start') {
        $app.UserControl = $true
        $app.Visible = $true
    }
    $root = $app.Personality2
    $reply.version = @(Read-Result ($root.ExecuteCommand('GetSTKVersion /'))) -join ' '
    $current = $root.CurrentScenario
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
                $reply.error = '已在出错命令处停止。前面成功的步骤已应用，请按日志继续。'
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
    process = subprocess.run([str(ps), "-NoProfile", "-NonInteractive", "-STA",
                              "-EncodedCommand", encoded],
                             input=json.dumps(request, ensure_ascii=False),
                             encoding="utf-8", capture_output=True,
                             creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        return json.loads(process.stdout.strip().lstrip("\ufeff"))
    except ValueError as error:
        raise RuntimeError(process.stderr.strip() or "STK 控制进程未返回可读结果。") from error
