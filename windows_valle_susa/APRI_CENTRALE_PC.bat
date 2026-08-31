@echo off
setlocal EnableExtensions
chcp 65001 >nul
title F1 - Apri Centrale Telefonate

set "AUTODIR=%LOCALAPPDATA%\F1Radar"
set "BASE=%USERPROFILE%\Documents\F1_Directory_Microzone"
set "SERVER=%AUTODIR%\f1_mobile_server.py"
set "GENERATOR=%AUTODIR%\centrale_telefonate_guidate.py"
set "SERVER_URL=https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/f1_mobile_server.py"
set "GENERATOR_URL=https://raw.githubusercontent.com/josephsocialmedia2-spec/immobili-in-zona/main/windows_valle_susa/centrale_telefonate_guidate.py"
set "HEALTH=http://127.0.0.1:8766/health"
set "CENTRALE=http://127.0.0.1:8766/"

if not exist "%AUTODIR%" mkdir "%AUTODIR%" >nul 2>&1
if not exist "%BASE%" mkdir "%BASE%" >nul 2>&1

where py.exe >nul 2>&1
if errorlevel 1 (
  echo ERRORE: Python non risulta disponibile tramite il comando py.exe.
  echo La Centrale non puo essere avviata.
  pause
  exit /b 1
)

echo Aggiornamento componenti F1...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} '%SERVER_URL%' -OutFile '%SERVER%' } catch { if(-not (Test-Path '%SERVER%')){ exit 1 } }"
if errorlevel 1 goto :download_error
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference='SilentlyContinue'; try { Invoke-WebRequest -UseBasicParsing -Headers @{'Cache-Control'='no-cache'} '%GENERATOR_URL%' -OutFile '%GENERATOR%' } catch { if(-not (Test-Path '%GENERATOR%')){ exit 1 } }"
if errorlevel 1 goto :download_error

echo Aggiornamento lista Centrale...
py "%GENERATOR%"
if errorlevel 1 (
  echo ATTENZIONE: generazione lista non completata. Provo comunque ad aprire l'ultima Centrale valida.
)

call :healthcheck
if not errorlevel 1 goto :open

echo Avvio server Centrale...
start "F1 Centrale Server" /min py "%SERVER%"

for /L %%I in (1,1,30) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH%' -TimeoutSec 1; if($r.StatusCode -eq 200 -and $r.Content.Trim() -eq 'OK'){exit 0} } catch {}; exit 1" >nul 2>&1
  if not errorlevel 1 goto :open
  powershell -NoProfile -Command "Start-Sleep -Milliseconds 500" >nul 2>&1
)

echo.
echo ERRORE: la Centrale non risponde sulla porta 8766.
echo Non apro una pagina non funzionante.
echo Controlla Windows Firewall e il processo Python F1Radar.
pause
exit /b 2

:open
echo Centrale ONLINE. Apertura...
start "" "%CENTRALE%"
exit /b 0

:healthcheck
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri '%HEALTH%' -TimeoutSec 1; if($r.StatusCode -eq 200 -and $r.Content.Trim() -eq 'OK'){exit 0} } catch {}; exit 1" >nul 2>&1
exit /b %errorlevel%

:download_error
echo.
echo ERRORE: impossibile scaricare i componenti F1 e nessuna copia locale valida e disponibile.
pause
exit /b 3
