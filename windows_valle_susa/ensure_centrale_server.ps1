param(
    [switch]$SkipTaskRegistration
)

$ErrorActionPreference = 'Stop'

$Port = 8766
$HealthUrl = "http://127.0.0.1:$Port/health"
$TaskName = 'F1 Centrale Server'
$AutoDir = Join-Path $env:LOCALAPPDATA 'F1Radar'
$ServerSource = Join-Path $PSScriptRoot 'f1_mobile_server.py'
$LauncherSource = Join-Path $PSScriptRoot 'APRI_CENTRALE_PC.bat'
$GeneratorSource = Join-Path $PSScriptRoot 'centrale_telefonate_guidate.py'
$Server = Join-Path $AutoDir 'f1_mobile_server.py'
$Launcher = Join-Path $AutoDir 'APRI_CENTRALE_PC.bat'
$Generator = Join-Path $AutoDir 'centrale_telefonate_guidate.py'
$Desktop = [Environment]::GetFolderPath('Desktop')
$DesktopShortcut = Join-Path $Desktop 'F1 - CENTRALE TELEFONATE GUIDATE.lnk'

function Test-F1Health {
    try {
        $r = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 2
        return ($r.StatusCode -eq 200 -and $r.Content.Trim() -eq 'OK')
    } catch {
        return $false
    }
}

function Wait-F1Health([bool]$Expected, [int]$Attempts = 30) {
    for ($i = 0; $i -lt $Attempts; $i++) {
        if ((Test-F1Health) -eq $Expected) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Stop-F1ServerProcess {
    $listeners = @()
    try {
        $listeners = @(Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue)
    } catch {}

    foreach ($listener in $listeners) {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
        if ($proc -and $proc.CommandLine -match 'f1_mobile_server\.py') {
            Stop-Process -Id $listener.OwningProcess -Force -ErrorAction SilentlyContinue
        } elseif ($proc) {
            throw "Porta $Port occupata da un processo non F1: PID $($listener.OwningProcess) $($proc.Name)"
        }
    }
}

if (-not (Test-Path $ServerSource)) { throw "Server sorgente non trovato: $ServerSource" }
if (-not (Test-Path $LauncherSource)) { throw "Launcher sorgente non trovato: $LauncherSource" }
if (-not (Test-Path $GeneratorSource)) { throw "Generatore sorgente non trovato: $GeneratorSource" }

New-Item -ItemType Directory -Force -Path $AutoDir | Out-Null
Copy-Item -Force $ServerSource $Server
Copy-Item -Force $LauncherSource $Launcher
Copy-Item -Force $GeneratorSource $Generator

$pythonCommand = Get-Command py.exe -ErrorAction SilentlyContinue
if (-not $pythonCommand) { $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue }
if (-not $pythonCommand) { throw 'Python non trovato (py.exe/python.exe).' }
$PythonExe = $pythonCommand.Source

if (-not $SkipTaskRegistration) {
    $currentUser = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $action = New-ScheduledTaskAction -Execute $PythonExe -Argument "`"$Server`""
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $principal = New-ScheduledTaskPrincipal -UserId $currentUser -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction Stop
    if ($task.Triggers.Count -lt 1) { throw 'Trigger avvio automatico Windows non registrato.' }
}

# Il collegamento desktop apre SEMPRE il launcher, che esegue a sua volta /health.
$ws = New-Object -ComObject WScript.Shell
$link = $ws.CreateShortcut($DesktopShortcut)
$link.TargetPath = $Launcher
$link.WorkingDirectory = $AutoDir
$link.IconLocation = 'shell32.dll,220'
$link.Description = 'F1 Immobiliare - Centrale Telefonate con health-check'
$link.Save()
if (-not (Test-Path $DesktopShortcut)) { throw 'Collegamento desktop Centrale non creato.' }

# Elimina un eventuale vecchio server F1, poi avvia la versione persistente.
if (-not $SkipTaskRegistration) {
    try { Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue } catch {}
}
Stop-F1ServerProcess
if (-not (Wait-F1Health $false 12)) { throw "La porta $Port non si e chiusa correttamente." }

if ($SkipTaskRegistration) {
    Start-Process -WindowStyle Hidden -FilePath $PythonExe -ArgumentList @($Server) | Out-Null
} else {
    Start-ScheduledTask -TaskName $TaskName
}
if (-not (Wait-F1Health $true 30)) { throw "Server Centrale non raggiungibile su $HealthUrl dopo l'avvio." }

# Test di riavvio reale del processo/attivita, non semplice controllo statico.
if (-not $SkipTaskRegistration) {
    Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Stop-F1ServerProcess
    if (-not (Wait-F1Health $false 20)) { throw 'FAIL stop server: /health continua a rispondere.' }
    Start-ScheduledTask -TaskName $TaskName
    if (-not (Wait-F1Health $true 30)) { throw 'FAIL restart server: /health non torna ONLINE.' }
}

Write-Host "PASS: Centrale server /health OK su $HealthUrl" -ForegroundColor Green
if (-not $SkipTaskRegistration) {
    Write-Host "PASS: task '$TaskName' registrato per AtLogOn e riavvio processo verificato." -ForegroundColor Green
}
Write-Host "PASS: collegamento desktop -> $Launcher" -ForegroundColor Green
