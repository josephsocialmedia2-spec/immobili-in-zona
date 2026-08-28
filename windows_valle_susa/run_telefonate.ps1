$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Sync = Join-Path $PSScriptRoot 'sync_v2_db.py'
$Base = Join-Path $HOME 'Documents\F1_Directory_Microzone'
$Bridge = Join-Path $Base 'f1_microzone_directory_v3.py'
$BridgeUrl = 'https://raw.githubusercontent.com/josephsocialmedia2-spec/launcher-dashboard/main/windows-bridge/f1_microzone_directory_v3.py'
$Targets = Join-Path $Base 'data\microzone_targets.csv'
$Report = Join-Path $Base 'LISTA_MATTINO.html'
$Calls = Join-Path $Base 'data\telefonate_mattino.csv'

New-Item -ItemType Directory -Force -Path $Base | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'data') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'IMPORTA_ESISTENTI') | Out-Null

Write-Host '=== F1 RADAR -> TUTTI I DATI -> MICROZONE -> NUMERI -> LISTA MATTINO V3 ==='
Write-Host '[1/5] Dipendenze Python'
py -m pip install --disable-pip-version-check --quiet selenium openpyxl

Write-Host '[2/5] Esporto il database VALLE_SUSA_UNICO v2 nel motore microzone'
py $Sync export

Write-Host '[3/5] Scarico da GitHub il bridge locale V3 completo'
Invoke-WebRequest -UseBasicParsing $BridgeUrl -OutFile $Bridge
if (-not (Test-Path $Bridge)) { throw 'Bridge V3 non scaricato.' }

Write-Host '[4/5] Radar completo -> 10 funzionari -> annunci -> vie -> 4 vie vicine -> numeri -> LISTA_MATTINO'
py $Bridge
if ($LASTEXITCODE -ne 0) { throw "Bridge V3 terminato con codice $LASTEXITCODE" }
if (-not (Test-Path $Targets)) { throw 'microzone_targets.csv non disponibile sul PC.' }
if (-not (Test-Path $Report)) { throw 'LISTA_MATTINO.html non e stata generata.' }
if (-not (Test-Path $Calls)) { throw 'telefonate_mattino.csv non e stato generato.' }

Write-Host '[5/5] Riporto i nuovi contatti nel database VALLE_SUSA_UNICO v2'
py $Sync import

Write-Host "RISULTATO OPERATIVO COMPLETO: $Report"
Write-Host "CSV TELEFONATE ARRICCHITO: $Calls"
Start-Process $Report
