@echo off
REM =========================================================================
REM  VestCare - Jalankan FastAPI server (deteksi + fuzzy + suara)
REM =========================================================================
REM 1. Pakai virtual environment .venv jika ada
REM 2. Pastikan VEST_API_KEY sudah di-set (lihat .env.example)
REM 3. Pastikan bobot model ada: models/best.pt (hasil training train_semua.py)
REM 4. Jalankan: run_server.bat
REM =========================================================================

setlocal

cd /d "%~dp0"

REM Aktifkan venv jika tersedia
if exist ".venv\Scripts\activate.bat" (
    echo [INFO] Mengaktifkan virtual environment .venv
    call ".venv\Scripts\activate.bat"
) else (
    echo [PERINGATAN] .venv tidak ditemukan, pakai Python global.
)

REM Pastikan dependensi terpasang
echo [INFO] Memeriksa dependensi...
pip install -r requirements.txt >nul 2>&1

REM Cek bobot model
if not exist "models\best.pt" (
    echo [PERINGATAN] models\best.pt belum ada. Jalankan training dulu (start_train.py).
    echo               API tetap akan nyala tapi /deteksi akan error 503 sampai model tersedia.
)

echo [INFO] Memulai FastAPI server di http://0.0.0.0:8000
echo [INFO] Dokumentasi: http://localhost:8000/docs
echo [INFO] Tekan Ctrl+C untuk menghentikan.
echo.

python server_rest_api.py

endlocal
