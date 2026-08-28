$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Sync = Join-Path $PSScriptRoot 'sync_v2_db.py'
$Priority = Join-Path $PSScriptRoot 'priorita_susa_10km.py'
$Base = Join-Path $HOME 'Documents\F1_Directory_Microzone'
$Bridge = Join-Path $Base 'f1_microzone_directory_v3.py'
$BridgeUrl = 'https://raw.githubusercontent.com/josephsocialmedia2-spec/launcher-dashboard/main/windows-bridge/f1_microzone_directory_v3.py'
$Targets = Join-Path $Base 'data\microzone_targets.csv'
$Report = Join-Path $Base 'LISTA_MATTINO.html'
$FocusReport = Join-Path $Base 'LISTA_SUSA_10KM.html'
$Calls = Join-Path $Base 'data\telefonate_mattino.csv'
$FocusCalls = Join-Path $Base 'data\telefonate_susa_10km.csv'

New-Item -ItemType Directory -Force -Path $Base | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'data') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'IMPORTA_ESISTENTI') | Out-Null

Write-Host '=== F1 RADAR -> SUSA + 10 KM PRIMA -> MICROZONE -> NUMERI -> LISTA TELEFONATE ==='
Write-Host '[1/6] Dipendenze Python'
py -m pip install --disable-pip-version-check --quiet selenium openpyxl

Write-Host '[2/6] Esporto il database VALLE_SUSA_UNICO v2 nel motore microzone'
py $Sync export

Write-Host '[3/6] Scarico da GitHub il bridge locale V3 completo'
Invoke-WebRequest -UseBasicParsing $BridgeUrl -OutFile $Bridge
if (-not (Test-Path $Bridge)) { throw 'Bridge V3 non scaricato.' }

Write-Host '[4/6] Radar completo -> annunci -> vie -> 4 vie vicine -> numeri -> LISTA_MATTINO'
py $Bridge
if ($LASTEXITCODE -ne 0) { throw "Bridge V3 terminato con codice $LASTEXITCODE" }
if (-not (Test-Path $Targets)) { throw 'microzone_targets.csv non disponibile sul PC.' }
if (-not (Test-Path $Report)) { throw 'LISTA_MATTINO.html non e stata generata.' }
if (-not (Test-Path $Calls)) { throw 'telefonate_mattino.csv non e stato generato.' }

Write-Host '[5/6] Applico priorita SUSA + comuni entro 10 km'
if (-not (Test-Path $Priority)) { throw "Script priorita non trovato: $Priority" }
py $Priority
if ($LASTEXITCODE -ne 0) { throw "Priorita Susa 10 km terminata con codice $LASTEXITCODE" }
if (-not (Test-Path $FocusReport)) { throw 'LISTA_SUSA_10KM.html non e stata generata.' }
if (-not (Test-Path $FocusCalls)) { throw 'telefonate_susa_10km.csv non e stato generato.' }

Write-Host '[6/6] Riporto i nuovi contatti nel database VALLE_SUSA_UNICO v2'
py $Sync import

# Collegamento Desktop stabile alla lista prioritaria.
$Desktop = [Environment]::GetFolderPath('Desktop')
$Shortcut = Join-Path $Desktop 'F1 - TELEFONATE SUSA 10 KM.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Link = $Shell.CreateShortcut($Shortcut)
$Link.TargetPath = $FocusReport
$Link.WorkingDirectory = $Base
$Link.IconLocation = 'shell32.dll,220'
$Link.Description = 'F1 Immobiliare - Telefonate prioritarie Susa e raggio 10 km'
$Link.Save()

Write-Host ''
Write-Host 'PRIORITA OPERATIVA: SUSA + 10 KM' -ForegroundColor Green
Write-Host "APRI PER TELEFONARE: $FocusReport" -ForegroundColor Green
Write-Host "ICONA DESKTOP: $Shortcut" -ForegroundColor Green
Write-Host "CSV SUSA + 10 KM: $FocusCalls" -ForegroundColor Cyan
Write-Host "LISTA COMPLETA VALLE: $Report"
Write-Host "CSV COMPLETO: $Calls"
Start-Process $FocusReport
