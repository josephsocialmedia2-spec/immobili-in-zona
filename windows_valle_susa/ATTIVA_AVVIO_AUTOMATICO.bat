@echo off
setlocal
chcp 65001 >nul
title F1 - Attiva avvio automatico Radar
set "PS1=%TEMP%\F1_ATTIVA_AVVIO_AUTOMATICO.ps1"
set "NOCACHE=%RANDOM%%RANDOM%%RANDOM%"
set "URL=https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/ATTIVA_AVVIO_AUTOMATICO.ps1?nocache=%NOCACHE%"
echo.
echo F1 - ATTIVAZIONE AVVIO AUTOMATICO
 echo Questa operazione si esegue UNA VOLTA SOLA.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} '%URL%' -OutFile '%PS1%'"
if errorlevel 1 goto :errore
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%"
if errorlevel 1 goto :errore
echo.
echo COMPLETATO: da ora il runner F1 parte automaticamente con Windows.
echo Non dovrai piu aprire run.cmd manualmente.
pause
exit /b 0
:errore
echo.
echo ERRORE. Leggi il messaggio sopra e mandami una foto della finestra.
pause
exit /b 1
