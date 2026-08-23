@echo off
setlocal
set "BASE_DIR=%LOCALAPPDATA%\F1IndirizzoRemoto"
set "APP_DIR=%BASE_DIR%\app"
set "PYTHON_EXE=%BASE_DIR%\venv\Scripts\python.exe"
set "PYTHONPATH=%APP_DIR%\src"
if not exist "%PYTHON_EXE%" (
  echo Installazione non trovata.
  pause
  exit /b 1
)
"%PYTHON_EXE%" -m f1_indirizzo_remoto.app --self-test
echo.
echo Il controllo non legge ne esporta pratiche reali.
pause
