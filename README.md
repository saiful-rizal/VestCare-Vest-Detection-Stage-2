# TAHAP 2 Deteksi Rintangan Jalan YOLOv26n-Seg dan Integrasi Fuzzy-Suara (VestCare)

Eksperimen segmentasi objek jalan untuk penunjang tunanetra (rompi VestCare):
melatih **YOLO26n-Seg** pada dataset gabungan lima kelas, memilih bobot terbaik
berdasarkan **mAP50-95 mask**, lalu menghubungkan output deteksi ke **fuzzy
Sugeno** (tingkat urgensi), **output suara**, **FastAPI**, dan **Cloudflare
Tunnel**.

Semua angka di halaman ini diambil langsung dari file di
[`runs/segment/runs/semua_kelas_yolo26n/reports/`](runs/segment/runs/semua_kelas_yolo26n/reports/)
dan [`results.csv`](runs/segment/runs/semua_kelas_yolo26n/results.csv).
Evaluasi tambahan (akurasi tingkat gambar, ketahanan per varian, dan kecepatan)
diambil dari [`evaluation/`](runs/segment/runs/semua_kelas_yolo26n/evaluation/).

| Ringkasan | Nilai |
|---|---|
| Bobot terbaik | `models/best.pt` (6.28 MB) |
| Arsitektur | YOLO26n-Seg, 3,054,875 parameter, 10.3 GFLOPs |
| Dataset | 5 kelas, 2778 gambar train dan 312 gambar val |
| Epoch | 100, bobot terbaik pada epoch 59 |
| Mask mAP50-95 | 0.5979 (epoch 59) dan 0.5924 (epoch 100) |
| Akurasi tingkat gambar | 0.8333 atau 260 dari 312 gambar benar |
| Kecepatan | 20.69 ms per gambar atau sekitar 48.3 FPS |

---

## 1. Pengaturan eksperimen

| Parameter | Nilai |
|---|---|
| Model | `yolo26n-seg.pt` (bobot pralatih Ultralytics), arsitektur YOLO26n-Seg |
| Tugas | Segmentasi instans (bounding box dan mask) |
| Kelas | pohon, mobil, motor, orang, lubang |
| Dataset | Gabungan lima dataset, split train/val 90/10 |
| Gambar train / val | 2778 / 312 |
| Konfigurasi split | `runs/dataset_splits/train.txt` dan `runs/dataset_splits/val.txt`; semua kelas tersedia di kedua split |
| Epoch | 100, `patience` 50 |
| `imgsz` / `batch` | 416 / 8 |
| Optimizer | AdamW, `lr0` 0.001, `lrf` 0.01, `momentum` 0.937, `weight_decay` 0.0005 |
| Warmup | 3 epoch, momentum 0.8, bias LR 0.1 |
| Loss gain | box 7.5, cls 0.5, dfl 1.5 |
| Augmentasi | HSV 0.015/0.7/0.4, rotate 10 derajat, translate 0.1, scale 0.5, fliplr 0.5, mosaic 1.0, mixup 0.0, close_mosaic 10 |
| Presisi campuran | `amp=True` |
| Seed / deterministik | 0 / `True` |
| Pekerja data | `workers=0` untuk menghindari masalah multiprocessing di Windows |
| Perangkat | NVIDIA GeForce GTX 1650 with Max-Q Design, 4096 MiB (CUDA) |
| Waktu latih | 31,537 detik atau 8 jam 45 menit 37 detik; rata-rata 315.4 detik per epoch |
| Pemilihan bobot | `metrics/mAP50-95(M)` tertinggi, yaitu epoch 59 |

Run yang dilaporkan: satu pelatihan 100 epoch. Evaluasi dilakukan pada split
validasi berisi 312 gambar dan 1072 instance.

---

## 2. Hasil utama

### 2.1 Metrik epoch 100 dan epoch terbaik 59

| Metrik | Epoch 100 | Epoch 59 (bobot terbaik) |
|---|---:|---:|
| Box precision | 0.8959 | 0.8331 |
| Box recall | 0.7846 | 0.8229 |
| Box mAP50 | 0.8718 | 0.8753 |
| Box mAP50-95 | 0.6625 | 0.6545 |
| Mask precision | 0.8994 | 0.8680 |
| Mask recall | 0.7857 | 0.7867 |
| Mask mAP50 | 0.8592 | 0.8663 |
| Mask mAP50-95 | 0.5924 | **0.5979** |
| `val/box_loss` | 1.0731 | 1.0897 |
| `val/seg_loss` | 1.7581 | 1.6124 |

Bobot terbaik dipilih berdasarkan mAP50-95 mask. Pada epoch 59 nilai tersebut
mencapai 0.5979, lebih tinggi 0.0055 dibanding epoch 100. Sebaliknya, box
mAP50-95 pada epoch 100 sedikit lebih tinggi, yaitu 0.6625 dibanding 0.6545.
Perbedaan ini menunjukkan bahwa metrik box dan mask tidak selalu bergerak ke
arah yang sama pada epoch akhir.

### 2.2 Evaluasi ulang bobot terbaik pada split validasi

| Metrik | Mask | Box |
|---|---:|---:|
| Precision | 0.8836 | 0.8848 |
| Recall | 0.7864 | 0.7859 |
| F1 | 0.8322 | 0.8324 |
| mAP50 | 0.8567 | 0.8703 |
| mAP50-95 | 0.5926 | 0.6604 |

Evaluasi ulang dijalankan dengan `start_eval.py` pada ambang confidence 0.25.
Selisih kecil terhadap laporan training berasal dari ambang confidence dan
proses validasi yang dijalankan terpisah.

---

## 3. Metrik per kelas

Sumber: [`reports/val_class_metrics.csv`](runs/segment/runs/semua_kelas_yolo26n/reports/val_class_metrics.csv).

### 3.1 Metrik bounding box

| Kelas | Gambar | Instance | Box P | Box R | Box F1 | Box mAP50 | Box mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| pohon | 76 | 76 | 0.9351 | 1.0000 | 0.9665 | 0.9950 | 0.9419 |
| mobil | 87 | 269 | 0.9379 | 0.6738 | 0.7842 | 0.8277 | 0.5465 |
| motor | 61 | 358 | 0.9195 | 0.7657 | 0.8356 | 0.9006 | 0.6512 |
| orang | 93 | 281 | 0.8367 | 0.7367 | 0.7835 | 0.7917 | 0.5729 |
| lubang | 60 | 88 | 0.8062 | 0.7159 | 0.7584 | 0.8232 | 0.5833 |

### 3.2 Metrik mask

| Kelas | Gambar | Instance | Mask P | Mask R | Mask F1 | Mask mAP50 | Mask mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| pohon | 76 | 76 | 0.9350 | 1.0000 | 0.9664 | 0.9950 | 0.8899 |
| mobil | 87 | 269 | 0.9328 | 0.6705 | 0.7802 | 0.8263 | 0.4853 |
| motor | 61 | 358 | 0.9565 | 0.7977 | 0.8699 | 0.9007 | 0.5655 |
| orang | 93 | 281 | 0.8120 | 0.7153 | 0.7606 | 0.7619 | 0.5082 |
| lubang | 60 | 88 | 0.8115 | 0.7273 | 0.7671 | 0.8164 | 0.5302 |

Kelas `pohon` paling mudah dideteksi karena bentuk dan ukurannya relatif
konsisten, dengan recall 1.0000 pada box maupun mask. Kelas `motor` memiliki
jumlah instance terbanyak, yaitu 358, dan tetap memperoleh mAP50 box 0.9006.
Kelas `mobil` memiliki presisi tinggi, tetapi recall box hanya 0.6738 sehingga
banyak instance terlewat. Kelas `lubang` memiliki presisi box paling rendah,
yaitu 0.8062, dan mAP50-95 mask 0.5302. Kelas `orang` memiliki presisi box
0.8367 dengan 24 false negative pada evaluasi tingkat gambar.

### 3.3 Akurasi tingkat gambar

Evaluasi ini menghitung benar atau salahnya keberadaan setiap kelas pada satu
gambar, bukan kualitas lokasi box atau mask. Ambang confidence yang dipakai
adalah 0.25.

| Kelas | TP | FP | FN | TN | Akurasi gambar | F1 gambar |
|---|---:|---:|---:|---:|---:|---:|
| pohon | 76 | 0 | 0 | 236 | 1.0000 | 1.0000 |
| mobil | 84 | 5 | 3 | 220 | 0.9744 | 0.9545 |
| motor | 60 | 1 | 1 | 250 | 0.9936 | 0.9836 |
| orang | 69 | 0 | 24 | 219 | 0.9231 | 0.8519 |
| lubang | 50 | 11 | 10 | 241 | 0.9327 | 0.8264 |

Secara keseluruhan diperoleh akurasi 0.8333 atau 260 dari 312 gambar benar,
dengan precision 0.9522, recall 0.8992, F1-mikro 0.9250, dan F1-makro 0.9233.
Kelas `orang` memiliki 24 false negative, sedangkan kelas `lubang` memiliki 11
false positive dan 10 false negative.

---

## 4. Ketahanan per varian gambar

Dataset validasi terdiri atas empat varian pengambilan gambar. Tabel berikut
menunjukkan kestabilan model pada masing-masing varian.

| Varian | Gambar | Mask P | Mask R | Mask F1 | Mask mAP50 | Mask mAP50-95 | Box mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|
| gerak diagonal | 78 | 0.8890 | 0.7927 | 0.8381 | 0.8688 | 0.5893 | 0.6532 |
| gerak horizontal | 81 | 0.8746 | 0.8107 | 0.8415 | 0.8676 | 0.6017 | 0.6715 |
| gerak vertikal | 76 | 0.8713 | 0.7792 | 0.8227 | 0.8400 | 0.5803 | 0.6549 |
| getar | 77 | 0.8855 | 0.7888 | 0.8344 | 0.8558 | 0.6125 | 0.6724 |

Rentang mask mAP50-95 antarvarian adalah 0.5803 sampai 0.6125. Varian `getar`
memperoleh nilai tertinggi, sedangkan `gerak vertikal` memperoleh nilai
terendah. Selisih tersebut relatif kecil sehingga model cukup stabil terhadap
perubahan sudut dan gerakan kamera.

---

## 5. Grafik

### 5.1 Ringkasan training per epoch

Grafik ini memuat loss training dan validasi serta seluruh metrik box dan mask
selama 100 epoch.

![Ringkasan metrik training per epoch](runs/segment/runs/semua_kelas_yolo26n/results.png)

### 5.2 Kurva Precision-Recall

| Mask | Box |
|---|---|
| ![Kurva PR mask](runs/segment/runs/semua_kelas_yolo26n/MaskPR_curve.png) | ![Kurva PR box](runs/segment/runs/semua_kelas_yolo26n/BoxPR_curve.png) |

### 5.3 Kurva F1

| Mask | Box |
|---|---|
| ![Kurva F1 mask](runs/segment/runs/semua_kelas_yolo26n/MaskF1_curve.png) | ![Kurva F1 box](runs/segment/runs/semua_kelas_yolo26n/BoxF1_curve.png) |

### 5.4 Confusion matrix

| Confusion matrix | Confusion matrix ternormalisasi |
|---|---|
| ![Confusion matrix](runs/segment/runs/semua_kelas_yolo26n/confusion_matrix.png) | ![Confusion matrix ternormalisasi](runs/segment/runs/semua_kelas_yolo26n/confusion_matrix_normalized.png) |

### 5.5 Contoh ground truth dan prediksi validasi

| Batch | Ground truth | Prediksi |
|---|---|---|
| 0 | ![Label validasi batch 0](runs/segment/runs/semua_kelas_yolo26n/val_batch0_labels.jpg) | ![Prediksi validasi batch 0](runs/segment/runs/semua_kelas_yolo26n/val_batch0_pred.jpg) |
| 1 | ![Label validasi batch 1](runs/segment/runs/semua_kelas_yolo26n/val_batch1_labels.jpg) | ![Prediksi validasi batch 1](runs/segment/runs/semua_kelas_yolo26n/val_batch1_pred.jpg) |
| 2 | ![Label validasi batch 2](runs/segment/runs/semua_kelas_yolo26n/val_batch2_labels.jpg) | ![Prediksi validasi batch 2](runs/segment/runs/semua_kelas_yolo26n/val_batch2_pred.jpg) |

Contoh hasil pada batch training juga tersedia di
[`train_batch0.jpg`](runs/segment/runs/semua_kelas_yolo26n/train_batch0.jpg),
[`train_batch1.jpg`](runs/segment/runs/semua_kelas_yolo26n/train_batch1.jpg),
dan [`train_batch2.jpg`](runs/segment/runs/semua_kelas_yolo26n/train_batch2.jpg).

### 5.6 Grafik evaluasi tambahan

| Ringkasan total | Metrik per kelas |
|---|---|
| ![Ringkasan total](runs/segment/runs/semua_kelas_yolo26n/evaluation/grafik/1_ringkasan_total.png) | ![Metrik per kelas](runs/segment/runs/semua_kelas_yolo26n/evaluation/grafik/2_per_kelas.png) |

| Metrik per varian | Akurasi tingkat gambar |
|---|---|
| ![Metrik per varian](runs/segment/runs/semua_kelas_yolo26n/evaluation/grafik/3_per_varian.png) | ![Akurasi tingkat gambar](runs/segment/runs/semua_kelas_yolo26n/evaluation/grafik/4_tingkat_gambar.png) |

Contoh prediksi yang benar dan salah tersimpan di
[`evaluation/contoh_prediksi/benar/`](runs/segment/runs/semua_kelas_yolo26n/evaluation/contoh_prediksi/benar/)
dan
[`evaluation/contoh_prediksi/salah/`](runs/segment/runs/semua_kelas_yolo26n/evaluation/contoh_prediksi/salah/).
Daftar kesalahan per gambar ada di
[`evaluation/kesalahan_gambar.csv`](runs/segment/runs/semua_kelas_yolo26n/evaluation/kesalahan_gambar.csv).

Grafik kurva P, R, dan F1 untuk box serta mask juga tersedia di folder
[`runs/segment/runs/semua_kelas_yolo26n/`](runs/segment/runs/semua_kelas_yolo26n/).

---

## 6. Log mentah dan artefak CSV

Log mentah pelatihan dan evaluasi disertakan agar hasil dapat diperiksa ulang.

| File | Isi |
|---|---|
| [`training_semua_20261106_214551_275012.log`](training_semua_20261106_214551_275012.log) | Log sesi training pertama, 6 November 2026, 2.4 MB |
| [`training_semua_20261107_002155_904083.log`](training_semua_20261107_002155_904083.log) | Log sesi training kedua, 7 November 2026, 6.4 MB |
| [`runs/segment/runs/semua_kelas_yolo26n/raw/training.log`](runs/segment/runs/semua_kelas_yolo26n/raw/training.log) | Salinan log mentah run terakhir, identik dengan log sesi kedua |
| [`runs/segment/runs/semua_kelas_yolo26n/evaluation/evaluation_20261107_091624.log`](runs/segment/runs/semua_kelas_yolo26n/evaluation/evaluation_20261107_091624.log) | Log evaluasi akurasi, ketahanan varian, dan kecepatan |

Artefak metrik:

| File | Isi |
|---|---|
| [`results.csv`](runs/segment/runs/semua_kelas_yolo26n/results.csv) | Metrik mentah setiap epoch, 100 baris |
| [`reports/epoch_metrics.csv`](runs/segment/runs/semua_kelas_yolo26n/reports/epoch_metrics.csv) | Metrik per epoch dalam bentuk yang sudah dirapikan |
| [`reports/val_class_metrics.csv`](runs/segment/runs/semua_kelas_yolo26n/reports/val_class_metrics.csv) | Metrik box dan mask per kelas |
| [`reports/training_report.json`](runs/segment/runs/semua_kelas_yolo26n/reports/training_report.json) | Laporan terstruktur epoch terakhir dan epoch terbaik |
| [`reports/training_report.txt`](runs/segment/runs/semua_kelas_yolo26n/reports/training_report.txt) | Ringkasan training dalam teks |
| [`reports/artifacts.json`](runs/segment/runs/semua_kelas_yolo26n/reports/artifacts.json) | Daftar seluruh artefak run |
| [`evaluation/per_kelas.csv`](runs/segment/runs/semua_kelas_yolo26n/evaluation/per_kelas.csv) | Metrik per kelas hasil evaluasi ulang |
| [`evaluation/per_varian.csv`](runs/segment/runs/semua_kelas_yolo26n/evaluation/per_varian.csv) | Metrik per varian gambar |
| [`evaluation/tingkat_gambar_per_kelas.csv`](runs/segment/runs/semua_kelas_yolo26n/evaluation/tingkat_gambar_per_kelas.csv) | TP, FP, FN, TN, akurasi, dan F1 tingkat gambar |
| [`evaluation/kesalahan_gambar.csv`](runs/segment/runs/semua_kelas_yolo26n/evaluation/kesalahan_gambar.csv) | Daftar gambar yang salah beserta jenis kesalahannya |
| [`evaluation/ringkasan_test.json`](runs/segment/runs/semua_kelas_yolo26n/evaluation/ringkasan_test.json) | Ringkasan evaluasi dalam JSON |
| [`evaluation/kecepatan.json`](runs/segment/runs/semua_kelas_yolo26n/evaluation/kecepatan.json) | Hasil pengukuran kecepatan inferensi |

Log memuat keluaran terminal selama pelatihan, progress bar per epoch, nilai
loss, metrik validasi, learning rate, peringatan, dan waktu pemrosesan. File
`results.csv` dapat dibuka langsung dengan spreadsheet atau diolah dengan
pandas.

---

## 7. Alur integrasi: YOLO, fuzzy, suara, FastAPI, dan Cloudflare

### 7.1 Diagram alur

```
Kamera ponsel atau unggahan gambar
        |
        v
FastAPI /deteksi  (server_rest_api.py)
        |
        v
YOLO26n-Seg  (models/best.pt)  ->  box, mask, kelas, confidence
        |
        v
Fuzzy Sugeno  (fuzzysugeno.py)  ->  urgensi 0-100
        |
        v
AMAN / INFO / WASPADA / BAHAYA  ->  JSON, getaran, pesan suara
        |
        v
Browser ponsel: Web Speech API (id-ID)  atau  PemutarPeringatan di server
```

Pipeline CLI terdapat di [`inferensi_vest.py`](inferensi_vest.py). Pipeline ini
menjalankan YOLO, memanggil `analisis_hasil` dari `fuzzysugeno.py`, lalu
memutar peringatan melalui `PemutarPeringatan` atau fallback TTS `edge-tts`.
Server FastAPI terdapat di [`server_rest_api.py`](server_rest_api.py) dan
memakai pipeline yang sama.

### 7.2 Fuzzy Sugeno

Fuzzy Sugeno orde-nol memakai tiga variabel masukan:

1. Jarak objek dalam meter, berasal dari geometri bounding box dan dapat
   digabung dengan sensor ultrasonik pada rentang 0.03 sampai 3.0 meter.
2. Tingkat bahaya kelas: `lubang`, `motor`, dan `mobil` bernilai 10;
   `orang` dan `pohon` bernilai 6.
3. Rasio keterhalangan jalur, yaitu bagian mask objek yang berada di koridor
   jalan di depan pengguna.

Himpunan fuzzy jarak adalah `sangat_dekat`, `dekat`, `sedang`, dan `jauh`.
Himpunan fuzzy bahaya adalah `rendah`, `sedang`, dan `tinggi`. Himpunan fuzzy
jalur adalah `luar`, `sebagian`, dan `penuh`. Basis aturan berisi 26 aturan
dengan konsekuen crisp, lalu nilai akhir dihitung sebagai rata-rata berbobot.

| Level | Rentang urgensi | Pola getaran |
|---|---|---|
| AMAN | 0 sampai kurang dari 25 | PWM 0, mati |
| INFO | 25 sampai kurang dari 50 | PWM 80, interval 1000 ms |
| WASPADA | 50 sampai kurang dari 75 | PWM 120, interval 600 ms |
| BAHAYA | 75 sampai 100 | PWM 255, interval 150 ms |

Jarak kritis ditetapkan 0.90 meter dan jarak tengah 1.50 meter. Untuk objek
yang berada di depan, hasil estimasi kamera dan ultrasonik digabung dengan
mengambil nilai minimum. Sistem juga menyimpan ingatan objek `lubang` yang
sempat terlihat selama 2.5 detik agar peringatan tidak langsung hilang saat
objek keluar dari frame.

### 7.3 Endpoint API

| Endpoint | Kegunaan | Kunci API |
|---|---|---|
| `GET /app` | Halaman kamera, hasil fuzzy, dan suara browser | Tidak |
| `GET /` | Informasi singkat dan status model | Tidak |
| `GET /status` | Health check proses, model, dan suara | Tidak |
| `GET /docs` | Dokumentasi interaktif FastAPI | Tidak |
| `POST /deteksi` | Gambar dan jarak opsional, menghasilkan JSON deteksi dan urgensi | Wajib |
| `POST /deteksi/suara` | Deteksi dan opsi pemutaran suara di server | Wajib |
| `POST /peringatan` | Perhitungan fuzzy tanpa gambar | Wajib |
| `GET /riwayat` | Riwayat deteksi dalam format JSONL | Wajib |

Endpoint operasi memerlukan header `X-API-Key` yang nilainya sama dengan
`VEST_API_KEY` di `.env`. Kunci wajib berupa string acak minimal 32 karakter.
Unggahan gambar dibatasi 10 MB. Server secara default hanya mendengarkan di
`127.0.0.1:8000`.

Dokumentasi API publik, contoh permintaan, kode error, dan panduan Cloudflare
Tunnel tersedia di [`API_CLOUDFLARE.md`](API_CLOUDFLARE.md).

### 7.4 Contoh permintaan

Deteksi objek dan fuzzy:

```powershell
curl.exe -X POST http://127.0.0.1:8000/deteksi `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -F "gambar=@foto_jalan.jpg" `
  -F "jarak_m=0.45"
```

Deteksi sekaligus memutar suara di server:

```powershell
curl.exe -X POST http://127.0.0.1:8000/deteksi/suara `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -F "gambar=@foto_jalan.jpg" `
  -F "jarak_m=0.45"
```

Perhitungan fuzzy tanpa gambar:

```powershell
curl.exe -X POST http://127.0.0.1:8000/peringatan `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -H "Content-Type: application/json" `
  -d "{\"skor_risiko\":0.9,\"jarak_m\":0.5}"
```

Contoh respons fuzzy untuk jarak 1.0 meter dan skor risiko 0.9 menghasilkan
urgensi sekitar 98.3 dengan level `BAHAYA`. Contoh lain: mobil pada jarak 1.2
meter menghasilkan urgensi 95, orang pada jarak 2.0 meter menghasilkan urgensi
50 dengan level `WASPADA`, dan pohon pada jarak 4.0 meter menghasilkan urgensi
8.3 dengan level `AMAN`.

---

## 8. Efisiensi

| Item | Nilai |
|---|---|
| Parameter | 3,054,875 atau sekitar 3.05 juta |
| Layer | 309 |
| GFLOPs | 10.3, menjadi 9.1 setelah fused |
| Ukuran bobot | 6.28 MB atau 6,585,245 byte |
| Waktu latih total | 31,537 detik atau 8 jam 45 menit 37 detik |
| Rata-rata per epoch | 315.4 detik atau 5 menit 15 detik |
| Inferensi murni | 13.6 ms per gambar |
| Total per gambar | 20.69 ms per gambar atau sekitar 48.3 FPS |
| Perangkat pengukuran | GTX 1650 Max-Q 4 GB, batch 1 |

Waktu latih dihitung dari kolom `time` pada epoch 100 dan mencakup validasi
setiap epoch. Pengukuran kecepatan dilakukan dengan `start_eval.py` pada 100
gambar, termasuk praproses dan pascaproses.

---

## 9. Kesimpulan

1. Model YOLO26n-Seg berhasil dilatih selama 100 epoch pada lima kelas dengan
   mask mAP50 0.8592 dan mask mAP50-95 0.5924 pada epoch 100.
2. Bobot terbaik berdasarkan mask mAP50-95 adalah epoch 59 dengan nilai
   0.5979, mask mAP50 0.8663, dan box mAP50 0.8753.
3. Metrik box lebih tinggi daripada mask. Box mAP50-95 mencapai 0.6604,
   sedangkan mask mAP50-95 mencapai 0.5926 pada evaluasi ulang.
4. Kelas `pohon` paling akurat dengan mAP50 box dan mask 0.9950 serta recall
   1.0000. Kelas `mobil` memiliki recall terendah, sedangkan kelas `lubang`
   memiliki presisi box terendah.
5. Akurasi tingkat gambar mencapai 0.8333 atau 260 dari 312 gambar benar pada
   ambang confidence 0.25, dengan F1-mikro 0.9250 dan F1-makro 0.9233.
6. Model cukup stabil pada empat varian gambar. Mask mAP50-95 berada pada
   rentang 0.5803 sampai 0.6125.
7. Kecepatan inferensi sekitar 48.3 FPS pada GTX 1650 Max-Q 4 GB, sehingga
   model layak dipakai untuk deteksi waktu nyata pada rompi.
8. Integrasi YOLO, fuzzy Sugeno, output suara, FastAPI, dan Cloudflare Tunnel
   sudah berjalan. Halaman `/app` dapat dipakai dari ponsel melalui HTTPS.

### 9.1 Keterbatasan

1. Evaluasi utama memakai split validasi, bukan split test terpisah. Angka
   akurasi dapat berubah jika diuji pada data lapangan yang berbeda.
2. Kelas `mobil`, `orang`, dan `lubang` masih memiliki false negative yang
   cukup terlihat pada tingkat gambar.
3. Pengukuran kecepatan dilakukan pada satu perangkat GPU. Perangkat ponsel
   atau CPU akan memberikan waktu inferensi yang berbeda.
4. Kualitas mask pada objek kecil dan objek yang saling menutupi masih perlu
   ditingkatkan.

### 9.2 Rekomendasi

1. Tambahkan data latih untuk kelas `mobil`, `orang`, dan `lubang`, terutama
   pada kondisi malam, hujan, dan objek yang terhalang.
2. Pertimbangkan penambahan augmentasi khusus objek kecil atau peningkatan
   `imgsz` jika perangkat inference memungkinkan.
3. Lakukan evaluasi pada split test terpisah dan data lapangan sebelum
   menetapkan ambang confidence produksi.
4. Kalibrasi ulang ambang fuzzy dan confidence berdasarkan hasil uji lapangan
   bersama pengguna rompi.

---

## 10. Struktur repositori

```
VestCare-Vest-Detection-Stage-2/
├── README.md                         halaman utama dokumentasi
├── README_INTEGRASI.md               panduan integrasi API, suara, dan tunnel
├── API_CLOUDFLARE.md                 dokumentasi API publik Cloudflare
├── HASIL_TRAINING.md                 laporan training versi lengkap
├── .env.example                      template variabel lingkungan
├── .gitignore                        aturan ignore Git
├── requirements.txt                  dependensi Python
├── dataset_gabungan.yaml             konfigurasi dataset gabungan
├── train_semua.py                    skrip pelatihan lima kelas
├── start_train.py                    pembungkus pelatihan
├── start_eval.py                     evaluasi akurasi, varian, dan kecepatan
├── inferensi_vest.py                 pipeline YOLO, fuzzy, dan suara
├── fuzzysugeno.py                    fuzzy Sugeno dan aturan urgensi
├── server_rest_api.py                server FastAPI
├── app.py                            entry point ASGI untuk `uvicorn app:app`
├── config_env.py                     pembaca file .env
├── start_server.py                   starter server dengan validasi kunci
├── start_tunnel.py                   starter Cloudflare Tunnel
├── run_server.bat                    menjalankan server FastAPI
├── run_tunnel.bat                    menjalankan Cloudflare Tunnel
├── start_all.bat                     menjalankan server dan tunnel
├── cloudflared.yml                   konfigurasi Cloudflare Tunnel
├── web/
│   └── index.html                    halaman kamera dan suara browser
├── models/
│   ├── best.pt                       bobot terbaik untuk inferensi
│   └── best_semua_kelas.pt           salinan bobot semua kelas
├── yolo26n-seg.pt                    bobot pralatih Ultralytics
├── suara-natural-ai/                 modul suara dan pemutar peringatan
├── runs/segment/runs/semua_kelas_yolo26n/
│   ├── weights/best.pt               bobot hasil training
│   ├── weights/last.pt               bobot epoch terakhir
│   ├── results.csv                   metrik per epoch
│   ├── results.png                   grafik ringkasan training
│   ├── Box*.png dan Mask*.png        kurva P, R, PR, dan F1
│   ├── confusion_matrix*.png         confusion matrix
│   ├── train_batch*.jpg              contoh batch training
│   ├── val_batch*_labels.jpg         ground truth validasi
│   ├── val_batch*_pred.jpg           prediksi validasi
│   ├── reports/                      laporan JSON, TXT, dan CSV
│   ├── raw/                          log dan CSV mentah
│   └── evaluation/                   evaluasi akurasi dan kecepatan
└── training_semua_*.log              log mentah sesi training
```

Folder dataset seperti `dataset_lubang/`, `dataset_mobil/`, `dataset_motor/`,
`dataset_orang/`, dan `dataset_pohon/` tidak disertakan di repositori karena
ukurannya besar. Dataset tersebut diperlukan hanya saat melatih ulang model.

---

## 11. Menjalankan ulang

### 11.1 Prasyarat

- Python 3.12 dan pip.
- Virtual environment pada folder `.venv`.
- GPU CUDA bila ingin melatih ulang dengan kecepatan penuh. Pelatihan masih
  dapat berjalan di CPU, tetapi waktu latih akan jauh lebih lama.
- FFmpeg untuk konversi audio pada fitur suara.
- `cloudflared` untuk publikasi melalui Cloudflare Tunnel.

### 11.2 Instalasi

```powershell
git clone https://github.com/saiful-rizal/VestCare-Vest-Detection-Stage-2.git
cd VestCare-Vest-Detection-Stage-2

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Salin konfigurasi contoh, lalu isi `VEST_API_KEY` dengan kunci acak minimal 32
karakter:

```powershell
Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

`config_env.py` akan memuat `.env` secara otomatis saat server dijalankan.
Jangan commit atau membagikan file `.env`.

### 11.3 Melatih ulang model

Letakkan lima dataset pada folder berikut:

```
dataset_lubang/3_pengayaan_gerak/data.yaml
dataset_mobil/3_pengayaan_gerak/data.yaml
dataset_motor/3_pengayaan_gerak/data.yaml
dataset_orang/3_pengayaan_gerak/data.yaml
dataset_pohon/3_pengayaan_gerak/data.yaml
```

Sesuaikan daftar `DATASETS` di `train_semua.py` jika lokasi dataset berbeda.
Skrip akan menggabungkan dataset, membuat split train/val, menulis
`dataset_gabungan.yaml`, lalu menjalankan training:

```powershell
.\.venv\Scripts\python.exe start_train.py
```

Konfigurasi utama yang dipakai: 100 epoch, `imgsz` 416, `batch` 8, AdamW,
`lr0` 0.001, `patience` 50, dan pemilihan bobot berdasarkan mAP50-95 mask.
Hasil run akan tersimpan di folder `runs/segment/runs/`.

### 11.4 Evaluasi ulang

```powershell
.\.venv\Scripts\python.exe start_eval.py `
  --model models\best.pt `
  --out runs\segment\runs\semua_kelas_yolo26n\evaluation
```

Evaluasi default memakai split `val`, `imgsz` 416, `batch` 1, dan
`conf` 0.25. Skrip menghasilkan metrik per kelas, metrik per varian, akurasi
tingkat gambar, daftar kesalahan, contoh prediksi, grafik, dan pengukuran
kecepatan.

### 11.5 Menjalankan server dan tunnel

Server lokal:

```powershell
.\run_server.bat
```

Buka `http://127.0.0.1:8000/app` untuk halaman kamera dan suara, atau
`http://127.0.0.1:8000/docs` untuk dokumentasi API.

Server dan Cloudflare Tunnel sekaligus:

```powershell
.\start_all.bat
```

Tanpa `CLOUDFLARED_TOKEN`, tunnel memakai Quick Tunnel dengan URL sementara.
Dengan token, tunnel berjalan sebagai tunnel terkelola. Setelah URL HTTPS
muncul, buka URL tersebut dengan akhiran `/app`, masukkan `VEST_API_KEY`, lalu
izinkan akses kamera dan suara di ponsel.

---

## 12. Lisensi dan kontak

Proyek ini dikembangkan untuk penelitian dan tugas akhir **VestCare Rompi
Cerdas Stage 2**. Kode dan dokumentasi mengikuti kebijakan pemilik repositori.

Repositori:
[saiful-rizal/VestCare-Vest-Detection-Stage-2](https://github.com/saiful-rizal/VestCare-Vest-Detection-Stage-2)
