$ErrorActionPreference = "Stop"
$ProjectDir = Split-Path $PSScriptRoot -Parent
Set-Location $ProjectDir

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("Node.js 22 o successivo non è installato.", "ACQUISIZIONE SUSA CRM") | Out-Null
    exit 1
}

if (Get-Command ollama -ErrorAction SilentlyContinue) {
    try {
        Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:11434/api/tags" -TimeoutSec 2 | Out-Null
    } catch {
        Start-Process -WindowStyle Hidden ollama -ArgumentList "serve"
    }
}

$Existing = Get-NetTCPConnection -LocalPort 4173 -State Listen -ErrorAction SilentlyContinue
if (-not $Existing) {
    Start-Process -WindowStyle Hidden node -ArgumentList "src/server.mjs" -WorkingDirectory $ProjectDir
    Start-Sleep -Seconds 2
}
Start-Process "http://127.0.0.1:4173"
