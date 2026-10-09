#Requires -Version 5.1
# Verify Windows plumbing with a local protocol fixture, without logging in or using an AI model.
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$taskName = 'AgentLab-CodexUsage-' + $identity.User.Value
if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
    throw 'Use an isolated Windows runner: an existing recorder must not be replaced by verification.'
}
$root = Join-Path ([IO.Path]::GetTempPath()) ('usage verification ' + [guid]::NewGuid())
$source = Join-Path $root 'repo with spaces'
$data = Join-Path $root 'data with spaces'
New-Item -ItemType Directory -Path $source,$data -Force | Out-Null
foreach ($name in @('codex_usage.py','windows-task.ps1','graph.py','graph.html')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $name) -Destination $source
}
$collector = Join-Path $source 'codex_usage.py'
$csv = Join-Path $data 'usage.csv'
$binary = Join-Path $root 'codex.exe'
$fixture = @'
using System;
using System.Text.RegularExpressions;
public class Fixture {
  public static void Main() {
    string line;
    while ((line = Console.ReadLine()) != null) {
      var match = Regex.Match(line, "\"id\"\\s*:\\s*(\\d+)");
      if (!match.Success) continue;
      string result;
      if (line.Contains("account/rateLimits/read"))
        result = "{\"rateLimits\":{\"limitId\":\"codex\",\"primary\":{\"usedPercent\":24,\"windowDurationMins\":10080,\"resetsAt\":2000000000}}}";
      else if (line.Contains("account/read"))
        result = "{\"account\":{\"id\":\"fixture-account\",\"type\":\"chatgpt\",\"planType\":\"pro\"}}";
      else if (line.Contains("initialize")) result = "{}";
      else throw new Exception("Unexpected method: no AI execution is allowed");
      Console.WriteLine("{\"id\":" + match.Groups[1].Value + ",\"result\":" + result + "}");
    }
  }
}
'@
Add-Type -TypeDefinition $fixture -OutputAssembly $binary -OutputType ConsoleApplication
$env:CODEX_HOME = Join-Path $root 'empty codex home'
try {
    # Installation must work with Windows' default script restriction, without changing it globally.
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Restricted -Force
    & python $collector once --codex $binary --csv $csv
    if ($LASTEXITCODE -ne 0) { throw 'Native acquisition failed.' }
    $rows = @(Import-Csv -LiteralPath $csv)
    if ($rows.Count -ne 1 -or $rows[0].used_percent -ne '24' -or $rows[0].status -ne 'warming_up') {
        throw 'Initial observation differs.'
    }
    # Verify npm's .cmd entry is bypassed in favor of its native platform package.
    $npm = Join-Path $root 'npm with spaces'
    $nativeFolder = Join-Path $npm 'node_modules\@openai\codex-win32-x64\vendor\x86_64-pc-windows-msvc\bin'
    New-Item -ItemType Directory -Path $nativeFolder -Force | Out-Null
    Copy-Item -LiteralPath $binary -Destination (Join-Path $nativeFolder 'codex.exe')
    $shim = Join-Path $npm 'codex.cmd'
    Set-Content -LiteralPath $shim -Value '@exit /b 99'
    & python $collector once --codex $shim --csv $csv
    if ($LASTEXITCODE -ne 0) { throw 'npm native-binary resolution failed.' }
    # AI_NOTE: Exercise native locking with two overlapping real collector processes.
    $jobs = @(1,2 | ForEach-Object {
        Start-Job -ScriptBlock { param($script,$exe,$out) & python $script once --codex $exe --csv $out; if ($LASTEXITCODE -ne 0) { throw 'Concurrent acquisition failed.' } } -ArgumentList $collector,$binary,$csv
    })
    $jobs | Wait-Job | Receive-Job -ErrorAction Stop | Out-Host
    $jobs | Remove-Job
    if (@(Import-Csv -LiteralPath $csv).Count -ne 4) { throw 'Concurrent observations missing.' }
    foreach ($attempt in 1,2) {
        & python $collector install --codex $binary --csv $csv
        if ($LASTEXITCODE -ne 0) { throw 'Installation or reinstallation failed.' }
    }
    $deadline = (Get-Date).AddSeconds(20)
    $log = Join-Path $data 'collector.log'
    while (-not (Test-Path -LiteralPath $log) -and (Get-Date) -lt $deadline) { Start-Sleep -Milliseconds 500 }
    Start-Sleep -Seconds 2
    if (-not (Test-Path -LiteralPath $log) -or -not (Get-Content $log -Raw).Contains('warming_up')) {
        throw 'Scheduled hidden acquisition did not write its log.'
    }
    $task = Get-ScheduledTask -TaskName $taskName
    $definition = [xml](Export-ScheduledTask -TaskName $taskName)
    # The scheduler omits RunLevel when it is the schema default, LeastPrivilege.
    $runLevel = $definition.SelectSingleNode("//*[local-name()='Principal']/*[local-name()='RunLevel']")
    if (($runLevel -and $runLevel.InnerText -ne 'LeastPrivilege') -or $task.Settings.WakeToRun) {
        throw 'Unexpected task privileges or wake behavior.'
    }
    $timer = $definition.SelectNodes("//*[local-name()='TimeTrigger']/*[local-name()='Repetition']")
    if ($timer.Count -ne 1 -or $timer[0].Interval -ne 'PT1M' -or $timer[0].SelectNodes("*[local-name()='Duration']").Count) {
        throw 'One-minute indefinite trigger missing.'
    }
    & python $collector check --codex $binary --csv $csv
    if ($LASTEXITCODE -ne 0) { throw 'Installed task check failed.' }
    & python $collector once --codex (Join-Path $root 'missing.exe') --csv $csv
    if ($LASTEXITCODE -eq 0 -or @(Import-Csv $csv)[-1].status -ne 'fetch_error') { throw 'Missing dependency was not reported.' }
    # AI_NOTE: The offline graph uses the same Windows CSV, including unknown failure rows.
    $graph = Join-Path $data 'usage graph.html'
    & python (Join-Path $source 'graph.py') --csv $csv --output $graph
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $graph)) { throw 'Graph generation failed.' }
    $html = Get-Content -LiteralPath $graph -Raw -Encoding UTF8
    if ($html.Contains('@@DATA@@') -or -not $html.Contains('fetch_error') -or -not $html.Contains('"used": 24.0')) {
        throw 'Graph did not embed the recorded measurements and failures.'
    }
    & python $collector stop
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $csv)) { throw 'Stop did not preserve history.' }
    & python $collector check --codex $binary --csv $csv
    if ($LASTEXITCODE -eq 0) { throw 'Missing task was incorrectly reported as healthy.' }
    Write-Output 'PASS: acquisition, concurrent locks, paths with spaces, install twice, hidden scheduled recording, check, missing dependencies, offline graph, stop.'
} finally {
    if (Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue) {
        Stop-ScheduledTask -TaskName $taskName
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
    Remove-Item -LiteralPath $root -Recurse -Force
}
exit 0
