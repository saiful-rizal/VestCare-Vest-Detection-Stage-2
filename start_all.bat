@echo off
REM =========================================================================
REM  VestCare - Jalankan server FastAPI + Cloudflare Tunnel sekaligus
REM =========================================================================
REM Server dan tunnel berjalan di jendela terpisah.
REM Isi VEST_API_KEY pada .env terlebih dahulu.
REM =========================================================================

setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment .venv tidak ditemukan.
    exit /b 1
)

".venv\Scripts\python.exe" -c "from config_env import load_project_env,api_key_is_configured; import os; load_project_env(); raise SystemExit(0 if api_key_is_configured(os.environ.get('VEST_API_KEY')) else 1)"
if errorlevel 1 (
    echo [ERROR] Isi .env dengan VEST_API_KEY acak minimal 32 karakter terlebih dahulu.
    exit /b 1
)

echo [INFO] Menjalankan FastAPI server (jendela 1)...
start "VestCare Server" "%ComSpec%" /k ""%~dp0run_server.bat""

echo [INFO] Menunggu server siap...
set "SERVER_READY="
for /L %%I in (1,1,60) do (
    curl.exe --silent --fail http://127.0.0.1:8000/status >nul 2>&1
    if not errorlevel 1 (
        set "SERVER_READY=1"
        goto :server_ready
    )
    timeout /t 2 /nobreak >nul
)

:server_ready
if not defined SERVER_READY (
    echo [ERROR] Server tidak siap dalam 120 detik. Tunnel tidak dijalankan.
    exit /b 1
)

echo [INFO] Server siap. Menjalankan Cloudflare Tunnel (jendela 2)...
start "VestCare Tunnel" "%ComSpec%" /k ""%~dp0run_tunnel.bat""

echo.
echo [INFO] Aplikasi ponsel lokal: http://localhost:8000/app
echo [INFO] URL publik akan muncul di jendela tunnel.

endlocal
