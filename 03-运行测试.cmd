@echo off
cd /d "%~dp0project\desktop"
set QT_QPA_PLATFORM=offscreen
"%~dp0python\python.exe" -E -s -B -m unittest discover -s tests -v
pause
