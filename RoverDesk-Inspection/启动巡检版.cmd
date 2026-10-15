@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 goto launch_error
"..\python\python.exe" -E -s -B main.py --mcp-port 8776 %*
set "rover_exit=%errorlevel%"
if not "%rover_exit%"=="0" goto launch_error
exit /b 0
:launch_error
echo Rover Desk could not start. Please copy the error message above.
pause
exit /b 1
