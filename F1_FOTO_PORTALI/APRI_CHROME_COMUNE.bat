@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "URL=%~1"
if not defined URL set "URL=https://www.google.it/"

set "CHROME="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "CHROME=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined CHROME if exist "%LocalAppData%\Google\Chrome\Application\chrome.exe" set "CHROME=%LocalAppData%\Google\Chrome\Application\chrome.exe"

if not defined CHROME (
    echo Google Chrome non trovato.
    echo Installa Google Chrome e riprova.
    pause
    exit /b 1
)

set "PROFILE=%~dp0profilo_chrome_portali"

start "" "%CHROME%" ^
 --remote-debugging-port=9222 ^
 --remote-allow-origins=* ^
 --user-data-dir="%PROFILE%" ^
 --start-maximized ^
 --no-first-run ^
 "%URL%"

exit /b 0
