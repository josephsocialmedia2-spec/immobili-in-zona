$ErrorActionPreference = "Stop"
$AppName = "ACQUISIZIONE SUSA CRM"
$InstallDir = Join-Path $env:LOCALAPPDATA "AcquisizioneSusaCRM"
$DesktopDir = [Environment]::GetFolderPath("Desktop")

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js 22 o successivo non trovato. Installalo da https://nodejs.org e rilancia questo file."
}

New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
Get-ChildItem -Path (Split-Path $PSScriptRoot -Parent) -Force |
    Where-Object { $_.Name -notin @(".git", "data", "backups", "node_modules") } |
    Copy-Item -Destination $InstallDir -Recurse -Force

$EnvFile = Join-Path $InstallDir ".env"
if (-not (Test-Path $EnvFile)) {
    Copy-Item (Join-Path $InstallDir ".env.example") $EnvFile
}

$ShortcutPath = Join-Path $DesktopDir "$AppName.lnk"
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$InstallDir\scripts\start-windows.ps1`""
$Shortcut.WorkingDirectory = $InstallDir
$Shortcut.Description = "CRM acquisizione immobiliare F1 Susa"
$Shortcut.Save()

Write-Host "Installazione completata." -ForegroundColor Green
Write-Host "Collegamento creato sul Desktop: $AppName"
Start-Process $ShortcutPath
