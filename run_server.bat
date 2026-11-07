@echo off
REM =========================================================================
REM  VestCare - Jalankan FastAPI server untuk browser dan API
REM =========================================================================
REM 1. Pastikan dependensi sudah tersedia di .venv
REM 2. Salin .env.example menjadi .env dan isi VEST_API_KEY
REM 3. Pastikan bobot hasil training tersedia di models\best.pt
REM 4. Jalankan: run_server.bat
REM =========================================================================

setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Python virtual environment .venv tidak ditemukan.
    echo         Buat venv dan install requirements.txt terlebih dahulu.
    exit /b 1
)

echo [INFO] Memulai FastAPI server di http://127.0.0.1:8000
echo [INFO] Dokumentasi: http://localhost:8000/docs
echo [INFO] Aplikasi kamera ponsel: http://localhost:8000/app
echo [INFO] Tekan Ctrl+C untuk menghentikan.
echo.

".venv\Scripts\python.exe" start_server.py

endlocal
