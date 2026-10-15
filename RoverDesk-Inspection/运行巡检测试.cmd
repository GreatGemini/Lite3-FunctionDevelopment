@echo off
chcp 65001 >nul
cd /d "%~dp0"
set QT_QPA_PLATFORM=offscreen
"%~dp0..\python\python.exe" -E -s -B -m unittest discover -s tests -v
pause
