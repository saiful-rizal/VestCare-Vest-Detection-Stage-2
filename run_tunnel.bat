@echo off
REM =========================================================================
REM  VestCare - Publikasi API lewat Cloudflare Tunnel (cloudflared)
REM =========================================================================
REM Prasyarat:
REM   1. cloudflared terpasang (unduh dari https://developers.cloudflare.com/cloudflare-one/connections/connect-apps/)
REM 2. FastAPI server sudah berjalan (run_server.bat) di port 8000
REM 3. Buat token di Cloudflare Zero Trust Dashboard (Access > Tunnels) lalu set:
REM      set CLOUDFLARED_TOKEN=...
REM    atau gunakan config file cloudflared.yml
REM =========================================================================

setlocal

cd /d "%~dp0"

if not defined CLOUDFLARED_TOKEN (
    echo [PERINGATAN] CLOUDFLARED_TOKEN belum di-set.
    echo              Contoh PowerShell: $env:CLOUDFLARED_TOKEN="token-anda"
    echo              Atau edit cloudflared.yml lalu jalankan: cloudflared --config cloudflared.yml tunnel --token ...
    echo.
)

echo [INFO] Membangun tunnel ke http://localhost:8000 ...
echo [INFO] Publikasi akan menghasilkan URL publik (https://xxxx.trycloudflare.com atau domain Anda)
echo [INFO] Tekan Ctrl+C untuk menghentikan tunnel.
echo.

REM Pilihan A: quick tunnel (tanpa akun, URL acak) - cocok uji coba
REM cloudflared tunnel --url http://localhost:8000

REM Pilihan B: dengan token (URL stabil, direkomendasikan)
cloudflared tunnel --token %CLOUDFLARED_TOKEN% --url http://localhost:8000

endlocal
