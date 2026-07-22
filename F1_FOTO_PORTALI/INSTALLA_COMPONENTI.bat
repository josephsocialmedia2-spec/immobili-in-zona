@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==============================================================
echo INSTALLAZIONE F1 FOTO PORTALI
echo ==============================================================
echo.

set "PYEXE="
where py >nul 2>&1
if not errorlevel 1 set "PYEXE=py -3"

if not defined PYEXE (
    where python >nul 2>&1
    if not errorlevel 1 set "PYEXE=python"
)

if not defined PYEXE (
    for /d %%D in ("%LocalAppData%\Programs\Python\Python*") do (
        if exist "%%~fD\python.exe" set "PYEXE=%%~fD\python.exe"
    )
)

if not defined PYEXE (
    echo Python 3 non trovato.
    echo Installa Python 3 dal Microsoft Store oppure da python.org.
    echo Durante l'installazione seleziona ADD PYTHON TO PATH.
    pause
    exit /b 1
)

%PYEXE% -m pip install --upgrade pip
%PYEXE% -m pip install --upgrade requests websocket-client pillow

if errorlevel 1 (
    echo.
    echo Installazione non riuscita.
    pause
    exit /b 1
)

echo.
echo Installazione completata.
echo.
echo Ordine consigliato:
echo 1. APRI_IMMOBILIARE.bat
echo 2. APRI_CASA_IT.bat
echo 3. APRI_IDEALISTA.bat
echo 4. AVVIA_FOTO_3_PORTALI.bat
pause
