@echo off
REM =========================================================================
REM  VestCare - Publikasi API lewat Cloudflare Tunnel (cloudflared)
REM =========================================================================
REM Prasyarat:
REM   1. cloudflared terpasang (unduh dari https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
REM 2. FastAPI server sudah berjalan pada 127.0.0.1:8000
REM 3. Isi VEST_API_KEY dalam .env. CLOUDFLARED_TOKEN bersifat opsional;
REM    tanpa token, runner memakai Quick Tunnel dengan URL sementara.
REM =========================================================================

setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment .venv tidak ditemukan.
    exit /b 1
)

echo [INFO] Memulai Cloudflare Tunnel dari konfigurasi .env ...
echo [INFO] Tekan Ctrl+C untuk menghentikan tunnel.
echo.

".venv\Scripts\python.exe" start_tunnel.py

endlocal
