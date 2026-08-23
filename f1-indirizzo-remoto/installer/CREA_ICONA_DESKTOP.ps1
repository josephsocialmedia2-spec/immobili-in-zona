$ErrorActionPreference = "Stop"
$installRoot = Join-Path $env:LOCALAPPDATA "F1IndirizzoRemoto"
$target = Join-Path $installRoot "app\installer\AVVIA_ORA.bat"
if (-not (Test-Path $target)) { throw "AVVIA_ORA.bat non trovato" }
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "F1 INDIRIZZO REMOTO.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = Split-Path $target
$shortcut.Description = "F1 Indirizzo Remoto - verifica e CRM locale"
$shortcut.WindowStyle = 1
$shortcut.Save()
Write-Host "Icona Desktop creata."
