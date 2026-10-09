#Requires -Version 5.1
param(
    [ValidateSet('install','status','stop')][string]$Action,
    [string]$ConfigPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
if ($env:OS -ne 'Windows_NT') { throw 'Windows task registration requires Windows.' }
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskName = 'AgentLab-CodexUsage-' + $identity.User.Value
$task = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue

if ($Action -eq 'stop') {
    # AI_NOTE: Remove future triggers while retaining the user's usage history.
    if ($task) {
        Stop-ScheduledTask -TaskName $taskName
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    Write-Output 'Usage recording stopped; history preserved.'
    exit 0
}
if ($Action -eq 'status') {
    if (-not $task) { throw 'FAIL: usage recording task is not installed.' }
    if ($task.State -eq 'Disabled') { throw 'FAIL: usage recording task is disabled.' }
    $info = Get-ScheduledTaskInfo -TaskName $taskName
    if ($info.LastTaskResult -notin @(0,267009,267011)) { throw "FAIL: scheduled recording result $($info.LastTaskResult)." }
    $task | Select-Object TaskName, State
    $info | Select-Object LastRunTime, LastTaskResult, NextRunTime
    exit 0
}
$config = Get-Content -LiteralPath $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
$Python = $config.Python
$Arguments = $config.Arguments
$WorkingDirectory = $config.WorkingDirectory
if (-not (Test-Path -LiteralPath $Python) -or -not (Test-Path -LiteralPath $WorkingDirectory)) {
    throw 'Python executable or usage directory missing.'
}
# AI_NOTE: Back up an existing definition before updating; no credentials are exported.
if ($task) {
    Export-ScheduledTask -TaskName $taskName |
        Set-Content -LiteralPath (Join-Path $WorkingDirectory 'previous-task.xml') -Encoding Unicode
    Stop-ScheduledTask -TaskName $taskName
}
$taskAction = New-ScheduledTaskAction -Execute $Python -Argument $Arguments -WorkingDirectory $WorkingDirectory
# AI_NOTE: Omitted repetition duration means indefinite repetition, including future days.
$timer = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$logon = New-ScheduledTaskTrigger -AtLogOn -User $identity.Name
$principal = New-ScheduledTaskPrincipal -UserId $identity.Name -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $taskName -Action $taskAction -Trigger @($timer,$logon) `
    -Principal $principal -Settings $settings -Force | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Output "Recording every 60 seconds; output directory: $WorkingDirectory"
