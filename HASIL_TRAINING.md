# Hasil Training YOLO26n-Seg - VestCare Rompi Cerdas (Stage 2)

Dokumen ini berisi laporan lengkap pelatihan model segmentasi untuk **VestCare
Rompi Cerdas**. Isi dokumen mencakup konfigurasi pelatihan, metrik akhir,
metrik terbaik, metrik per kelas, evaluasi tingkat gambar, ketahanan per
varian, grafik, log mentah, dan artefak CSV.

Model terbaik disimpan di `models/best.pt` dan `models/best_semua_kelas.pt`.
Dokumentasi integrasi dan cara menjalankan sistem ada di
[`README.md`](README.md) dan [`README_INTEGRASI.md`](README_INTEGRASI.md).

---

## 1. Ringkasan eksekutif

| Item | Nilai |
|---|---|
| Arsitektur | YOLO26n-Seg (nano, segmentasi instans) |
| Bobot awal | `yolo26n-seg.pt` |
| Jumlah epoch | 100 |
| Epoch terbaik | 59, berdasarkan `metrics/mAP50-95(M)` |
| Ukuran gambar | 416 |
| Batch size | 8 |
| Optimizer | AdamW |
| Learning rate awal | 0.001 |
| Perangkat | NVIDIA GeForce GTX 1650 with Max-Q Design, 4096 MiB (CUDA) |
| Kelas | 5: pohon, mobil, motor, orang, lubang |
| Gambar train / val | 2778 / 312 |
| Bobot terbaik | `models/best.pt` (6.28 MB) |
| Waktu latih | 31,537 detik atau 8 jam 45 menit 37 detik |

Mask mAP50-95 pada epoch terbaik adalah 0.5979. Pada epoch terakhir nilainya
0.5924. Evaluasi ulang bobot terbaik menghasilkan mask mAP50-95 0.5926 dan
box mAP50-95 0.6604.

---

## 2. Konfigurasi pelatihan

Sumber: `train_semua.py` dan `runs/segment/runs/semua_kelas_yolo26n/args.yaml`.

```python
EPOCHS = 100
IMGSZ = 416
BATCH = 8
WORKERS = 0
DEVICE = "0"
PATIENCE = 50
SEED_LATIH = 0
DETERMINISTIC = True
CACHE = False
AMP = True
OPTIMIZER = "AdamW"
LR0 = 0.001
LRF = 0.01
MOMENTUM = 0.937
WEIGHT_DECAY = 0.0005
LABEL_SMOOTHING = 0.1
WARMUP_EPOCHS = 3.0
WARMUP_MOMENTUM = 0.8
WARMUP_BIAS_LR = 0.1
BOX = 7.5
CLS = 0.5
DFL = 1.5
```

Augmentasi:

```python
HSV_H = 0.015
HSV_S = 0.7
HSV_V = 0.4
DEGREES = 10.0
TRANSLATE = 0.1
SCALE = 0.5
SHEAR = 0.0
FLIPUD = 0.0
FLIPLR = 0.5
MOSAIC = 1.0
MIXUP = 0.0
CLOSE_MOSAIC = 10
```

Dataset gabungan lima kelas memakai split train/val 90/10. Semua kelas
dipastikan tersedia di kedua split. Konfigurasi split ditulis ke
`runs/dataset_splits/train.txt` dan `runs/dataset_splits/val.txt`.

---

## 3. Metrik akhir dan metrik terbaik

### 3.1 Epoch 100

Sumber: `runs/segment/runs/semua_kelas_yolo26n/reports/training_report.txt`.

| Metrik | Box | Mask |
|---|---:|---:|
| Precision | 0.8959 | 0.8994 |
| Recall | 0.7846 | 0.7857 |
| mAP50 | 0.8718 | 0.8592 |
| mAP50-95 | 0.6625 | 0.5924 |

Loss validasi:

| Loss | Nilai |
|---|---:|
| `val/box_loss` | 1.0731 |
| `val/seg_loss` | 1.7581 |
| `val/cls_loss` | 0.7750 |
| `val/l1_loss` | 0.0135 |
| `val/sem_loss` | 0.0000 |

### 3.2 Epoch 59, bobot terbaik

| Metrik | Box | Mask |
|---|---:|---:|
| Precision | 0.8331 | 0.8680 |
| Recall | 0.8229 | 0.7867 |
| mAP50 | 0.8753 | 0.8663 |
| mAP50-95 | 0.6545 | 0.5979 |

Loss validasi pada epoch 59 adalah `val/box_loss` 1.0897 dan `val/seg_loss`
1.6124. Epoch 59 dipilih karena mask mAP50-95 lebih tinggi 0.0055 dibanding
epoch 100.

---

## 4. Metrik per kelas

Sumber: `runs/segment/runs/semua_kelas_yolo26n/reports/val_class_metrics.csv`.

### 4.1 Bounding box

| Kelas | Gambar | Instance | P | R | F1 | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| pohon | 76 | 76 | 0.9351 | 1.0000 | 0.9665 | 0.9950 | 0.9419 |
| mobil | 87 | 269 | 0.9379 | 0.6738 | 0.7842 | 0.8277 | 0.5465 |
| motor | 61 | 358 | 0.9195 | 0.7657 | 0.8356 | 0.9006 | 0.6512 |
| orang | 93 | 281 | 0.8367 | 0.7367 | 0.7835 | 0.7917 | 0.5729 |
| lubang | 60 | 88 | 0.8062 | 0.7159 | 0.7584 | 0.8232 | 0.5833 |

### 4.2 Mask

| Kelas | Gambar | Instance | P | R | F1 | mAP50 | mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| pohon | 76 | 76 | 0.9350 | 1.0000 | 0.9664 | 0.9950 | 0.8899 |
| mobil | 87 | 269 | 0.9328 | 0.6705 | 0.7802 | 0.8263 | 0.4853 |
| motor | 61 | 358 | 0.9565 | 0.7977 | 0.8699 | 0.9007 | 0.5655 |
| orang | 93 | 281 | 0.8120 | 0.7153 | 0.7606 | 0.7619 | 0.5082 |
| lubang | 60 | 88 | 0.8115 | 0.7273 | 0.7671 | 0.8164 | 0.5302 |

Keterangan:

- `pohon` memiliki performa terbaik dengan recall 1.0000 pada box dan mask.
- `motor` memiliki instance terbanyak, yaitu 358, dan mAP50 box 0.9006.
- `mobil` memiliki presisi box tinggi, tetapi recall 0.6738 sehingga banyak
  instance terlewat.
- `lubang` memiliki presisi box paling rendah, yaitu 0.8062, dan mask
  mAP50-95 0.5302.
- `orang` memiliki presisi box 0.8367 dan 24 false negative pada evaluasi
  tingkat gambar.

---

## 5. Evaluasi tingkat gambar dan varian

Sumber: `runs/segment/runs/semua_kelas_yolo26n/evaluation/`.

### 5.1 Akurasi tingkat gambar

Ambang confidence yang dipakai adalah 0.25.

| Kelas | TP | FP | FN | TN | Akurasi | F1 |
|---|---:|---:|---:|---:|---:|---:|
| pohon | 76 | 0 | 0 | 236 | 1.0000 | 1.0000 |
| mobil | 84 | 5 | 3 | 220 | 0.9744 | 0.9545 |
| motor | 60 | 1 | 1 | 250 | 0.9936 | 0.9836 |
| orang | 69 | 0 | 24 | 219 | 0.9231 | 0.8519 |
| lubang | 50 | 11 | 10 | 241 | 0.9327 | 0.8264 |

Total: akurasi 0.8333 atau 260 dari 312 gambar benar, precision 0.9522,
recall 0.8992, F1-mikro 0.9250, dan F1-makro 0.9233.

### 5.2 Ketahanan per varian

| Varian | Gambar | Mask P | Mask R | Mask F1 | Mask mAP50 | Mask mAP50-95 | Box mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| gerak diagonal | 78 | 0.8890 | 0.7927 | 0.8381 | 0.8688 | 0.5893 | 0.6532 |
| gerak horizontal | 81 | 0.8746 | 0.8107 | 0.8415 | 0.8676 | 0.6017 | 0.6715 |
| gerak vertikal | 76 | 0.8713 | 0.7792 | 0.8227 | 0.8400 | 0.5803 | 0.6549 |
| getar | 77 | 0.8855 | 0.7888 | 0.8344 | 0.8558 | 0.6125 | 0.6724 |

Mask mAP50-95 berada pada rentang 0.5803 sampai 0.6125. Selisih antarvarian
relatif kecil sehingga model cukup stabil terhadap perubahan sudut dan gerakan
kamera.

### 5.3 Kecepatan

| Item | Nilai |
|---|---:|
| Jumlah gambar uji | 100 |
| Rata-rata | 20.69 ms per gambar |
| Median | 18.42 ms per gambar |
| Maksimum | 120.35 ms per gambar |
| FPS rata-rata | 48.3 |
| Inferensi murni | 13.6 ms per gambar |

Pengukuran dilakukan pada GTX 1650 Max-Q 4 GB dengan batch 1 dan sudah
termasuk praproses serta pascaproses.

---

## 6. Grafik evaluasi

Semua grafik berada di
`runs/segment/runs/semua_kelas_yolo26n/`.

| Grafik | File | Keterangan |
|---|---|---|
| Ringkasan semua metrik | `results.png` | Loss dan metrik per epoch |
| Presisi box | `BoxP_curve.png` | Kurva presisi bounding box |
| Recall box | `BoxR_curve.png` | Kurva recall bounding box |
| PR box | `BoxPR_curve.png` | Kurva precision-recall box |
| F1 box | `BoxF1_curve.png` | Kurva F1 box |
| Presisi mask | `MaskP_curve.png` | Kurva presisi segmentasi |
| Recall mask | `MaskR_curve.png` | Kurva recall segmentasi |
| PR mask | `MaskPR_curve.png` | Kurva precision-recall mask |
| F1 mask | `MaskF1_curve.png` | Kurva F1 mask |
| Confusion matrix | `confusion_matrix.png` | Matriks kebingungan |
| Confusion matrix normalisasi | `confusion_matrix_normalized.png` | Matriks kebingungan ternormalisasi |
| Prediksi train | `train_batch*.jpg` | Contoh batch training |
| Label validasi | `val_batch*_labels.jpg` | Ground truth validasi |
| Prediksi validasi | `val_batch*_pred.jpg` | Hasil prediksi validasi |
| Ringkasan evaluasi | `evaluation/grafik/1_ringkasan_total.png` | Ringkasan akurasi total |
| Metrik per kelas | `evaluation/grafik/2_per_kelas.png` | Akurasi per kelas |
| Metrik per varian | `evaluation/grafik/3_per_varian.png` | Akurasi per varian |
| Akurasi tingkat gambar | `evaluation/grafik/4_tingkat_gambar.png` | TP, FP, FN, TN per kelas |

Grafik utama juga ditampilkan langsung di [`README.md`](README.md).

---

## 7. Log mentah dan artefak

### 7.1 Log

| File | Keterangan |
|---|---|
| `training_semua_20261106_214551_275012.log` | Log sesi training pertama, 2.4 MB |
| `training_semua_20261107_002155_904083.log` | Log sesi training kedua, 6.4 MB |
| `runs/segment/runs/semua_kelas_yolo26n/raw/training.log` | Salinan log mentah run terakhir |
| `runs/segment/runs/semua_kelas_yolo26n/evaluation/evaluation_20261107_091624.log` | Log evaluasi akurasi dan kecepatan |

Log memuat keluaran terminal selama pelatihan, progress bar per epoch, nilai
loss, metrik validasi, learning rate, peringatan, dan waktu pemrosesan.

### 7.2 CSV dan JSON

| File | Isi |
|---|---|
| `runs/segment/runs/semua_kelas_yolo26n/results.csv` | Metrik mentah setiap epoch |
| `runs/segment/runs/semua_kelas_yolo26n/reports/epoch_metrics.csv` | Metrik per epoch yang sudah dirapikan |
| `runs/segment/runs/semua_kelas_yolo26n/reports/val_class_metrics.csv` | Metrik box dan mask per kelas |
| `runs/segment/runs/semua_kelas_yolo26n/reports/training_report.json` | Laporan terstruktur |
| `runs/segment/runs/semua_kelas_yolo26n/reports/training_report.txt` | Ringkasan teks |
| `runs/segment/runs/semua_kelas_yolo26n/reports/artifacts.json` | Daftar artefak run |
| `runs/segment/runs/semua_kelas_yolo26n/evaluation/per_kelas.csv` | Metrik per kelas hasil evaluasi |
| `runs/segment/runs/semua_kelas_yolo26n/evaluation/per_varian.csv` | Metrik per varian |
| `runs/segment/runs/semua_kelas_yolo26n/evaluation/tingkat_gambar_per_kelas.csv` | Akurasi tingkat gambar |
| `runs/segment/runs/semua_kelas_yolo26n/evaluation/kesalahan_gambar.csv` | Daftar kesalahan per gambar |
| `runs/segment/runs/semua_kelas_yolo26n/evaluation/ringkasan_test.json` | Ringkasan evaluasi JSON |
| `runs/segment/runs/semua_kelas_yolo26n/evaluation/kecepatan.json` | Hasil pengukuran kecepatan |

---

## 8. Struktur folder hasil training

```
runs/segment/runs/semua_kelas_yolo26n/
├── weights/
│   ├── best.pt                    bobot terbaik
│   └── last.pt                    bobot epoch terakhir
├── reports/
│   ├── training_report.json
│   ├── training_report.txt
│   ├── val_class_metrics.csv
│   ├── epoch_metrics.csv
│   └── artifacts.json
├── raw/
│   ├── training.log
│   └── results.csv
├── evaluation/
│   ├── laporan_akurasi.txt
│   ├── per_kelas.csv
│   ├── per_varian.csv
│   ├── tingkat_gambar_per_kelas.csv
│   ├── kesalahan_gambar.csv
│   ├── ringkasan_test.json
│   ├── kecepatan.json
│   ├── grafik/
│   ├── contoh_prediksi/
│   ├── ultralytics/
│   └── reports/
├── results.csv
├── results.png
├── BoxP_curve.png
├── BoxR_curve.png
├── BoxPR_curve.png
├── BoxF1_curve.png
├── MaskP_curve.png
├── MaskR_curve.png
├── MaskPR_curve.png
├── MaskF1_curve.png
├── confusion_matrix.png
├── confusion_matrix_normalized.png
├── train_batch*.jpg
├── val_batch*_labels.jpg
├── val_batch*_pred.jpg
├── args.yaml
└── training.log
```

Bobot model juga disalin ke `models/best.pt` dan
`models/best_semua_kelas.pt`.

---

## 9. Cara memakai model

Inferensi langsung dengan webcam:

```powershell
.\.venv\Scripts\python.exe inferensi_vest.py --source 0 --model models\best.pt --suara suara-natural-ai\cache_ardi
```

Melalui server FastAPI:

```powershell
.\run_server.bat
```

Buka `http://127.0.0.1:8000/docs` untuk dokumentasi API dan
`http://127.0.0.1:8000/app` untuk halaman kamera ponsel.

Contoh permintaan deteksi:

```powershell
curl.exe -X POST http://127.0.0.1:8000/deteksi `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -F "gambar=@foto_jalan.jpg" `
  -F "jarak_m=0.45"
```

---

## 10. Catatan dan rekomendasi

1. Mask mAP50-95 0.5979 masih dapat ditingkatkan. Kelas `mobil`, `orang`, dan
   `lubang` membutuhkan data tambahan, terutama pada kondisi objek kecil,
   oklusi, malam, dan hujan.
2. Evaluasi utama memakai split validasi. Evaluasi pada split test terpisah dan
   data lapangan perlu dilakukan sebelum menentukan ambang produksi.
3. Model sudah siap dipakai untuk inferensi waktu nyata dengan output suara
   melalui fuzzy Sugeno. Kecepatan sekitar 48.3 FPS pada GTX 1650 Max-Q 4 GB
   memberikan ruang untuk pemrosesan kamera ponsel.
4. Semua grafik, log, dan CSV tersimpan lengkap di
   `runs/segment/runs/semua_kelas_yolo26n/` agar hasil dapat diperiksa dan
   direproduksi.
