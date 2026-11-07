# 🧢 VestCare — Rompi Cerdas Deteksi Rintangan (Stage 2)

Sistem deteksi rintangan jalan untuk rompi tunanetra berbasis **YOLOv26n-Seg**, **fuzzy logic Sugeno** (tingkat urgensi), dan **output suara**, disajikan melalui **FastAPI** dan dipublikasi dengan **Cloudflare Tunnel**.

> Repositori ini adalah lanjutan dari **Stage 2** proyek VestCare. Hasil training, grafik, dan log mentah disertakan lengkap di folder `runs/` dan dokumentasi di `HASIL_TRAINING.md`.

---

## 📋 Fitur Utama

| Fitur | Keterangan |
|-------|------------|
| 🎯 **Deteksi segmen** | YOLOv26n-Seg deteksi 5 kelas: pohon, mobil, motor, orang, lubang |
| 🧠 **Fuzzy logic** | Sugeno orde-nol menghitung tingkat urgensi (AMAN / INFO / WASPADA / BAHAYA) berdasarkan jarak + bahaya kelas + jalur |
| 🔊 **Output suara** | Ucapan peringatan Bahasa Indonesia melalui speaker rompi (klip suara + TTS fallback) |
| 🌐 **FastAPI API** | Endpoint `/deteksi`, `/deteksi/suara`, `/peringatan`, `/riwayat`, `/status` |
| ☁️ **Cloudflare Tunnel** | Publikasi API ke internet umum dengan URL publik (HTTPS) |
| 📊 **Hasil training lengkap** | Grafik, metrik per kelas, log mentah, dan bobot model |

---

## 🏗️ Arsitektur

```
[Kamera / ESP32-CAM / Klien]
        │  HTTPS via Cloudflare Tunnel
        ▼
+---------------------------+
|   FastAPI Server (8000)   |
|  /deteksi                 |
|  /deteksi/suara           |
|  /peringatan              |
|  /riwayat                 |
+---------------------------+
        │ memuat models/best.pt
        ▼
+---------------------------+
|   YOLOv26n-Seg Deteksi    |  → 5 objek jalan
+---------------------------+
        │ fuzzy Sugeno
        ▼
+---------------------------+
|   Tingkat Urgensi         |  AMAN / INFO / WASPADA / BAHAYA
+---------------------------+
        │ output suara
        ▼
+---------------------------+
|   Pemutar Suara / TTS     |  Bahasa Indonesia alami
+---------------------------+
        ▼
  JSON response ke klien
```

---

## 📊 Ringkasan Hasil Training

Model terbaik: `models/best.pt` (YOLOv26n-Seg, 100 epoch, imgsz 416)

### Metrik Akhir (Epoch 100)
| Metrik | Nilai |
|--------|-------|
| Box mAP50 | 0.8718 |
| Box mAP50-95 | 0.6625 |
| Mask mAP50 | 0.8592 |
| Mask mAP50-95 | 0.5924 |

### Metrik Terbaik (Epoch 59)
| Metrik | Nilai |
|--------|-------|
| Mask mAP50-95 | **0.5979** |
| Mask mAP50 | 0.8663 |

### Metrik Per Kelas (Validasi)
| Kelas | Box mAP50 | Box mAP50-95 | Mask mAP50 | Mask mAP50-95 |
|-------|-----------|--------------|------------|---------------|
| pohon | 0.9950 | 0.9419 | 0.9950 | 0.8899 |
| mobil | 0.8277 | 0.5465 | 0.8263 | 0.4853 |
| motor | 0.9006 | 0.6512 | 0.9007 | 0.5655 |
| orang | 0.7917 | 0.5729 | 0.7619 | 0.5082 |
| lubang | 0.8232 | 0.5833 | 0.8164 | 0.5302 |

> Detail lengkap: lihat [`HASIL_TRAINING.md`](HASIL_TRAINING.md) dan folder `runs/segment/runs/semua_kelas_yolo26n/`.

---

## 🚀 Cara Memulai

### 1. Clone repositori
```bash
git clone https://github.com/saiful-rizal/VestCare-Vest-Detection-Stage-2.git
cd VestCare-Vest-Detection-Stage-2
```

### 2. Install dependensi
```powershell
pip install -r requirements.txt
```
> Pastikan **FFmpeg** terpasang di sistem (diperlukan edge-tts/pydub untuk suara).

### 3. Siapkan variabel lingkungan
Salin `.env.example` → `.env`, lalu isi:
```powershell
$env:VEST_API_KEY="kunci-rahasia-anda"
```

### 4. Jalankan server FastAPI
```powershell
.\run_server.bat
```
Buka dokumentasi interaktif: `http://localhost:8000/docs`

### 5. Publikasi via Cloudflare Tunnel
Dapatkan token di [Cloudflare Zero Trust Dashboard](https://zero-trust.dash.cloudflare.com/) (Networks > Tunnels), lalu:
```powershell
$env:CLOUDFLARED_TOKEN="token-anda"
.\run_tunnel.bat
```

---

## 📖 Dokumentasi Detail

| Dokumen | Isi |
|---------|-----|
| [`README_INTEGRASI.md`](README_INTEGRASI.md) | Panduan integrasi lengkap: training → fuzzy → suara → API → Cloudflare |
| [`HASIL_TRAINING.md`](HASIL_TRAINING.md) | Laporan training lengkap: metrik, grafik, log mentah, rekomendasi |

---

## 🔌 Contoh Pemakaian API

### Deteksi objek + fuzzy (JSON)
```bash
curl -X POST https://URL-PUBLIK/deteksi \
     -H "X-API-Key: kunci-rahasia-anda" \
     -F "gambar=@foto.jpg" -F "jarak_m=0.45"
```

### Deteksi + putar suara di server
```bash
curl -X POST https://URL-PUBLIK/deteksi/suara \
     -H "X-API-Key: kunci-rahasia-anda" \
     -F "gambar=@foto.jpg" -F "jarak_m=0.45"
```

### Fuzzy saja (tanpa kamera)
```bash
curl -X POST https://URL-PUBLIK/peringatan \
     -H "X-API-Key: kunci-rahasia-anda" \
     -H "Content-Type: application/json" \
     -d '{"skor_risiko":0.9,"jarak_m":0.5}'
```

---

## 📁 Struktur Repositori

```
VestCare-Vest-Detection-Stage-2/
├── README.md                 ← Halaman ini (tampak di GitHub)
├── README_INTEGRASI.md       ← Panduan integrasi lengkap
├── HASIL_TRAINING.md         ← Laporan hasil training lengkap
├── .env.example              │ Template variabel lingkungan
├── .gitignore                │ File yang diabaikan Git
├── requirements.txt          │ Dependensi Python
├── train_semua.py            │ Skrip training YOLOv26n-Seg
├── inferensi_vest.py         │ Pipeline deteksi + fuzzy + suara
├── server_rest_api.py        │ Server FastAPI
├── fuzzysugeno.py            │ Fuzzy logic Sugeno
├── run_server.bat            │ Jalankan FastAPI server
├── run_tunnel.bat            │ Jalankan Cloudflare Tunnel
├── start_all.bat             │ Jalankan server + tunnel sekaligus
├── cloudflared.yml           │ Konfigurasi tunnel Cloudflare
├── models/
│   ├── best.pt               │ Bobot model terbaik
│   └── best_semua_kelas.pt   │ Bobot model semua kelas
├── runs/segment/runs/semua_kelas_yolo26n/
│   ├── weights/best.pt       │ Bobot training
│   ├── reports/              │ Laporan metrik (JSON, CSV, TXT)
│   ├── raw/                  │ Log mentah + results.csv
│   └── *.png                 │ Grafik evaluasi (12 file)
└── suara-natural-ai/         │ Modul suara dan pemutar peringatan
```

---

## 📝 Lisensi

Proyek ini dikembangkan untuk tugas akhir / penelitian **VestCare Rompi Cerdas (Stage 2)**.

---

Dibuat oleh **Saiful Rizal** — [saiful-rizal/VestCare-Vest-Detection-Stage-2](https://github.com/saiful-rizal/VestCare-Vest-Detection-Stage-2)
