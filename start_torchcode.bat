@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-web.ps1" %*
set "TORCHCODE_EXIT_CODE=%ERRORLEVEL%"
if not "%TORCHCODE_EXIT_CODE%"=="0" pause
exit /b %TORCHCODE_EXIT_CODE%
