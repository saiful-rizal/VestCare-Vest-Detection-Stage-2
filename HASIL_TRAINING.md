# 📊 Hasil Training YOLOv26n-Seg — VestCare Rompi Cerdas (Stage 2)

Dokumen ini berisi laporan lengkap hasil pelatihan model deteksi segmen untuk **VestCare Rompi Cerdas**, termasuk konfigurasi, metrik akhir, metrik terbaik, metrik per kelas, grafik evaluasi, dan log mentah.

> Model terbaik disimpan di: `models/best.pt` (dan `models/best_semua_kelas.pt`)

---

## 1. Ringkasan Eksekutif

| Item | Nilai |
|------|-------|
| Model arsitektur | YOLOv26n-Seg (nano, segmentasi) |
| Bobot awal | `yolo26n-seg.pt` |
| Jumlah epoch | 100 |
| Epoch terbaik (berdasarkan `metrics/mAP50-95(M)`) | **59** |
| Ukuran gambar (imgsz) | 416 |
| Batch size | 8 |
| Optimizer | AdamW |
| Learning rate awal | 0.001 |
| Device | GPU (CUDA) |
| Kelas | 5 (pohon, mobil, motor, orang, lubang) |
| Bobot terbaik | `models/best.pt` (6.28 MB) |

---

## 2. Metrik Akhir (Epoch ke-100)

Berikut metrik pada epoch terakhir (100) dari file `runs/segment/runs/semua_kelas_yolo26n/reports/training_report.txt`:

### Deteksi (Bounding Box / Box)
| Metrik | Nilai |
|--------|-------|
| Precision (B) | 0.8959 |
| Recall (B) | 0.7846 |
| mAP50 (B) | 0.8718 |
| mAP50-95 (B) | 0.6625 |

### Segmentasi (Mask / M)
| Metrik | Nilai |
|--------|-------|
| Precision (M) | 0.8994 |
| Recall (M) | 0.7857 |
| mAP50 (M) | 0.8592 |
| mAP50-95 (M) | 0.5924 |

### Loss (Validasi)
| Loss | Nilai |
|------|-------|
| val/box_loss | 1.0731 |
| val/seg_loss | 1.7581 |
| val/cls_loss | 0.7750 |
| val/l1_loss | 0.0135 |
| val/sem_loss | 0.0000 |

---

## 3. Metrik Terbaik (Epoch ke-59)

Epoch terbaik dipilih berdasarkan `metrics/mAP50-95(M)` (mAP segmentasi 50:95).

| Metrik | Nilai Epoch 59 |
|--------|----------------|
| mAP50-95 (M) | **0.5979** |
| mAP50 (M) | 0.8663 |
| Precision (M) | 0.8680 |
| Recall (M) | 0.7867 |
| mAP50-95 (B) | 0.6545 |
| mAP50 (B) | 0.8753 |
| Precision (B) | 0.8331 |
| Recall (B) | 0.8229 |
| val/box_loss | 1.0897 |
| val/seg_loss | 1.6124 |

---

## 4. Metrik Per Kelas (Validasi)

Sumber: `runs/segment/runs/semua_kelas_yolo26n/reports/val_class_metrics.csv`

| Class ID | Nama | Gambar | Instances | Box P | Box R | Box mAP50 | Box mAP50-95 | Mask P | Mask R | Mask mAP50 | Mask mAP50-95 |
|----------|------|--------|-----------|-------|-------|-----------|--------------|--------|--------|------------|---------------|
| 0 | pohon | 76 | 76 | 0.9351 | 1.0000 | 0.9950 | 0.9419 | 0.9350 | 1.0000 | 0.9950 | 0.8899 |
| 1 | mobil | 87 | 269 | 0.9379 | 0.6738 | 0.8277 | 0.5465 | 0.9328 | 0.6705 | 0.8263 | 0.4853 |
| 2 | motor | 61 | 358 | 0.9195 | 0.7657 | 0.9006 | 0.6512 | 0.9565 | 0.7977 | 0.9007 | 0.5655 |
| 3 | orang | 93 | 281 | 0.8367 | 0.7367 | 0.7917 | 0.5729 | 0.8120 | 0.7153 | 0.7619 | 0.5082 |
| 4 | lubang | 60 | 88 | 0.8062 | 0.7159 | 0.8232 | 0.5833 | 0.8115 | 0.7273 | 0.8164 | 0.5302 |

**Keterangan:**
- **pohon**: Performa terbaik (mAP50 box 0.995, recall 1.0) — mudah terdeteksi karena ukuran besar dan bentuk konsisten.
- **motor**: mAP50 box tertinggi (0.9006) dengan banyak instances (358).
- **mobil**: Banyak instances (269) tapi recall lebih rendah (0.6738) — kemungkinan karena variasi ukuran dan oklusi.
- **orang**: Recall baik (0.7367) tapi precision lebih rendah (0.8367).
- **lubang**: Performa terendah (box mAP50-95 0.5833) — bentuk tidak teratur dan sering sedikit/terpencil.

---

## 5. Konfigurasi Pelatihan

Sumber: `train_semua.py`

```python
EPOCHS = 100
IMGSZ = 416
BATCH = 8
WORKERS = 0            # Windows: 0 untuk menghindari error multiprocessing
DEVICE = "0"           # GPU
PATIENCE = 50
SEED_LATIH = 0
DETERMINISTIC = True
CACHE = False
AMP = True             # Automatic Mixed Precision
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
```

Dataset gabungan 5 kelas (pohon, mobil, motor, orang, lubang) dengan split train/val 90%/10%, memastikan semua kelas tersedia di kedua split.

---

## 6. Grafik Evaluasi

Semua grafik berada di folder `runs/segment/runs/semua_kelas_yolo26n/`:

| Grafik | File | Keterangan |
|--------|------|------------|
| Ringkasan semua metrik | `results.png` | Plot gabungan loss dan metrik per epoch |
| Presisi Box | `BoxP_curve.png` | Kurva presisi bounding box |
| Recall Box | `BoxR_curve.png` | Kurva recall bounding box |
| mAP50 Box | (dalam `results.png`) | — |
| PR Curve Box | `BoxPR_curve.png` | Kurva Precision-Recall box |
| F1 Curve Box | `BoxF1_curve.png` | Kurva F1 box |
| Presisi Mask | `MaskP_curve.png` | Kurva presisi segmentasi |
| Recall Mask | `MaskR_curve.png` | Kurva recall segmentasi |
| PR Curve Mask | `MaskPR_curve.png` | Kurva Precision-Recall mask |
| F1 Curve Mask | `MaskF1_curve.png` | Kurva F1 mask |
| Confusion Matrix | `confusion_matrix.png` | Matriks kebingungan deteksi |
| Confusion Matrix (Norm) | `confusion_matrix_normalized.png` | Matriks kebingungan dinormalisasi |
| Prediksi Train | `train_batch*.jpg` | Contoh hasil prediksi pada batch train |
| Prediksi Val | `val_batch*_pred.jpg` | Hasil prediksi pada data validasi |
| Label Val | `val_batch*_labels.jpg` | Ground truth label pada data validasi |

**Untuk melihat grafik**, buka file PNG di folder `runs/segment/runs/semua_kelas_yolo26n/` langsung atau melalui GitHub file browser.

---

## 7. Log Mentah (Raw Log)

File log pelatihan lengkap tersedia di:

- `training_semua_20261106_214551_275012.log` — log sesi training pertama (6 Nov 2026)
- `training_semua_20261107_002155_904083.log` — log sesi training kedua (7 Nov 2026)
- `runs/segment/runs/semua_kelas_yolo26n/raw/training.log` — salinan log mentah dari run terakhir
- `runs/segment/runs/semua_kelas_yolo26n/training.log` — log run terakhir

Log mencakup:
- Output terminal selama pelatihan
- Progress bar per epoch (loss, metrik, learning rate)
- Peringatan dan error (jika ada)
- Waktu pemrosesan per epoch

---

## 8. Artefak dan File Hasil Training

Struktur folder `runs/segment/runs/semua_kelas_yolo26n/`:

```
runs/segment/runs/semua_kelas_yolo26n/
├── weights/
│   ├── best.pt           ← Bobot terbaik (dipakai untuk inferensi)
│   └── last.pt           ← Bobot epoch terakhir
├── reports/
│   ├── training_report.json    ← Laporan terstruktur (JSON)
│   ├── training_report.txt     ← Laporan ringkasan (teks)
│   ├── val_class_metrics.csv   ← Metrik per kelas (CSV)
│   ├── epoch_metrics.csv       ← Metrik per epoch (CSV)
│   └── artifacts.json          ← Daftar semua artefak
├── raw/
│   ├── training.log            ← Log mentah lengkap
│   └── results.csv             ← Hasil metrik per epoch (CSV)
├── results.png                 ← Grafik ringkasan
├── BoxP_curve.png              ← Grafik presisi box
├── BoxR_curve.png              ← Grafik recall box
├── BoxPR_curve.png             ← Grafik PR box
├── BoxF1_curve.png             ← Grafik F1 box
├── MaskP_curve.png             ← Grafik presisi mask
├── MaskR_curve.png             ← Grafik recall mask
├── MaskPR_curve.png            ← Grafik PR mask
├── MaskF1_curve.png            ← Grafik F1 mask
├── confusion_matrix.png        ← Confusion matrix
├── confusion_matrix_normalized.png
├── train_batch*.jpg            ← Contoh prediksi train
├── val_batch*_pred.jpg         ← Prediksi validasi
├── val_batch*_labels.jpg       ← Ground truth validasi
├── args.yaml                   ← Konfigurasi argumen training
└── training.log                ← Salinan log run
```

Bobot model akhir juga disalin ke:
- `models/best.pt`
- `models/best_semua_kelas.pt`

---

## 9. Cara Memakai Model Hasil Training

### Inferensi langsung (CLI)
```powershell
python inferensi_vest.py --source 0 --model models/best.pt --suara cache_suara
```

### Melalui FastAPI server
```powershell
.\run_server.bat
# Buka http://localhost:8000/docs
```

### Contoh request deteksi
```bash
curl -X POST http://localhost:8000/deteksi \
     -H "X-API-Key: kunci-rahasia-anda" \
     -F "gambar=@foto_jalan.jpg" -F "jarak_m=0.45"
```

---

## 10. Catatan dan Rekomendasi

1. **mAP segmentasi masih moderat** (0.5924 mAP50-95). Untuk meningkatkan, pertimbangkan menambah data pelatihan khusus untuk kelas `lubang` dan `orang`.
2. **Kelas `lubang`** memiliki performa terendah. Disarankan augmentasi lebih banyak atau parameter loss yang berbeda.
3. Model sudah siap digunakan untuk inferensi real-time dengan output suara melalui fuzzy logic (Sugeno) berdasarkan tingkat urgensi.
4. Semua grafik dan log tersimpan lengkap di folder `runs/segment/runs/semua_kelas_yolo26n/` untuk direview dan direproduksi di masa depan.

---

## 11. Sumber File

| File | Lokasi | Keterangan |
|------|--------|------------|
| Bobot terbaik | `models/best.pt` | Model siap pakai |
| Konfigurasi training | `train_semua.py` | Skrip pelatihan lengkap |
| Laporan teks | `runs/...\reports\training_report.txt` | Ringkasan metrik |
| Laporan JSON | `runs/...\reports\training_report.json` | Data terstruktur |
| Metrik per kelas | `runs/...\reports\val_class_metrics.csv` | Detail per kelas |
| Log mentah | `training_semua_*.log` | Output terminal training |
| Hasil per epoch | `runs/...\results.csv` | Metrik setiap epoch |
| Grafik | `runs/...\*.png` | Visualisasi evaluasi |
