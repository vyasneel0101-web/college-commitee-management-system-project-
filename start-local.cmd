@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing virtual environment. See docs\LOCAL_SETUP.md.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000
pause
