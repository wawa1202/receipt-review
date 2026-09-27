@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. Please follow README.md to set up the environment.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m receipt_review.launcher
if errorlevel 1 pause
