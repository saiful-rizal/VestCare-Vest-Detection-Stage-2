# Integrasi VestCare: YOLO, Fuzzy, Suara Browser, FastAPI, dan Cloudflare

Model lima kelas menganalisis gambar, hasil deteksi dinilai oleh fuzzy Sugeno, lalu browser di ponsel membacakan urgensi menggunakan Web Speech API. FastAPI menyajikan aplikasi dan API; Cloudflare Tunnel menyediakan HTTPS untuk akses kamera ponsel dari luar jaringan lokal.

## Alur sistem

1. Kamera ponsel mengirim gambar ke `POST /deteksi`.
2. YOLO memproses lima kelas: `pohon`, `mobil`, `motor`, `orang`, `lubang`.
3. Fuzzy Sugeno menghitung skor urgensi berdasarkan kelas, jarak, dan posisi objek.
4. API mengembalikan hasil JSON; halaman `/app` menampilkan hasil dan membacakan peringatan di ponsel.

Suara browser adalah keluaran utama. Server tidak memutar suara secara default. Endpoint opsional `POST /deteksi/suara` hanya memutar suara jika `VEST_TANPA_SUARA=0` dan perangkat server mendukungnya.

## Persiapan

Gunakan virtual environment proyek dan pasang dependensi yang sudah tercantum di `requirements.txt`:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Pastikan model terlatih tersedia di `models\best.pt` (atau tentukan `VEST_MODEL_PATH` pada `.env`). Salin konfigurasi contoh dan isi kunci API acak:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Salin hasil perintah ke `VEST_API_KEY` di `.env`. Kunci minimal 32 karakter wajib; contoh placeholder tidak diterima. Jangan bagikan atau commit `.env`.

## Menjalankan

Untuk lokal:

```powershell
.\run_server.bat
```

Alternatif menjalankan langsung dengan Uvicorn:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app:app --host 127.0.0.1 --port 8000
```

Buka `http://127.0.0.1:8000/app` di ponsel pada jaringan yang sama, atau di komputer yang menjalankan server. Dokumentasi API ada di `http://127.0.0.1:8000/docs`. Browser memerlukan HTTPS untuk kamera jarak jauh; `localhost` dapat dipakai untuk pengujian lokal.

Untuk Cloudflare Tunnel, pasang `cloudflared` dan opsional atur `CLOUDFLARED_TOKEN` di `.env`. Tanpa token, runner menggunakan Quick Tunnel dengan URL sementara. Jalankan:

```powershell
.\start_all.bat
```

Launcher memulai API hanya pada `127.0.0.1`, menunggu pemeriksaan status berhasil, kemudian menjalankan tunnel. Buka URL HTTPS yang dicetak Cloudflare dengan akhiran `/app`, masukkan `VEST_API_KEY`, lalu izinkan akses kamera dan suara.

URL publik juga disimpan otomatis ke `data/public_url.txt`. Dokumentasi API publik, contoh permintaan, dan kode error tersedia di [`API_CLOUDFLARE.md`](API_CLOUDFLARE.md).

## Endpoint

| Endpoint | Kegunaan | Kunci API |
|---|---|---|
| `GET /app` | Halaman kamera, hasil fuzzy, dan suara browser | Tidak |
| `GET /` dan `GET /status` | Informasi dan health check minimal | Tidak |
| `GET /docs` | Dokumentasi interaktif | Tidak |
| `POST /deteksi` | Gambar + jarak opsional → JSON deteksi dan urgensi | Wajib |
| `POST /deteksi/suara` | Deteksi dan opsi pemutaran suara di server | Wajib |
| `POST /peringatan` | Perhitungan fuzzy tanpa gambar | Wajib |
| `GET /riwayat` | Riwayat deteksi | Wajib |

Operasi API memerlukan header `X-API-Key`. Unggahan gambar dibatasi 10 MB. `/status` hanya memberi status proses dan tidak memuat detail konfigurasi rahasia.

Contoh permintaan:

```powershell
curl.exe -X POST http://127.0.0.1:8000/deteksi `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -F "gambar=@foto_jalan.jpg" `
  -F "jarak_m=0.45"
```

## Konfigurasi `.env`

- `VEST_API_KEY`: wajib, acak, minimal 32 karakter.
- `VEST_MODEL_PATH`: bobot YOLO; default `models\best.pt`.
- `VEST_IMGSZ`: ukuran inferensi; default 416.
- `VEST_CONF`: confidence minimum; default 0.35.
- `VEST_RIWAYAT_PATH`: lokasi riwayat JSONL.
- `VEST_TANPA_SUARA`: default `1`, suara diputar di browser, bukan server.
- `VEST_HOST` / `VEST_PORT`: default bind `127.0.0.1:8000`.
- `CLOUDFLARED_TOKEN`: opsional, untuk tunnel terkelola.

## Catatan keamanan

Jangan publikasikan server tanpa mengisi kunci kuat. Hindari membagikan URL tunnel dan kunci API; Quick Tunnel memberi URL acak tetapi bukan mekanisme autentikasi. HTTPS tunnel diperlukan untuk akses kamera ponsel dari jaringan publik.
