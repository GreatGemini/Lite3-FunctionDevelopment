@echo off
cd /d "%~dp0project\desktop"
"%~dp0python\python.exe" -E -s -B main.py
if errorlevel 1 pause
