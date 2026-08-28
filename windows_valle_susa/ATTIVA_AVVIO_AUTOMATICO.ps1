$ErrorActionPreference = 'Stop'

$RunnerDir = Join-Path $HOME 'F1-GitHub-Runner'
$RunCmd = Join-Path $RunnerDir 'run.cmd'
$AutoDir = Join-Path $env:LOCALAPPDATA 'F1Radar'
$Watchdog = Join-Path $AutoDir 'F1_RUNNER_WATCHDOG.ps1'
$Startup = [Environment]::GetFolderPath('Startup')
$StartupLink = Join-Path $Startup 'F1 GitHub Runner.lnk'
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'

if (-not (Test-Path $RunCmd)) {
    throw "Runner non trovato: $RunCmd. Esegui prima INSTALLA_AUTOMAZIONE_GITHUB.bat."
}

New-Item -ItemType Directory -Force -Path $AutoDir | Out-Null

$watchdogContent = @'
$ErrorActionPreference = 'SilentlyContinue'
$RunnerDir = Join-Path $HOME 'F1-GitHub-Runner'
$RunCmd = Join-Path $RunnerDir 'run.cmd'

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, 'F1_GITHUB_RUNNER_WATCHDOG', [ref]$createdNew)
if (-not $createdNew) { exit 0 }

try {
    while ($true) {
        if (-not (Test-Path $RunCmd)) {
            Start-Sleep -Seconds 60
            continue
        }

        $listener = Get-CimInstance Win32_Process | Where-Object {
            ($_.Name -eq 'Runner.Listener.exe' -or $_.Name -eq 'Runner.Listener') -and
            (($_.ExecutablePath -like "$RunnerDir*") -or ($_.CommandLine -like "*$RunnerDir*"))
        }

        if (-not $listener) {
            Start-Process -FilePath $RunCmd -WorkingDirectory $RunnerDir -WindowStyle Minimized
            Start-Sleep -Seconds 12
        }

        Start-Sleep -Seconds 20
    }
}
finally {
    try { $mutex.ReleaseMutex() } catch {}
    $mutex.Dispose()
}
'@

Set-Content -Path $Watchdog -Value $watchdogContent -Encoding UTF8

# Avvio automatico principale: chiave utente Windows. Non richiede amministratore.
New-Item -Path $RunKey -Force | Out-Null
$autoCommand = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Watchdog`""
Set-ItemProperty -Path $RunKey -Name 'F1GitHubRunnerWatchdog' -Value $autoCommand -Type String

# Backup: anche il collegamento Startup punta al watchdog, non direttamente a run.cmd.
$ws = New-Object -ComObject WScript.Shell
$link = $ws.CreateShortcut($StartupLink)
$link.TargetPath = 'powershell.exe'
$link.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Watchdog`""
$link.WorkingDirectory = $AutoDir
$link.WindowStyle = 7
$link.Save()

# Avvia subito il watchdog. Il mutex impedisce doppioni tra Run e Startup.
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',$Watchdog) -WindowStyle Hidden
Start-Sleep -Seconds 5

$listenerNow = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'Runner.Listener.exe' -or $_.Name -eq 'Runner.Listener') -and
    (($_.ExecutablePath -like "$RunnerDir*") -or ($_.CommandLine -like "*$RunnerDir*"))
}

Write-Host ''
Write-Host 'F1 AVVIO AUTOMATICO ATTIVATO.' -ForegroundColor Green
Write-Host 'Da ora non devi aprire run.cmd manualmente.' -ForegroundColor Green
Write-Host "Watchdog: $Watchdog"
Write-Host 'Avvio: automatico ad ogni accesso Windows + riavvio automatico del runner se si chiude.'
if ($listenerNow) {
    Write-Host 'Runner F1: ONLINE.' -ForegroundColor Green
} else {
    Write-Host 'Runner F1: avvio richiesto; puo impiegare alcuni secondi a comparire online.' -ForegroundColor Yellow
}
