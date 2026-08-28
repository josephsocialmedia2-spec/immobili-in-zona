@echo off
setlocal
chcp 65001 >nul
title F1 - Automazione GitHub Radar Telefonate
set "PS1=%TEMP%\F1_INSTALLA_AUTOMAZIONE_GITHUB.ps1"
set "AUTO=%TEMP%\F1_ATTIVA_AVVIO_AUTOMATICO.ps1"
set "NOCACHE=%RANDOM%%RANDOM%%RANDOM%"
set "URL=https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/INSTALLA_AUTOMAZIONE_GITHUB.ps1?nocache=%NOCACHE%"
set "AUTOURL=https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/ATTIVA_AVVIO_AUTOMATICO.ps1?nocache=%NOCACHE%"
echo Scarico configurazione aggiornata da GitHub...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} '%URL%' -OutFile '%PS1%'"
if errorlevel 1 goto :errore
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if errorlevel 1 goto :errore

echo.
echo Attivo watchdog permanente del runner F1...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} '%AUTOURL%' -OutFile '%AUTO%'"
if errorlevel 1 goto :errore
powershell -NoProfile -ExecutionPolicy Bypass -File "%AUTO%"
if errorlevel 1 goto :errore

echo.
echo F1 AUTOMAZIONE GITHUB CONFIGURATA.
echo Il runner parte automaticamente ad ogni accesso Windows e viene riavviato se si chiude.
pause
exit /b 0
:errore
echo.
echo ERRORE NELLA CONFIGURAZIONE. Leggi il messaggio sopra.
pause
exit /b 1
