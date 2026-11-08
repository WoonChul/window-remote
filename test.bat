@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" call setup.bat || exit /b 1
".venv\Scripts\python.exe" -m pytest -q %*
pause
