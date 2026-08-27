$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Sync = Join-Path $PSScriptRoot 'sync_v2_db.py'
$Base = Join-Path $HOME 'Documents\F1_Directory_Microzone'
$Bridge = Join-Path $Base 'f1_microzone_directory.py'
$BridgeUrl = 'https://raw.githubusercontent.com/josephsocialmedia2-spec/launcher-dashboard/main/windows-bridge/f1_microzone_directory.py'

New-Item -ItemType Directory -Force -Path $Base | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'data') | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Base 'IMPORTA_ESISTENTI') | Out-Null

Write-Host '=== F1 RADAR VALLE DI SUSA -> TELEFONATE ==='
Write-Host '[1/5] Dipendenze Python'
py -m pip install --disable-pip-version-check --quiet selenium openpyxl

Write-Host '[2/5] Esporto il database VALLE_SUSA_UNICO v2 nel motore microzone'
py $Sync export

Write-Host '[3/5] Scarico da GitHub il motore numeri/vie aggiornato'
Invoke-WebRequest -UseBasicParsing $BridgeUrl -OutFile $Bridge

Write-Host '[4/5] PagineBianche/PagineGialle + microzone + lista mattino'
py $Bridge

Write-Host '[5/5] Riporto i nuovi contatti nel database VALLE_SUSA_UNICO v2'
py $Sync import

$Report = Join-Path $Base 'LISTA_MATTINO.html'
if (Test-Path $Report) {
    Start-Process $Report
    Write-Host "LISTA PRONTA: $Report"
}
