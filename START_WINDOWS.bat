@echo off
chcp 65001 > nul
setlocal
set "APP_DIR=%~dp0"
set "PYTHON_EXE=%APP_DIR%database\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" set "PYTHON_EXE=%APP_DIR%..\DB\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Khong tim thay moi truong Python.
  echo Hay cai dat theo database\README.md
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
"%PYTHON_EXE%" server.py
pause
