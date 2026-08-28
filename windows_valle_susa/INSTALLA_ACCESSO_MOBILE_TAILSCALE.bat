@echo off
setlocal
chcp 65001 >nul
title F1 - Accesso Mobile Privato

set "PS1=%TEMP%\F1_INSTALLA_ACCESSO_MOBILE_TAILSCALE.ps1"
set "NOCACHE=%RANDOM%%RANDOM%%RANDOM%"
set "URL=https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/INSTALLA_ACCESSO_MOBILE_TAILSCALE.ps1?nocache=%NOCACHE%"

echo.
echo F1 - ACCESSO PRIVATO LISTA_MATTINO DA TELEFONO
echo Questa configurazione si esegue una sola volta.
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} '%URL%' -OutFile '%PS1%'"
if errorlevel 1 goto :errore

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%PS1%\"'"
if errorlevel 1 goto :errore

echo.
echo CONFIGURAZIONE TERMINATA.
echo Sul Desktop trovi F1_LISTA_MATTINO_TELEFONO.txt con il link privato.
pause
exit /b 0

:errore
echo.
echo ERRORE. Mandami una foto del messaggio mostrato sopra.
pause
exit /b 1
