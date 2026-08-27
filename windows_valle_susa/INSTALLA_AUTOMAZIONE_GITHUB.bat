@echo off
setlocal
chcp 65001 >nul
title F1 - Automazione GitHub Radar Telefonate
set "PS1=%TEMP%\F1_INSTALLA_AUTOMAZIONE_GITHUB.ps1"
set "NOCACHE=%RANDOM%%RANDOM%%RANDOM%"
set "URL=https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/INSTALLA_AUTOMAZIONE_GITHUB.ps1?nocache=%NOCACHE%"
echo Scarico configurazione aggiornata da GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} '%URL%' -OutFile '%PS1%'"
if errorlevel 1 goto :errore
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if errorlevel 1 goto :errore
echo.
echo F1 AUTOMAZIONE GITHUB CONFIGURATA.
pause
exit /b 0
:errore
echo.
echo ERRORE NELLA CONFIGURAZIONE. Leggi il messaggio sopra.
pause
exit /b 1
