$ErrorActionPreference = "Stop"
$root = Resolve-Path (Join-Path $PSScriptRoot "..")
$dist = Join-Path $root "dist"
if (-not (Test-Path $dist)) { New-Item -ItemType Directory -Path $dist | Out-Null }
$target = Join-Path $dist "F1_INDIRIZZO_REMOTO_WINDOWS.zip"
if (Test-Path $target) { Remove-Item $target }
$items = Get-ChildItem $root -Force | Where-Object { $_.Name -notin @(".git", ".venv", "data", "uploads", "exports", "letters", "backups", "diagnostics", "dist", "build") }
Compress-Archive -Path $items.FullName -DestinationPath $target -CompressionLevel Optimal
Write-Host "Pacchetto creato: $target"
