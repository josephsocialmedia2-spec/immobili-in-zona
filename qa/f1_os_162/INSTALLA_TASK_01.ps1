param(
    [Parameter(Mandatory=$true)][string]$PythonExe,
    [Parameter(Mandatory=$true)][string]$AppPath
)
$ErrorActionPreference = 'Stop'
$taskName = 'F1 OS Immobiliare - Flusso 01'
if (-not (Test-Path -LiteralPath $PythonExe)) { throw "Python non trovato: $PythonExe" }
if (-not (Test-Path -LiteralPath $AppPath)) { throw "F1 OS non trovato: $AppPath" }
$workDir = Split-Path -Parent $AppPath
$action = New-ScheduledTaskAction -Execute $PythonExe -Argument ('"{0}" --daily-flow' -f $AppPath) -WorkingDirectory $workDir
$trigger = New-ScheduledTaskTrigger -Daily -At 1:00AM
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 3)
$userId = if ($env:USERDOMAIN) { "$($env:USERDOMAIN)\$($env:USERNAME)" } else { $env:USERNAME }
$principal = New-ScheduledTaskPrincipal -UserId $userId -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'F1 OS: sincronizzazione Seller Radar e ricerca contatti incrementale ogni giorno alle 01:00; recupero al primo momento utile se il PC non era disponibile.' -Force | Out-Null
$task = Get-ScheduledTask -TaskName $taskName
if (-not $task) { throw 'Attività pianificata non creata.' }
Write-Host "TASK_OK|$taskName|01:00|StartWhenAvailable|$PythonExe"
