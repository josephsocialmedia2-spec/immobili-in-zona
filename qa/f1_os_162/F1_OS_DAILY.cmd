@echo off
setlocal EnableExtensions
chcp 65001 >nul
set "DEST=%LOCALAPPDATA%\F1_OS_Immobiliare"
set "APP=%DEST%\F1_OS_Immobiliare.pyw"
set "LOG=%APPDATA%\F1_OS_Immobiliare\daily_task_stdout.log"
if not exist "%APP%" exit /b 20
cd /d "%DEST%"
set "PY="
for /f "delims=" %%P in ('where py.exe 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY for /f "delims=" %%P in ('where python.exe 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY for /f "delims=" %%P in ('where pyw.exe 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do if not defined PY set "PY=%%P"
if not defined PY exit /b 21
"%PY%" "%APP%" --daily-flow >> "%LOG%" 2>&1
exit /b %ERRORLEVEL%
