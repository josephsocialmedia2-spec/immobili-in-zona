$ErrorActionPreference = 'Stop'

$RunnerDir = Join-Path $HOME 'F1-GitHub-Runner'
$RunCmd = Join-Path $RunnerDir 'run.cmd'
$AutoDir = Join-Path $env:LOCALAPPDATA 'F1Radar'
$Watchdog = Join-Path $AutoDir 'F1_RUNNER_WATCHDOG.ps1'
$MobileServer = Join-Path $AutoDir 'f1_mobile_server.py'
$MobileServerUrl = 'https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/f1_mobile_server.py'
$Startup = [Environment]::GetFolderPath('Startup')
$StartupLink = Join-Path $Startup 'F1 GitHub Runner.lnk'
$Desktop = [Environment]::GetFolderPath('Desktop')
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$MobileUrl = 'http://f1-radar.local:8766/'

if (-not (Test-Path $RunCmd)) {
    throw "Runner non trovato: $RunCmd. Esegui prima INSTALLA_AUTOMAZIONE_GITHUB.bat."
}

New-Item -ItemType Directory -Force -Path $AutoDir | Out-Null

Write-Host 'Scarico server mobile F1...'
Invoke-WebRequest -UseBasicParsing -Headers @{ 'Cache-Control'='no-cache' } $MobileServerUrl -OutFile $MobileServer
if (-not (Test-Path $MobileServer)) { throw 'Server mobile F1 non scaricato.' }

# Zeroconf pubblicizza f1-radar.local nella sola LAN.
py -m pip install --disable-pip-version-check --quiet zeroconf
if ($LASTEXITCODE -ne 0) { throw 'Installazione zeroconf fallita.' }

$watchdogContent = @'
$ErrorActionPreference = 'SilentlyContinue'
$RunnerDir = Join-Path $HOME 'F1-GitHub-Runner'
$RunCmd = Join-Path $RunnerDir 'run.cmd'
$AutoDir = Join-Path $env:LOCALAPPDATA 'F1Radar'
$MobileServer = Join-Path $AutoDir 'f1_mobile_server.py'

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, 'F1_GITHUB_RUNNER_WATCHDOG', [ref]$createdNew)
if (-not $createdNew) { exit 0 }

try {
    while ($true) {
        if (Test-Path $RunCmd) {
            $listener = Get-CimInstance Win32_Process | Where-Object {
                ($_.Name -eq 'Runner.Listener.exe' -or $_.Name -eq 'Runner.Listener') -and
                (($_.ExecutablePath -like "$RunnerDir*") -or ($_.CommandLine -like "*$RunnerDir*"))
            }
            if (-not $listener) {
                Start-Process -FilePath $RunCmd -WorkingDirectory $RunnerDir -WindowStyle Minimized
                Start-Sleep -Seconds 12
            }
        }

        if (Test-Path $MobileServer) {
            $mobile = Get-CimInstance Win32_Process | Where-Object {
                ($_.Name -like 'python*.exe' -or $_.Name -eq 'py.exe') -and $_.CommandLine -like "*$MobileServer*"
            }
            if (-not $mobile) {
                Start-Process -FilePath 'py.exe' -ArgumentList @($MobileServer) -WorkingDirectory $AutoDir -WindowStyle Hidden
                Start-Sleep -Seconds 4
            }
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

# Avvio automatico principale: chiave utente Windows.
New-Item -Path $RunKey -Force | Out-Null
$autoCommand = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Watchdog`""
Set-ItemProperty -Path $RunKey -Name 'F1GitHubRunnerWatchdog' -Value $autoCommand -Type String

# Backup: collegamento nella cartella Esecuzione automatica.
$ws = New-Object -ComObject WScript.Shell
$link = $ws.CreateShortcut($StartupLink)
$link.TargetPath = 'powershell.exe'
$link.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$Watchdog`""
$link.WorkingDirectory = $AutoDir
$link.WindowStyle = 7
$link.Save()

# Collegamento desktop alla pagina mobile stabile.
$mobileLink = $ws.CreateShortcut((Join-Path $Desktop 'F1 - Lista Mattino Telefono.lnk'))
$mobileLink.TargetPath = $MobileUrl
$mobileLink.IconLocation = 'shell32.dll,220'
$mobileLink.Save()

# Prova ad autorizzare la porta solo su reti PRIVATE. Se non siamo amministratori,
# l'installer BAT dedicato puo essere eseguito una volta con UAC.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if ($isAdmin) {
    $existing = Get-NetFirewallRule -DisplayName 'F1 Radar Mobile 8766' -ErrorAction SilentlyContinue
    if (-not $existing) {
        New-NetFirewallRule -DisplayName 'F1 Radar Mobile 8766' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766 -Profile Private | Out-Null
    }
    Write-Host 'Firewall: porta 8766 autorizzata solo su reti PRIVATE.' -ForegroundColor Green
} else {
    Write-Host 'Firewall: esecuzione non amministratore; se il telefono non apre la pagina, usa ATTIVA_TELEFONO_F1.bat una sola volta.' -ForegroundColor Yellow
}

# Avvia subito watchdog + server.
Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',$Watchdog) -WindowStyle Hidden
Start-Sleep -Seconds 8

$listenerNow = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -eq 'Runner.Listener.exe' -or $_.Name -eq 'Runner.Listener') -and
    (($_.ExecutablePath -like "$RunnerDir*") -or ($_.CommandLine -like "*$RunnerDir*"))
}
$mobileNow = Get-CimInstance Win32_Process | Where-Object {
    ($_.Name -like 'python*.exe' -or $_.Name -eq 'py.exe') -and $_.CommandLine -like "*$MobileServer*"
}

Write-Host ''
Write-Host 'F1 AUTOMAZIONE COMPLETA ATTIVATA.' -ForegroundColor Green
Write-Host 'Da ora non devi aprire run.cmd manualmente.' -ForegroundColor Green
Write-Host 'Runner: automatico ad ogni accesso Windows + riavvio automatico.'
Write-Host 'Pagina telefono (stessa Wi-Fi):' -ForegroundColor Cyan
Write-Host $MobileUrl -ForegroundColor Cyan
Write-Host "Link di riserva/IP viene scritto in: $HOME\Documents\F1_Directory_Microzone\LINK_TELEFONO.txt"
if ($listenerNow) { Write-Host 'Runner F1: ONLINE.' -ForegroundColor Green } else { Write-Host 'Runner F1: avvio richiesto.' -ForegroundColor Yellow }
if ($mobileNow) { Write-Host 'Server telefono F1: ONLINE.' -ForegroundColor Green } else { Write-Host 'Server telefono F1: avvio richiesto.' -ForegroundColor Yellow }
