@echo off
chcp 65001 > nul
setlocal
set "APP_DIR=%~dp0"
set "PYTHON_EXE=%APP_DIR%database\.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
  echo Khong tim thay moi truong Python.
  echo Hay chay: python -m venv database\.venv
  echo Sau do: database\.venv\Scripts\python.exe -m pip install -r database\requirements.txt
  pause
  exit /b 1
)

if not exist "%APP_DIR%database\.env" (
  echo Chua co database\.env.
  echo Hay sao chep database\.env.example thanh database\.env va dien mat khau.
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
"%PYTHON_EXE%" -c "from backend_db import healthcheck; print(healthcheck())"
if errorlevel 1 (
  echo Khong ket noi duoc PostgreSQL. Kiem tra database\.env va mang LAN.
  pause
  exit /b 1
)
"%PYTHON_EXE%" server.py
pause
