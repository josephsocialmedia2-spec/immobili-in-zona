@echo off
setlocal EnableExtensions
title F1 INDIRIZZO REMOTO - DISINSTALLAZIONE
echo Questa operazione rimuove il programma ma CONSERVA database, documenti ed esportazioni.
if not "%F1_IR_NONINTERACTIVE%"=="1" (
  choice /M "Continuare"
  if errorlevel 2 exit /b 0
)
set "INSTALL_ROOT=%LOCALAPPDATA%\F1IndirizzoRemoto"
set "DESKTOP_LINK=%USERPROFILE%\Desktop\F1 INDIRIZZO REMOTO.lnk"
if exist "%DESKTOP_LINK%" del "%DESKTOP_LINK%"
if exist "%INSTALL_ROOT%\app" rmdir /S /Q "%INSTALL_ROOT%\app"
if exist "%INSTALL_ROOT%\venv" rmdir /S /Q "%INSTALL_ROOT%\venv"
echo Programma rimosso. Dati conservati in F1IndirizzoRemoto nel profilo locale.
if not "%F1_IR_NONINTERACTIVE%"=="1" pause
