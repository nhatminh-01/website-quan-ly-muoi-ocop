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

if exist "%APP_DIR%database\.env.production" (
  set "PTNT_DB_ENV_FILE=%APP_DIR%database\.env.production"
  set "DB_ENV_LABEL=production"
) else if exist "%APP_DIR%database\.env" (
  set "PTNT_DB_ENV_FILE=%APP_DIR%database\.env"
  set "DB_ENV_LABEL=local"
) else (
  echo Chua co database\.env hoac database\.env.production.
  echo Hay tao mot trong hai tep tu database\.env.example va dien mat khau.
  pause
  exit /b 1
)

cd /d "%APP_DIR%"
if /I "%DB_ENV_LABEL%"=="local" (
  echo [1/4] Kiem tra dich vu PostgreSQL local...
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
) else (
  echo [1/4] Bo qua service local; production se duoc kiem tra qua ket noi TCP...
)

echo [2/4] Kiem tra va ap dung migration PostgreSQL con thieu...
if /I "%DB_ENV_LABEL%"=="production" (
  "%PYTHON_EXE%" database\migration\bootstrap_production.py --env-file "%PTNT_DB_ENV_FILE%"
  if errorlevel 1 (
    echo Bootstrap production that bai. Khong tu dong ghi de du lieu.
    pause
    exit /b 1
  )
)
"%PYTHON_EXE%" database\migration\apply_pending.py
if errorlevel 1 (
  echo Migration that bai. Kiem tra %DB_ENV_LABEL% va quyen PostgreSQL.
  pause
  exit /b 1
)

echo [3/4] Kiem tra ket noi database...
"%PYTHON_EXE%" -c "from backend_db import healthcheck; print(healthcheck())"
if errorlevel 1 (
  echo Khong ket noi duoc PostgreSQL. Kiem tra %DB_ENV_LABEL% va mang LAN.
  pause
  exit /b 1
)
echo [4/4] Khoi dong web server...
"%PYTHON_EXE%" server.py
pause
