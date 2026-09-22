@echo off
cd /d "%~dp0"
echo STOP>"%~dp0STOP.txt"
echo Richiesta di arresto inviata.
echo Il programma si fermera in sicurezza entro pochi secondi.
timeout /t 3 /nobreak >nul
