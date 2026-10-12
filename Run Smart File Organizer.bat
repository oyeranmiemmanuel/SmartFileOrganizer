@echo off
cd /d "%~dp0"
py smart_file_organizer.py
if errorlevel 1 python smart_file_organizer.py
pause
