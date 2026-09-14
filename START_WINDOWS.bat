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
echo [1/4] Kiem tra dich vu PostgreSQL...
sc query postgresql-x64-17 | findstr /I "RUNNING" > nul
if errorlevel 1 (
  echo PostgreSQL chua chay, dang thu khoi dong...
  net start postgresql-x64-17
  if errorlevel 1 (
    echo Khong the khoi dong PostgreSQL. Hay chay file nay bang quyen Administrator
    echo hoac mo Services va Start service postgresql-x64-17.
    pause
    exit /b 1
  )
)

echo [2/4] Kiem tra va ap dung migration PostgreSQL con thieu...
"%PYTHON_EXE%" database\migration\apply_pending.py
if errorlevel 1 (
  echo Migration that bai. Kiem tra database\.env va quyen PostgreSQL.
  pause
  exit /b 1
)

echo [3/4] Kiem tra ket noi database...
"%PYTHON_EXE%" -c "from backend_db import healthcheck; print(healthcheck())"
if errorlevel 1 (
  echo Khong ket noi duoc PostgreSQL. Kiem tra database\.env va mang LAN.
  pause
  exit /b 1
)
echo [4/4] Khoi dong web server...
"%PYTHON_EXE%" server.py
pause
