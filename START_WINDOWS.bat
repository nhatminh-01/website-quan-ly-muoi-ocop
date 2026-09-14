@echo off
chcp 65001 > nul
setlocal
rem Cach dung:
rem   START_WINDOWS.bat       = dung server cu roi khoi dong server moi
rem   START_WINDOWS.bat stop  = chi dung server, khong khoi dong lai
set "APP_DIR=%~dp0"
set "PYTHON_EXE=%APP_DIR%database\.venv\Scripts\python.exe"
set "STOP_ONLY=0"
if /I "%~1"=="stop" set "STOP_ONLY=1"
if /I "%~1"=="/stop" set "STOP_ONLY=1"

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
rem Web server mặc định chạy ở cổng 8080. Có thể ghi đè bằng SALT_WEB_PORT trong file .env.
set "WEB_PORT=8080"
for /f "usebackq tokens=1,* delims==" %%A in ("%PTNT_DB_ENV_FILE%") do (
  if /I "%%A"=="SALT_WEB_PORT" set "WEB_PORT=%%B"
)

echo [1/5] Dung server web dang chay tren cong %WEB_PORT%...
set "STOP_FAILED="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%WEB_PORT% .*LISTENING"') do (
  if not "%%P"=="0" (
    echo Dang dung tien trinh web PID %%P...
    taskkill /PID %%P /T /F >nul 2>&1
    if errorlevel 1 (
      echo Khong the dung PID %%P. Tien trinh co the dang chay bang quyen Administrator.
      set "STOP_FAILED=1"
    )
  )
)
if defined STOP_FAILED (
  echo Khong the dung mot tien trinh dang chiem cong %WEB_PORT%.
  echo Hay chay START_WINDOWS.bat stop bang quyen Administrator, sau do chay lai file nay.
  pause
  exit /b 1
)
timeout /t 1 /nobreak >nul
if "%STOP_ONLY%"=="1" (
  echo Da dung server web. Khong khoi dong lai.
  exit /b 0
)

if /I "%DB_ENV_LABEL%"=="local" (
  echo [2/5] Kiem tra dich vu PostgreSQL local...
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
  echo [2/5] Bo qua service local; production se duoc kiem tra qua ket noi TCP...
)

echo [3/5] Kiem tra va ap dung migration PostgreSQL con thieu...
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

echo [4/5] Kiem tra ket noi database...
"%PYTHON_EXE%" -c "from backend_db import healthcheck; print(healthcheck())"
if errorlevel 1 (
  echo Khong ket noi duoc PostgreSQL. Kiem tra %DB_ENV_LABEL% va mang LAN.
  pause
  exit /b 1
)
echo [5/5] Khoi dong web server tai cong %WEB_PORT%...
"%PYTHON_EXE%" server.py
pause
