@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>&1
if not errorlevel 1 (
  py -3 -u server.py --port 8000
  pause
  exit /b
)
where python >nul 2>&1
if not errorlevel 1 (
  python -u server.py --port 8000
  pause
  exit /b
)
echo Python 3 is required. Install Python, then run this file again.
pause
