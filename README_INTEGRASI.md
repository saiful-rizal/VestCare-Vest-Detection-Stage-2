# 🧢 VestCare Rompi Cerdas — Integrasi Training → Fuzzy → Suara → FastAPI → Cloudflare

Dokumen ini menjakuri alur lengkap dari hasil training YOLO-seg, diproses oleh **fuzzy logic berdasarkan tingkat urgensi**, kemudian diubah menjadi **output suara**, disajikan melalui **FastAPI**, dan dipublikasi via **Cloudflare Tunnel**.

---

## 1. Arsitektur

```
[Kamera / ESP32-CAM / Klien]
        |
        |  HTTPS (via Cloudflare Tunnel)
        v
+-------------------------------+
|   FastAPI Server (port 8000)  |
|  - POST /deteksi              |
|  - POST /deteksi/suara        |
|  - POST /peringatan           |
|  - GET  /riwayat              |
+-------------------------------+
        |
        |  memuat models/best.pt (hasil train_semua.py)
        v
+-------------------------------+
|   YOLOv26n-seg Deteksi        |  (5 kelas: pohon, mobil, motor, orang, lubang)
+-------------------------------+
        |
        |  fuzzy Sugeno: jarak + bahaya kelas + jalur
        v
+-------------------------------+
|   Tingkat Urgensi             |  AMAN / INFO / WASPADA / BAHAYA
+-------------------------------+
        |
        |  output suara (speaker rompi)
        v
+-------------------------------+
|   PemutarPeringatan / TTS     |  kalimat Bahasa Indonesia alami
+-------------------------------+
        |
        v
  JSON response ke klien
```

---

## 2. File yang diubah / ditambah

| Berkas | Keterangan |
|--------|------------|
| `train_semua.py` | (tidak diubah) Hasil training: `models/best.pt` |
| `fuzzysugeno.py` | (tidak diubah) Fuzzy Sugeno: `analisis_hasil()` → urgensi + level |
| `inferensi_vest.py` | **BARU** Pipeline terpadu: YOLO + fuzzy + suara (CLI + impor) |
| `server_rest_api.py` | **DITULIS ULANG** FastAPI: deteksi, suara, riwayat, status |
| `requirements.txt` | Ditambah: fastapi, uvicorn, python-multipart, edge-tts, pydub, pygame-ce |
| `run_server.bat` | **BARU** Jalankan FastAPI server |
| `run_tunnel.bat` | **BARU** Jalankan Cloudflare Tunnel |
| `start_all.bat` | **BARU** Jalankan server + tunnel sekaligus |
| `cloudflared.yml` | **BARU** Konfigurasi tunnel Cloudflare |
| `.env.example` | **BARU** Template variabel lingkungan |
| `suara-natural-ai/` | (tidak diubah) Pustaka klip suara + PemutarPeringatan |

---

## 3. Langkah pemasangan

### A. Install dependensi
```powershell
pip install -r requirements.txt
```
Pastikan **FFmpeg** terpasang di sistem (diperlukan edge-tts/pydub):
https://ffmpeg.org/download.html

### B. Training model (jika belum)
```powershell
python start_train.py
```
Hasil: `models/best.pt` (dan `models/best_semua_kelas.pt`).

### C. Siapkan pustaka suara (opsional, untuk suara klip alami)
Pustaka klip siap pakai sudah ada di `suara-natural-ai\cache_ardi\`. Untuk pakai di server, salin atau buat folder `cache_suara` di root:

```powershell
cd suara-natural-ai
$env:GEMINI_API_KEY="kunci-gemini-anda"
python siapkan_pustaka.py --suara id-ID-ArdiNeural --folder ..\cache_suara --varian 3
python siapkan_pustaka.py --folder ..\cache_suara --periksa
```

Jika tidak ingin ribet, server akan otomatis pakai **TTS fallback** (edge-tts langsung bicara teks peringatan) tanpa butuh pustaka klip.

### D. Siapkan variabel lingkungan
Salin `.env.example` → `.env`, lalu isi:
```powershell
$env:VEST_API_KEY="kunci-rahasia-anda"
$env:VEST_MODEL_PATH="models\best.pt"
$env:VEST_SUARA_FOLDER="cache_suara"
```

### E. Jalankan server
```powershell
python run_server.bat
# atau
.\run_server.bat
```
Server di `http://0.0.0.0:8000`, dokumentasi di `http://localhost:8000/docs`.

---

## 4. Publikasi dengan Cloudflare Tunnel

### A. Dapatkan token
1. Buka https://zero-trust.dash.cloudflare.com/
2. **Networks > Tunnels > Create tunnel**
3. Beri nama `vestcare`, simpan, lalu copy token yang ditampilkan.

### B. Set token dan jalankan
```powershell
$env:CLOUDFLARED_TOKEN="token-anda"
.\run_tunnel.bat
```

### C. Hasil
Tunnel akan mencetak URL publik, misalnya:
```
https://vestcare-xxxx.trycloudflare.com
```
ATAU jika menggunakan domain Anda sendiri di `cloudflared.yml`:
```
https://api.vestcare-contoh.com
```

Semua endpoint API bisa diakses lewat URL publik itu.

---

## 5. Contoh pemakaian API

### Deteksi objek + fuzzy (JSON only)
```bash
curl -X POST https://URL-PUBLIK/deteksi \
     -H "X-API-Key: kunci-rahasia-anda" \
     -F "gambar=@foto_jalan.jpg" -F "jarak_m=0.45"
```

### Deteksi + putar suara di server (speaker rompi)
```bash
curl -X POST https://URL-PUBLIK/deteksi/suara \
     -H "X-API-Key: kunci-rahasia-anda" \
     -F "gambar=@foto_jalan.jpg" -F "jarak_m=0.45"
```

### Fuzzy saja (tanpa kamera/model)
```bash
curl -X POST https://URL-PUBLIK/peringatan \
     -H "X-API-Key: kunci-rahasia-anda" \
     -H "Content-Type: application/json" \
     -d '{"skor_risiko": 0.9, "jarak_m": 0.5}'
```

### Lihat riwayat
```bash
curl -X GET "https://URL-PUBLIK/riwayat?limit=10" \
     -H "X-API-Key: kunci-rahasia-anda"
```

### Status server
```bash
curl https://URL-PUBLIK/status
```

Contoh respons `/deteksi`:
```json
{
  "waktu": "2026-11-07 10:15:30",
  "jumlah_objek": 2,
  "level_tertinggi": "BAHAYA",
  "urgensi_tertinggi": 92.0,
  "aksi_suara": "Awas! ... segera berhenti ...",
  "suara_diputar": true,
  "deteksi": [
    {
      "kelas": "mobil",
      "arah": "kiri",
      "jarak_m": 1.2,
      "urgensi": 92.0,
      "level": "BAHAYA",
      "conf": 0.94,
      "sumber": "kamera",
      "pesan": "BAHAYA: mobil kiri, sekitar 1.2 meter",
      "getar": {"pwm": 255, "interval_ms": 150, "pola": "terus-menerus cepat"}
    }
  ]
}
```

---

## 6. Jalankan CLI langsung (tanpa server)

Untuk menguji deteksi + suara langsung dari webcam:
```powershell
python inferensi_vest.py --source 0 --model models\best.pt --suara cache_suara
```
Tekan `q` untuk keluar.

---

## 7. Catatan penting

- **Output suara** memerlukan speaker/headphone yang terhubung ke komputer/server yang menjalankan `server_rest_api.py`.
- Jika server dijalankan di komputer tanpa audio, set `VEST_TANPA_SUARA=1` agar tidak error.
- Autentikasi (`X-API-Key`) **wajib diisi** saat dipublikasi via Cloudflare Tunnel ke internet umum.
- `VEST_IMGSZ` harus sama dengan saat training (416) agar akurasi deteksi optimal.
