@echo off
setlocal
chcp 65001 > nul
cd /d "%~dp0"
set "OCOP_PYTHON=python"
python --version > nul 2>&1
if errorlevel 1 set "OCOP_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
"%OCOP_PYTHON%" --version > nul 2>&1
if errorlevel 1 (
    echo Khong tim thay Python. Can cai Python 3.11 tro len va them vao PATH.
    pause
    exit /b 1
)
if not exist "salt_management_TEST.db" (
    echo Chua co salt_management_TEST.db. Hay chay python prepare_ocop_test.py truoc.
    pause
    exit /b 1
)
"%OCOP_PYTHON%" migrate_roles.py --db "salt_management_TEST.db"
if errorlevel 1 (
    pause
    exit /b 1
)
"%OCOP_PYTHON%" migrate_ocop.py --db "salt_management_TEST.db"
if errorlevel 1 (
    pause
    exit /b 1
)
"%OCOP_PYTHON%" server.py --db "salt_management_TEST.db" --skip-legacy-sync --host 127.0.0.1 --port 8081
pause
