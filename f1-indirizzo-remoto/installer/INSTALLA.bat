@echo off
setlocal EnableExtensions
title F1 INDIRIZZO REMOTO - INSTALLAZIONE
color 0A

set "SOURCE_ROOT=%~dp0.."
set "INSTALL_ROOT=%LOCALAPPDATA%\F1IndirizzoRemoto"
set "APP_DIR=%INSTALL_ROOT%\app"
set "VENV_DIR=%INSTALL_ROOT%\venv"
set "DIAG_DIR=%INSTALL_ROOT%\diagnostics"

if not "%OS%"=="Windows_NT" goto :wrong_os
if not defined PROCESSOR_ARCHITECTURE goto :wrong_arch
echo Architettura rilevata: %PROCESSOR_ARCHITECTURE%
if not exist "%INSTALL_ROOT%" mkdir "%INSTALL_ROOT%"
if not exist "%APP_DIR%" mkdir "%APP_DIR%"
if not exist "%DIAG_DIR%" mkdir "%DIAG_DIR%"

where py >nul 2>nul
if %errorlevel%==0 (
  set "PYTHON_CMD=py -3"
) else (
  where python >nul 2>nul
  if errorlevel 1 goto :no_python
  set "PYTHON_CMD=python"
)
%PYTHON_CMD% -c "import sys; raise SystemExit(0 if sys.version_info >= (3,12) else 1)"
if errorlevel 1 goto :old_python

echo [1/6] Copia applicazione...
robocopy "%SOURCE_ROOT%" "%APP_DIR%" /E /R:2 /W:2 /XD .git .venv data uploads exports letters backups diagnostics dist build /XF .env *.db *.sqlite *.sqlite3 *.log >nul
if errorlevel 8 goto :copy_error

echo [2/6] Prepara ambiente Python...
if not exist "%VENV_DIR%\Scripts\python.exe" %PYTHON_CMD% -m venv "%VENV_DIR%"
if not exist "%VENV_DIR%\Scripts\python.exe" goto :venv_error

echo [3/6] Installa componenti...
"%VENV_DIR%\Scripts\python.exe" -m pip install --disable-pip-version-check --upgrade pip >nul
if errorlevel 1 goto :dependency_error
"%VENV_DIR%\Scripts\python.exe" -m pip install --disable-pip-version-check -r "%APP_DIR%\requirements.txt" >nul
if errorlevel 1 goto :dependency_error

echo [4/6] Inizializza cartelle locali...
if not exist "%INSTALL_ROOT%\data" mkdir "%INSTALL_ROOT%\data"
if not exist "%INSTALL_ROOT%\uploads" mkdir "%INSTALL_ROOT%\uploads"
if not exist "%INSTALL_ROOT%\exports" mkdir "%INSTALL_ROOT%\exports"
if not exist "%INSTALL_ROOT%\letters" mkdir "%INSTALL_ROOT%\letters"
if not exist "%INSTALL_ROOT%\backups" mkdir "%INSTALL_ROOT%\backups"
set "PYTHONPATH=%APP_DIR%\src"
set "F1_IR_HOME=%INSTALL_ROOT%"
"%VENV_DIR%\Scripts\python.exe" -c "from f1_indirizzo_remoto.app import create_app; create_app()"
if errorlevel 1 goto :database_error

echo [5/6] Esegue self-test...
"%VENV_DIR%\Scripts\python.exe" -m f1_indirizzo_remoto.app --self-test >"%DIAG_DIR%\self-test.txt" 2>&1
if errorlevel 1 goto :selftest_error

echo [6/6] Crea icona Desktop...
powershell -NoProfile -ExecutionPolicy Bypass -File "%APP_DIR%\installer\CREA_ICONA_DESKTOP.ps1"
if errorlevel 1 goto :shortcut_error

echo.
echo ==========================================
echo INSTALLAZIONE COMPLETATA
echo Usa l'icona F1 INDIRIZZO REMOTO sul Desktop.
echo ==========================================
if not "%F1_IR_NONINTERACTIVE%"=="1" pause
exit /b 0

:wrong_os
echo ERRORE: questo installer richiede Windows.
goto :failed
:wrong_arch
echo ERRORE: architettura Windows non rilevata.
goto :failed
:no_python
echo ERRORE: Python 3.12 o superiore non trovato. Installa Python da python.org selezionando Add Python to PATH.
goto :failed
:old_python
echo ERRORE: e richiesto Python 3.12 o superiore. Aggiorna Python e riprova.
goto :failed
:copy_error
echo ERRORE durante la copia dell'applicazione.
goto :failed
:venv_error
echo ERRORE durante la creazione dell'ambiente Python.
goto :failed
:dependency_error
echo ERRORE durante l'installazione dei componenti. Controlla la connessione Internet e riprova.
goto :failed
:database_error
echo ERRORE durante l'inizializzazione del database locale. I dati esistenti non sono stati cancellati.
goto :failed
:selftest_error
echo ERRORE: self-test non superato. Il file diagnostico non contiene pratiche o documenti personali.
goto :failed
:shortcut_error
echo ERRORE durante la creazione dell'icona Desktop.
goto :failed
:failed
echo INSTALLAZIONE NON COMPLETATA.
if not "%F1_IR_NONINTERACTIVE%"=="1" pause
exit /b 1
