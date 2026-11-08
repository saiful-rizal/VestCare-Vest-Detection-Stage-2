# VestCare — Rompi Cerdas (Stage 2)

Sistem peringatan rintangan untuk rompi cerdas berbasis **segmentasi YOLO26n**, **logika fuzzy Sugeno**, dan **suara natural Bahasa Indonesia**. Model mendeteksi lima kelas — **pohon, mobil, motor, orang, dan lubang** — lalu hasilnya dipetakan menjadi arah, jarak, tingkat risiko, dan instruksi suara bagi pengguna.

## Fitur utama

- **Segmentasi 5 kelas** dengan YOLO26n-seg (mask + bounding box).
- **Fuzzy Sugeno** untuk menghitung skor risiko dan tingkat peringatan dari jarak serta konteks objek.
- **Suara natural** yang dirakit dari klip Bahasa Indonesia (`suara-natural-ai/`), dengan fallback ke kalimat netral bila klip gerak belum tersedia.
- **Deteksi gerak objek** (`PelacakGerak`) untuk `mobil`, `motor`, dan `orang`: status `netral`, `bergerak`, atau `diam`.
- **Penanda `ragu`**: deteksi dengan confidence di bawah `0.50` tetap dikirim di JSON, tetapi tidak dipakai untuk ringkasan, memori, suara, maupun UI.
- **REST API FastAPI** + dashboard React dengan deteksi kamera otomatis multi-objek, kotak setiap objek, hasil deteksi langsung, dan instruksi suara.
- **Riwayat Supabase**: backend menyinkronkan objek deteksi ke tabel `detections` dan memakai satu perangkat virtual server; konfigurasi URL dan secret/service-role key di `.env` root.
- **Quality gate training** per kelas dengan ambang 98% (box P, box mAP50, mask P, mask mAP50).

## Struktur proyek

| Path | Fungsi |
|---|---|
| `server_rest_api.py` | Server FastAPI, engine YOLO, fuzzy, suara, riwayat, dan tunnel ngrok |
| `fuzzysugeno.py` | Fuzzy Sugeno, `analisis_hasil`, `PelacakGerak`, dan penanda `ragu` |
| `start_train.py` / `train_semua.py` | Pipeline training 5 kelas, quality gate, evaluasi akhir, dan pembersihan run lama |
| `start_eval.py` | Evaluasi model per kelas dan per varian dataset |
| `dataset_gabungan.yaml` | Konfigurasi dataset gabungan 5 kelas (path absolut Windows) |
| `models/best.pt` | Bobot aktif yang dipakai server |
| `vest-care-react/` | Dashboard React; hasil build disajikan server dari `vest-care-react/dist/` |
| `web/index.html` | Halaman web lama (tidak disajikan sebagai halaman utama) |
| `suara-natural-ai/` | Pustaka klip suara, perakit kalimat, dan contoh integrasi |
| `runs/segment/runs/` | Artefak training, grafik, laporan, dan evaluasi |

## Hasil training terbaru

Run yang dipublikasikan:

```text
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/
```

| Konfigurasi | Nilai |
|---|---|
| Model dasar | `yolo26n-seg.pt` |
| Epoch | 100 / 100 |
| Image size | 512 |
| Batch | 4 |
| Optimizer | AdamW |
| Seed / deterministic | 0 / ya |
| Device | GPU 0 |
| Waktu training | ± 8,3 jam (29.825 detik) |
| Dataset train / val | 2.778 / 312 gambar |
| Overlap train–val | 0 gambar |

### Metrik validasi keseluruhan

| Metrik | Box | Mask |
|---|---:|---:|
| Precision | 0.8851 | 0.8902 |
| Recall | 0.7806 | 0.7822 |
| mAP50 | 0.8540 | 0.8493 |
| mAP50-95 | 0.6477 | 0.6105 |

### Metrik per kelas

| Kelas | Box P | Box R | Box mAP50 | Mask P | Mask R | Mask mAP50 |
|---|---:|---:|---:|---:|---:|---:|
| pohon | 0.9846 | 1.0000 | 0.9950 | 0.9851 | 1.0000 | 0.9950 |
| mobil | 0.8977 | 0.7505 | 0.8456 | 0.9153 | 0.7637 | 0.8449 |
| motor | 0.9129 | 0.7907 | 0.8882 | 0.9482 | 0.8179 | 0.9182 |
| orang | 0.8583 | 0.7367 | 0.8081 | 0.8274 | 0.7046 | 0.7628 |
| lubang | 0.7718 | 0.6250 | 0.7336 | 0.7777 | 0.6250 | 0.7169 |

### Status quality gate

Quality gate memakai ambang **98%** untuk `box_p`, `box_map50`, `mask_p`, dan `mask_map50` pada setiap kelas.

- **Hasil: belum lulus** (`passed: false`, `deployed: false`).
- Hanya kelas **pohon** yang memenuhi seluruh metrik wajib.
- Kelas **mobil, motor, orang, dan lubang** masih di bawah ambang, terutama pada `box_map50` dan `mask_map50`.
- Pipeline **tidak** mengganti bobot aktif secara otomatis. Checkpoint terbaik tetap disalin manual ke `models/best.pt` untuk kebutuhan serving.

Laporan lengkap tersedia di:

```text
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.txt
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.json
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/val_class_metrics.csv
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/
```

## Cara menjalankan

### Prasyarat

- Python 3.10+ dan virtual environment `.venv`.
- Dependensi utama: `ultralytics`, `fastapi`, `uvicorn`, `pillow`, `numpy`, `python-multipart`.
- Untuk suara: `pip install -r suara-natural-ai/requirements_pemutar.txt` (butuh `pygame-ce`).
- Untuk tunnel publik: `ngrok` tersedia di `PATH`.

### Training

```powershell
python start_train.py
```

Pipeline akan:

1. Menyiapkan split train/val dari dataset gabungan.
2. Melatih `yolo26n-seg.pt` selama 100 epoch pada `imgsz=512`.
3. Menjalankan quality gate per kelas.
4. Melakukan evaluasi akhir dan menulis laporan ke folder run.
5. Menghapus run lama serta checkpoint duplikat setelah training selesai.

### Evaluasi

```powershell
python start_eval.py --dataset dataset_gabungan.yaml --split val
```

Opsi lain: `--model`, `--out`, `--imgsz`, `--batch`, `--conf`, `--contoh`, `--n-kecepatan`, dan `--device`.

### Server API

Isi `.env` terlebih dahulu (lihat `.env` untuk daftar kunci). Kunci yang dipakai antara lain:

```text
VEST_API_KEY=<kunci acak minimal 32 karakter>
VEST_MODEL_PATH=models/best.pt
VEST_IMGSZ=512
VEST_CONF=0.35
VEST_CONF_RAGU=0.50
VEST_HOST=127.0.0.1
VEST_PORT=8080
```

Jalankan:

```powershell
cd vest-care-react
npm install
npm run build
cd ..
python server_rest_api.py
```

Server akan membuka API lokal dan tunnel ngrok. URL utama ngrok (`/`) langsung menampilkan dashboard React; `/app` tetap menjadi alias. Dokumentasi interaktif tersedia di `/docs`. Build dashboard perlu diperbarui dengan `npm run build` setiap kali source React berubah.

### Deteksi dari kamera (modul suara)

```powershell
python suara-natural-ai/jalankan_fuzzy.py --sumber 0
```

Gunakan `--sumber` untuk indeks kamera atau path video. Contoh integrasi tanpa kamera tersedia di `suara-natural-ai/contoh_integrasi.py`.

## Endpoint API

| Method | Path | Keterangan |
|---|---|---|
| `GET` | `/info` | Info versi, model, `imgsz`, `conf`, `conf_ragu`, status engine |
| `GET` | `/status` | Status server dan pustaka suara |
| `GET` | `/` | Dashboard React VestCare |
| `GET` | `/app` | Alias dashboard React VestCare |
| `GET` | `/docs` | Dokumentasi OpenAPI |
| `POST` | `/deteksi` | Upload gambar (`multipart/form-data`) + `jarak_m` opsional |
| `POST` | `/deteksi/suara` | Sama seperti `/deteksi`, dengan rencana suara |
| `POST` | `/peringatan` | JSON `{ "skor_risiko": 0..1, "jarak_m": ... }` |
| `GET` | `/riwayat?limit=20` | Riwayat deteksi terakhir |
| `GET` | `/suara/pratinjau` | Contoh rencana suara |
| `GET` | `/suara/{nama_berkas}` | Berkas klip suara |

Jika `VEST_API_KEY` aktif, sertakan header `X-API-Key` pada setiap request yang diproteksi.

## Alur deteksi, gerak, dan status ragu

1. Gambar diterima server dan dijalankan melalui YOLO26n-seg pada `imgsz=512`.
2. Setiap objek mendapat `confidence`, kelas, box, dan mask.
3. Objek dengan `confidence < VEST_CONF_RAGU` (default `0.50`) ditandai `ragu: true`.
4. Objek `ragu` tetap ada di JSON, tetapi diabaikan oleh:
   - ringkasan deteksi,
   - memori/riwayat objek,
   - perencana suara,
   - tampilan UI.
5. `PelacakGerak` membandingkan ukuran box antar-frame untuk `mobil`, `motor`, dan `orang`:
   - `bergerak` bila box mengecil/membesar secara konsisten,
   - `diam` bila ukuran stabil,
   - `netral` bila sampel belum cukup.
6. Fuzzy Sugeno menghitung risiko dari jarak dan tingkat peringatan.
7. Perencana suara merakit kalimat dari klip yang tersedia. Karena `cache_ardi` belum memiliki klip `bergerak`/`diam`, dipakai fallback `benda_{kelas}_{arah}_netral`.

## Artefak dan log

- Log training root: `training_semua_20261107_154452_851599.log`
- Log run: `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/training.log`
- Log mentah: `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/raw/training.log`
- Evaluasi akhir: `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/`
- Bobot: `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/weights/best.pt`

## Catatan

- `dataset_gabungan.yaml` memakai path absolut `C:/dataset vestcare (rompi-cerdas)`. Sesuaikan path bila repo dipindahkan ke mesin lain.
- File `.env` tidak di-commit. Jangan pernah menuliskan kunci API asli ke README atau file yang di-commit.
- Quality gate 98% belum terpenuhi; gunakan hasil ini sebagai baseline untuk perbaikan dataset dan training berikutnya.
- Repo ini tidak memakai Git LFS. Bobot dan artefak run disimpan langsung agar hasil training dapat direproduksi dan diaudit.
