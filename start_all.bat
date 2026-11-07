@echo off
REM =========================================================================
REM  VestCare - Jalankan server FastAPI + Cloudflare Tunnel sekaligus
REM =========================================================================
REM Catatan: Server dan tunnel berjalan di jendela terpisah (start).
REM Pastikan VEST_API_KEY dan CLOUDFLARED_TOKEN sudah di-set.
REM =========================================================================

setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [PERINGATAN] .venv tidak ditemukan.
) else (
    call ".venv\Scripts\activate.bat"
)

pip install -r requirements.txt >nul 2>&1

echo [INFO] Menjalankan FastAPI server (jendela 1)...
start "VestCare Server" cmd /k "python server_rest_api.py"

timeout /t 3 >nul

if defined CLOUDFLARED_TOKEN (
    echo [INFO] Menjalankan Cloudflare Tunnel (jendela 2)...
    start "VestCare Tunnel" cmd /k "cloudflared tunnel --token %CLOUDFLARED_TOKEN% --url http://localhost:8000"
) else (
    echo [PERINGATAN] CLOUDFLARED_TOKEN belum di-set. Tunnel tidak dijalankan.
    echo              Set dulu: set CLOUDFLARED_TOKEN=token-anda
)

echo.
echo [INFO] Selesai. Buka http://localhost:8000/docs untuk mencoba API.
echo [INFO] URL publik akan muncul di jendela tunnel.
pause

endlocal
