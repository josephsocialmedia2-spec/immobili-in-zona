$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Sync = Join-Path $PSScriptRoot 'sync_v2_db.py'
$Filter20 = Join-Path $PSScriptRoot 'filtra_susa_20km.py'
$Prospect = Join-Path $PSScriptRoot 'prospect_susa_20km.py'
$Central = Join-Path $PSScriptRoot 'centrale_telefonate_guidate.py'
$EnsureServer = Join-Path $PSScriptRoot 'ensure_centrale_server.ps1'
$Base = Join-Path $HOME 'Documents\F1_Directory_Microzone'
$Bridge = Join-Path $Base 'f1_microzone_directory_v3.py'
$BridgeUrl = 'https://raw.githubusercontent.com/josephsocialmedia2-spec/launcher-dashboard/main/windows-bridge/f1_microzone_directory_v3.py'
$Targets = Join-Path $Base 'data\microzone_targets.csv'
$MicroCalls = Join-Path $Base 'data\telefonate_mattino.csv'
$FocusCalls = Join-Path $Base 'data\telefonate_susa_20km.csv'
$WebProspects = Join-Path $Base 'data\prospect_web_susa_20km.csv'
$CentralCsv = Join-Path $Base 'data\centrale_telefonate_guidate.csv'
$CentralHtml = Join-Path $Base 'F1_CENTRALE_TELEFONATE_GUIDATE.html'
$HealthUrl = 'http://127.0.0.1:8766/health'
$CentralUrl = 'http://127.0.0.1:8766/'
$Desktop = [Environment]::GetFolderPath('Desktop')
$Shortcut = Join-Path $Desktop 'F1 - CENTRALE TELEFONATE GUIDATE.lnk'

New-Item -ItemType Directory -Force -Path $Base | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'data') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'IMPORTA_ESISTENTI') | Out-Null

Write-Host '=== F1 SUSA 20 KM -> RADAR -> CONTATTI PUBBLICI -> CENTRALE TELEFONATE GUIDATE ==='

Write-Host '[1/8] Dipendenze locali'
py -m pip install --disable-pip-version-check --quiet selenium openpyxl zeroconf
if ($LASTEXITCODE -ne 0) { throw "Installazione dipendenze terminata con codice $LASTEXITCODE" }

Write-Host '[2/8] Importo nel motore directory gli eventuali contatti locali gia esistenti'
py $Sync export
if ($LASTEXITCODE -ne 0) { throw "Sync database terminato con codice $LASTEXITCODE" }

Write-Host '[3/8] Scarico il bridge locale corrente'
Invoke-WebRequest -UseBasicParsing $BridgeUrl -OutFile $Bridge
if (-not (Test-Path $Bridge)) { throw 'Bridge V3 non scaricato.' }

Write-Host '[4/8] Radar -> microzone -> directory pubbliche -> numeri locali'
py $Bridge
if ($LASTEXITCODE -ne 0) { throw "Bridge V3 terminato con codice $LASTEXITCODE" }
if (-not (Test-Path $Targets)) { throw 'microzone_targets.csv non disponibile sul PC.' }
if (-not (Test-Path $MicroCalls)) { throw 'telefonate_mattino.csv non generato.' }

Write-Host '[5/8] Applico perimetro operativo unico SUSA + 20 KM'
py $Filter20
if ($LASTEXITCODE -ne 0) { throw "Filtro Susa 20 km terminato con codice $LASTEXITCODE" }
if (-not (Test-Path $FocusCalls)) { throw 'telefonate_susa_20km.csv non generato.' }

Write-Host '[6/8] Cerco prospect e contatti pubblicati sul web nel perimetro Susa 20 km'
$env:F1_SEARCH_INTERVAL = '2'
py $Prospect
if ($LASTEXITCODE -ne 0) { throw "Prospect web terminato con codice $LASTEXITCODE" }
if (-not (Test-Path $WebProspects)) { throw 'prospect_web_susa_20km.csv non generato.' }

Write-Host '[7/8] Unisco tutto nella F1 CENTRALE TELEFONATE GUIDATE'
py $Central
if ($LASTEXITCODE -ne 0) { throw "Centrale Telefonate terminata con codice $LASTEXITCODE" }
if (-not (Test-Path $CentralHtml)) { throw 'F1_CENTRALE_TELEFONATE_GUIDATE.html non generata.' }
if (-not (Test-Path $CentralCsv)) { throw 'centrale_telefonate_guidate.csv non generato.' }

Write-Host '[8/8] Installa/aggiorna server persistente, health-check e test restart'
if (-not (Test-Path $EnsureServer)) { throw 'ensure_centrale_server.ps1 non disponibile.' }
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File $EnsureServer
if ($LASTEXITCODE -ne 0) { throw "Setup server persistente terminato con codice $LASTEXITCODE" }

try {
    $r = Invoke-WebRequest -UseBasicParsing -Uri $HealthUrl -TimeoutSec 3
    if ($r.StatusCode -ne 200 -or $r.Content.Trim() -ne 'OK') { throw "Health-check inatteso: $($r.StatusCode) $($r.Content)" }
} catch {
    throw "Centrale locale NON raggiungibile dopo setup: $($_.Exception.Message)"
}
if (-not (Test-Path $Shortcut)) { throw 'Collegamento desktop verificato non disponibile.' }

Write-Host ''
Write-Host 'CENTRO OPERATIVO: SUSA' -ForegroundColor Green
Write-Host 'RAGGIO OPERATIVO: 20 KM' -ForegroundColor Green
Write-Host 'UNICO PUNTO CHIAMATE: F1 CENTRALE TELEFONATE GUIDATE' -ForegroundColor Green
Write-Host "URL LOCALE VERIFICATO: $CentralUrl" -ForegroundColor Green
Write-Host "ICONA DESKTOP: $Shortcut" -ForegroundColor Green
Write-Host "CSV CENTRALE: $CentralCsv" -ForegroundColor Cyan
Write-Host "PROSPECT WEB LOCALI: $WebProspects"
Write-Host 'NOTA: i prospect non vengono inseriti nel CRM automaticamente. Il CRM si usa solo dopo un esito utile.' -ForegroundColor Yellow
Write-Host 'PASS: /health ha risposto OK dopo stop + restart del servizio persistente.' -ForegroundColor Green
