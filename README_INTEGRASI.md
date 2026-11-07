# Integrasi VestCare: YOLO, Fuzzy, Suara Browser, FastAPI, dan Cloudflare

Model lima kelas menganalisis gambar, hasil deteksi dinilai oleh fuzzy Sugeno, lalu browser di ponsel memutar klip suara Ardi dari `suara-natural-ai/cache_ardi` sesuai tingkat urgensi. FastAPI menyajikan aplikasi dan API; Cloudflare Tunnel menyediakan HTTPS untuk akses kamera ponsel dari luar jaringan lokal.

## Alur sistem

1. Kamera ponsel mengirim gambar ke `POST /deteksi` memakai cookie sesi dari `/app`.
2. YOLO memproses lima kelas: `pohon`, `mobil`, `motor`, `orang`, `lubang`.
3. Fuzzy Sugeno menghitung skor urgensi berdasarkan kelas, jarak, dan posisi objek.
4. API mengembalikan hasil JSON beserta rencana `suara`: daftar segmen klip Ardi yang sesuai level fuzzy.
5. Halaman `/app` menampilkan hasil dan memutar segmen MP3 tersebut secara berurutan.

Suara browser adalah keluaran utama dan memakai klip Ardi, bukan Web Speech API. Server tidak memutar suara secara default. Endpoint opsional `POST /deteksi/suara` hanya memutar suara jika `VEST_TANPA_SUARA=0` dan perangkat server mendukungnya.

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

Buka `http://127.0.0.1:8000/app` di komputer yang menjalankan server. Untuk ponsel, gunakan URL HTTPS Cloudflare pada bagian berikutnya. Dokumentasi API ada di `http://127.0.0.1:8000/docs`. Browser memerlukan HTTPS untuk kamera jarak jauh; `localhost` dapat dipakai untuk pengujian lokal.

Untuk Cloudflare Tunnel, pasang `cloudflared` dan opsional atur `CLOUDFLARED_TOKEN` di `.env`. Tanpa token, runner menggunakan Quick Tunnel dengan URL sementara. Jalankan:

```powershell
.\start_all.bat
```

Launcher memulai API hanya pada `127.0.0.1`, menunggu pemeriksaan status berhasil, kemudian menjalankan tunnel. Buka URL HTTPS yang dicetak Cloudflare dengan akhiran `/app`, lalu izinkan akses kamera dan suara. Halaman tidak meminta API key karena server menerbitkan cookie sesi otomatis.

Pada halaman `/app`, ikuti urutan ini di ponsel:

1. Tekan **Tes suara Ardi** dan pastikan suara tes terdengar; naikkan volume media jika perlu.
2. Tekan **Aktifkan kamera belakang** dan izinkan akses kamera.
3. Tekan **Deteksi dan putar suara Ardi**. Hasil deteksi, level fuzzy, dan teks suara tampil di halaman.
4. Suara Ardi diputar otomatis sesuai level: AMAN, INFO, WASPADA, atau BAHAYA.
5. Jika ingin mengulang, tekan **Putar ulang suara terakhir**.

Browser ponsel dapat memblokir audio otomatis sebelum ada sentuhan pengguna, karena itu tombol tes suara disediakan. Jika halaman menampilkan `401`, muat ulang `/app` agar cookie sesi diperbarui. Untuk kamera, gunakan URL HTTPS Cloudflare, bukan alamat HTTP dari jaringan luar.

URL publik juga disimpan otomatis ke `data/public_url.txt`. Dokumentasi API publik, contoh permintaan, dan kode error tersedia di [`API_CLOUDFLARE.md`](API_CLOUDFLARE.md).

## Endpoint

| Endpoint | Kegunaan | Autentikasi |
|---|---|---|
| `GET /app` | Halaman kamera, hasil fuzzy, dan suara Ardi | Tidak |
| `GET /` dan `GET /status` | Informasi dan health check minimal | Tidak |
| `GET /docs` | Dokumentasi interaktif | Tidak |
| `POST /deteksi` | Gambar + jarak opsional → JSON deteksi, urgensi, dan rencana suara | Header atau cookie |
| `POST /deteksi/suara` | Deteksi dan opsi pemutaran suara di server | Header atau cookie |
| `POST /peringatan` | Perhitungan fuzzy tanpa gambar | Header atau cookie |
| `GET /riwayat` | Riwayat deteksi | Header atau cookie |
| `GET /suara/pratinjau` | Rencana suara contoh untuk tes browser | Header atau cookie |
| `GET /suara/{berkas}` | Berkas MP3 Ardi untuk diputar browser | Header atau cookie |

Klien API memakai header `X-API-Key`. Halaman `/app` memakai cookie sesi `HttpOnly` yang ditandatangani HMAC dan diterbitkan saat halaman dibuka, sehingga pengguna ponsel tidak perlu mengetik kunci. Unggahan gambar dibatasi 10 MB. `/status` hanya memberi status proses dan tidak memuat detail konfigurasi rahasia.

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
- `VEST_SUARA_FOLDER`: pustaka klip Ardi; default `suara-natural-ai/cache_ardi`.
- `VEST_IMGSZ`: ukuran inferensi; default 416.
- `VEST_CONF`: confidence minimum; default 0.35.
- `VEST_RIWAYAT_PATH`: lokasi riwayat JSONL.
- `VEST_TANPA_SUARA`: default `1`, suara diputar di browser, bukan server.
- `VEST_HOST` / `VEST_PORT`: default bind `127.0.0.1:8000`.
- `CLOUDFLARED_TOKEN`: opsional, untuk tunnel terkelola.

## Catatan keamanan

Jangan publikasikan server tanpa mengisi kunci kuat. Endpoint API memerlukan header `X-API-Key`, sedangkan `/app` menerbitkan cookie sesi tanpa meminta kunci; perlakukan URL `/app` sebagai rahasia dan gunakan Cloudflare Access untuk produksi. Hindari membagikan URL tunnel dan kunci API; Quick Tunnel memberi URL acak tetapi bukan mekanisme autentikasi. HTTPS tunnel diperlukan untuk akses kamera ponsel dari jaringan publik.
