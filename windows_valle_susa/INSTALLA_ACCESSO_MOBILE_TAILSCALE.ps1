$ErrorActionPreference = 'Stop'

$ReportDir = Join-Path $HOME 'Documents\F1_Directory_Microzone'
$Report = Join-Path $ReportDir 'LISTA_MATTINO.html'
$AutoDir = Join-Path $env:LOCALAPPDATA 'F1Radar'
$LinkFile = Join-Path $HOME 'Desktop\F1_LISTA_MATTINO_TELEFONO.txt'
$RunKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
$FallbackScript = Join-Path $AutoDir 'F1_MOBILE_FALLBACK.ps1'

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable('Path','Machine')
    $user = [Environment]::GetEnvironmentVariable('Path','User')
    $env:Path = "$machine;$user"
}

function Find-Tailscale {
    $cmd = Get-Command tailscale.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        (Join-Path $env:ProgramFiles 'Tailscale\tailscale.exe'),
        (Join-Path ${env:ProgramFiles(x86)} 'Tailscale\tailscale.exe')
    ) | Where-Object { $_ -and (Test-Path $_) }
    if ($candidates) { return $candidates[0] }
    return $null
}

Write-Host '=== F1 - ACCESSO PRIVATO LISTA_MATTINO DA TELEFONO ==='
Write-Host ''

if (-not (Test-Path $ReportDir)) {
    throw "Cartella F1 non trovata: $ReportDir"
}

$ts = Find-Tailscale
if (-not $ts) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        Start-Process 'https://tailscale.com/download/windows'
        throw 'Tailscale non installato e winget non disponibile. Ho aperto la pagina ufficiale di download.'
    }
    Write-Host 'Installazione Tailscale...' -ForegroundColor Cyan
    & winget install -e --id Tailscale.Tailscale --accept-package-agreements --accept-source-agreements
    if ($LASTEXITCODE -ne 0) {
        Start-Process 'https://tailscale.com/download/windows'
        throw 'Installazione automatica Tailscale non riuscita. Ho aperto la pagina ufficiale.'
    }
    Refresh-Path
    Start-Sleep -Seconds 4
    $ts = Find-Tailscale
}

if (-not $ts) { throw 'tailscale.exe non trovato dopo installazione.' }

Write-Host "Tailscale: $ts" -ForegroundColor Green

# Se il PC non e ancora dentro il tailnet, avvia il login. Il browser verra aperto da Tailscale.
$ip = ''
try { $ip = (& $ts ip -4 2>$null | Select-Object -First 1).Trim() } catch {}
if (-not ($ip -match '^100\.')) {
    Write-Host ''
    Write-Host 'Serve il login Tailscale UNA SOLA VOLTA sul PC.' -ForegroundColor Yellow
    Write-Host 'Completa l accesso nel browser quando si apre.'
    & $ts up
    if ($LASTEXITCODE -ne 0) { throw 'Accesso Tailscale non completato.' }
    for ($i=0; $i -lt 30; $i++) {
        Start-Sleep -Seconds 2
        try { $ip = (& $ts ip -4 2>$null | Select-Object -First 1).Trim() } catch { $ip = '' }
        if ($ip -match '^100\.') { break }
    }
}
if (-not ($ip -match '^100\.')) { throw 'IP Tailscale non disponibile. Verifica che Tailscale risulti Connected.' }

Write-Host "IP privato Tailscale PC: $ip" -ForegroundColor Green
New-Item -ItemType Directory -Force -Path $AutoDir | Out-Null

# Metodo preferito: Tailscale Serve. Con --bg resta attivo anche dopo reboot/restart del client.
$serveOk = $false
$serveOutput = ''
try {
    $serveOutput = (& $ts serve --bg --yes $ReportDir 2>&1 | Out-String)
    if ($LASTEXITCODE -eq 0) { $serveOk = $true }
} catch {
    $serveOutput = $_ | Out-String
}

$url = ''
if ($serveOk) {
    try {
        $status = (& $ts serve status 2>&1 | Out-String)
        $m = [regex]::Match($status, 'https://[^\s/]+')
        if ($m.Success) { $url = $m.Value.TrimEnd('/') + '/LISTA_MATTINO.html' }
    } catch {}
}

if (-not $url) {
    Write-Host 'Tailscale Serve non disponibile: attivo fallback privato su IP Tailscale.' -ForegroundColor Yellow

    $fallbackContent = @'
$ErrorActionPreference = 'SilentlyContinue'
$ReportDir = Join-Path $HOME 'Documents\F1_Directory_Microzone'
$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, 'F1_MOBILE_HTTP_SERVER', [ref]$createdNew)
if (-not $createdNew) { exit 0 }
try {
    while ($true) {
        $existing = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*http.server 8766*F1_Directory_Microzone*' }
        if (-not $existing) {
            $py = Get-Command py.exe -ErrorAction SilentlyContinue
            if (-not $py) { $py = Get-Command python.exe -ErrorAction SilentlyContinue }
            if ($py) {
                Start-Process -FilePath $py.Source -ArgumentList @('-m','http.server','8766','--bind','0.0.0.0','--directory',$ReportDir) -WindowStyle Hidden
                Start-Sleep -Seconds 8
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
    Set-Content -Path $FallbackScript -Value $fallbackContent -Encoding UTF8
    New-Item -Path $RunKey -Force | Out-Null
    $fallbackCmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$FallbackScript`""
    Set-ItemProperty -Path $RunKey -Name 'F1MobileHttpServer' -Value $fallbackCmd -Type String

    $ruleName = 'F1 Lista Mattino Tailscale'
    if (-not (Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue)) {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8766 -RemoteAddress '100.64.0.0/10' -Profile Any | Out-Null
    }

    Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-WindowStyle','Hidden','-ExecutionPolicy','Bypass','-File',$FallbackScript) -WindowStyle Hidden
    $url = "http://$ip`:8766/LISTA_MATTINO.html"
}

Set-Content -Path $LinkFile -Value @(
    'F1 LISTA MATTINO - LINK PRIVATO TELEFONO',
    '',
    $url,
    '',
    'Apri Tailscale sul telefono e verifica che sia CONNESSO allo stesso account/tailnet del PC.',
    'Poi apri questo link nel browser.'
) -Encoding UTF8

try { Set-Clipboard -Value $url } catch {}

Write-Host ''
Write-Host 'CONFIGURAZIONE COMPLETATA.' -ForegroundColor Green
Write-Host 'Il file originale resta:'
Write-Host "  $Report"
Write-Host ''
Write-Host 'LINK PRIVATO PER IL TELEFONO:' -ForegroundColor Green
Write-Host "  $url" -ForegroundColor Cyan
Write-Host ''
Write-Host "Il link e stato anche salvato qui: $LinkFile"
Write-Host 'Sul telefono installa Tailscale, accedi con lo STESSO account e attiva la connessione.'
Write-Host 'Nomi e numeri non vengono pubblicati su GitHub o sul web pubblico.'
