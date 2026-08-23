@echo off
setlocal EnableExtensions
title F1 INDIRIZZO REMOTO
set "INSTALL_ROOT=%LOCALAPPDATA%\F1IndirizzoRemoto"
set "APP_DIR=%INSTALL_ROOT%\app"
set "PYTHON_EXE=%INSTALL_ROOT%\venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" (
  echo F1 Indirizzo Remoto non e installato correttamente.
  echo Avvia prima INSTALLA.bat.
  pause
  exit /b 1
)
set "PYTHONPATH=%APP_DIR%\src"
set "F1_IR_HOME=%INSTALL_ROOT%"
"%PYTHON_EXE%" -m f1_indirizzo_remoto.app --open-browser
if errorlevel 1 (
  echo Avvio non riuscito. Esegui nuovamente INSTALLA.bat per autoriparare i componenti.
  pause
)
