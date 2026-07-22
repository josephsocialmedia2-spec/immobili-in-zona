@echo off
setlocal EnableExtensions
cd /d "%~dp0"

if exist "%~dp0STOP.txt" del /q "%~dp0STOP.txt" >nul 2>&1

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
    echo Esegui INSTALLA_COMPONENTI.bat.
    pause
    exit /b 1
)

%PYEXE% "%~dp0fotografa_portali.py"
