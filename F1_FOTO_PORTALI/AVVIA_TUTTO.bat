@echo off
setlocal EnableExtensions
cd /d "%~dp0"

call "%~dp0APRI_IMMOBILIARE.bat"
timeout /t 2 /nobreak >nul
call "%~dp0APRI_CASA_IT.bat"
timeout /t 2 /nobreak >nul
call "%~dp0APRI_IDEALISTA.bat"
timeout /t 4 /nobreak >nul
call "%~dp0AVVIA_FOTO_3_PORTALI.bat"
