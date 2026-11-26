<p align="center">
  <img src="assets/vestcare-title.svg" alt="VestCare - Rompi Cerdas (Stage 2)" width="900">
</p>

Sistem peringatan rintangan untuk rompi cerdas berbasis segmentasi YOLO26n, logika fuzzy Sugeno, dan suara natural Bahasa Indonesia. Model mendeteksi lima kelas, yaitu pohon, mobil, motor, orang, dan lubang. Hasil deteksi dipetakan menjadi arah, jarak, tingkat risiko, instruksi suara, serta riwayat perangkat pada Supabase. Dashboard menampilkan posisi, jarak ultrasonik, dan telemetri GPS Wemos secara realtime pada peta Google Maps.

## Ringkasan sistem

| Komponen | Keterangan |
|---|---|
| Model visi | YOLO26n-seg, 5 kelas, keluaran bounding box dan mask |
| Logika keputusan | Fuzzy Sugeno orde-nol dengan 26 aturan |
| Keluaran peringatan | Level AMAN, INFO, WASPADA, BAHAYA; getar; instruksi suara |
| Suara | Klip Bahasa Indonesia dari `data/runtime/audio/cache_ardi` |
| API | FastAPI, autentikasi API key atau cookie sesi HttpOnly |
| Web | Dashboard React + Vite yang disajikan langsung oleh FastAPI |
| Penyimpanan | Riwayat lokal JSONL dan sinkronisasi ke Supabase |
| Perangkat | Satu perangkat virtual server dengan UUID tetap |

## Hasil training terbaru

Run yang dipublikasikan:

```text
data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/
```

### Konfigurasi training

| Parameter | Nilai |
|---|---|
| Model dasar | `yolo26n-seg.pt` |
| Epoch | 100 / 100 |
| Image size | 512 |
| Batch | 4 |
| Optimizer | AdamW |
| Learning rate awal | 0.001 |
| Seed / deterministic | 0 / ya |
| Device | GPU 0, NVIDIA GeForce GTX 1650 Max-Q |
| Dataset train | 2.778 gambar |
| Dataset validasi | 312 gambar |
| Overlap train dan validasi | 0 gambar |
| Waktu training | 29.825,4 detik atau sekitar 8,28 jam |
| Checkpoint terbaik | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/weights/best.pt` |

### Hyperparameter lengkap run

Nilai berikut berasal dari `args.yaml` run tersebut dan konfigurasi yang diberikan oleh `train_semua.py`.

| Kelompok | Parameter | Nilai |
|---|---|---|
| Reproduksibilitas | Seed split / training | `0` / `0` |
| Reproduksibilitas | Deterministic | `True` |
| Reproduksibilitas | Cache / AMP | `False` / `True` |
| Eksekusi | Task / pretrained | Segmentasi / `True` |
| Eksekusi | Epoch maksimum / patience | `100` / `50` |
| Eksekusi | Batch / image size | `4` / `512` |
| Eksekusi | Device / workers | GPU `0` / `0` |
| Optimisasi | Optimizer | `AdamW` |
| Optimisasi | `lr0` / `lrf` | `0.001` / `0.01` |
| Optimisasi | Momentum / weight decay | `0.937` / `0.0005` |
| Optimisasi | Label smoothing | `0.1` |
| Warmup | Epoch / momentum / bias LR | `3.0` / `0.8` / `0.1` |
| Loss | Box / cls / DFL | `7.5` / `0.5` / `1.5` |
| Augmentasi warna | HSV H / S / V | `0.015` / `0.7` / `0.4` |
| Augmentasi geometri | Degrees / translate / scale | `10` / `0.1` / `0.5` |
| Augmentasi geometri | Shear / perspective | `0` / `0` |
| Flip | Horizontal / vertikal | `0.5` / `0` |
| Augmentasi gambar | Mosaic / mixup | `1.0` / `0` |
| Augmentasi gambar | Cutmix / copy-paste / erasing | `0` / `0` / `0.4` |
| Training | Close mosaic / nominal batch size | `10` epoch terakhir / `64` |
| Evaluasi | Split / IoU / max detections | `val` / `0.7` / `300` |
| Quality gate | Target precision dan mAP50 tiap kelas | `98%`; run belum lulus |

### Split dataset dan seed

Run terbaru memakai pembagian aktual 90% train dan 10% validasi, bukan 80% train dan 20% validasi. Nilai pembagi berada di `train_semua.py` pada `VAL_FRACTION = 0.10`.

| Parameter split | Nilai |
|---|---|
| `VAL_FRACTION` | 0,10 |
| Proporsi train | 90% |
| Proporsi validasi | 10% |
| Jumlah gambar train | 2.778 |
| Jumlah gambar validasi | 312 |
| Total gambar | 3.090 |
| Persentase train aktual | 89,90% |
| Persentase validasi aktual | 10,10% |
| Seed pengacakan split | 0, memakai `random.Random(0)` |
| Seed training | 0, memakai `SEED_LATIH = 0` |
| Deterministic | `True` |
| Cache dataset | `False` |
| AMP | `True` |
| Manifest train | `data/results/runs/dataset_splits/train.txt` |
| Manifest validasi | `data/results/runs/dataset_splits/val.txt` |

Cara split bekerja:

1. Gambar dikelompokkan berdasarkan nama sebelum penanda `__`, sehingga varian dari objek yang sama tidak terpisah antara train dan validasi.
2. Daftar grup diacak dengan `random.Random(0)`.
3. Sebanyak 10% grup dipilih sebagai validasi.
4. Sisa grup menjadi train.
5. Pipeline memastikan kelima kelas tetap muncul di train dan validasi.
6. Hasil split ditulis ke `train.txt` dan `val.txt`, lalu dibaca oleh `dataset_gabungan.yaml`.

Jika ingin memakai 80% train dan 20% validasi, ubah `VAL_FRACTION = 0.20` di `train_semua.py`, lalu jalankan training ulang. Metrik pada README ini tetap berlaku untuk split 90/10 dan tidak dapat dibandingkan langsung dengan hasil split 80/20.

### Tabel indikator utama

| Indikator | Nilai | Keterangan |
|---|---:|---|
| Jumlah kelas | 5 | pohon, mobil, motor, orang, lubang |
| Box precision | 0,8851 | 88,51% |
| Box recall | 0,7806 | 78,06% |
| Box F1 | 0,8295 | 82,95% |
| Box mAP50 | 0,8541 | 85,41% |
| Box mAP50-95 | 0,6477 | 64,77% |
| Mask precision | 0,8908 | 89,08% |
| Mask recall | 0,7822 | 78,22% |
| Mask F1 | 0,8330 | 83,30% |
| Mask mAP50 | 0,8476 | 84,76% |
| Mask mAP50-95 | 0,6118 | 61,18% |
| Akurasi tingkat gambar | 0,8045 | 251 dari 312 gambar benar, confidence minimal 0,25 |
| Presisi tingkat gambar | 0,9220 | 92,20% |
| Recall tingkat gambar | 0,9098 | 90,98% |
| F1 mikro tingkat gambar | 0,9159 | 91,59% |
| F1 makro tingkat gambar | 0,9143 | 91,43% |
| Kecepatan inferensi | 17,21 ms/gambar | Sekitar 58,1 FPS, batch 1, termasuk praproses dan pascaproses |
| Status quality gate | Belum lulus | Ambang 98% per kelas belum terpenuhi |
| Bobot aktif | Tidak diganti otomatis | `models/best.pt` dipertahankan |

### Nilai mentah metrik validasi

Nilai berikut diambil tanpa pembulatan dari `reports/training_report.json` bagian `validation.val.overall`.

| Metrik | Nilai mentah |
|---|---:|
| `metrics/precision(B)` | 0,8850734184435352 |
| `metrics/recall(B)` | 0,7805736969039915 |
| `metrics/mAP50(B)` | 0,8539829367863725 |
| `metrics/mAP50-95(B)` | 0,6476855973686102 |
| `metrics/precision(M)` | 0,8902456090770972 |
| `metrics/recall(M)` | 0,7821941168477433 |
| `metrics/mAP50(M)` | 0,8492560575568179 |
| `metrics/mAP50-95(M)` | 0,6105370743416991 |
| `fitness` | 1,2582226717103093 |

### Nilai mentah evaluasi akhir

Nilai berikut diambil tanpa pembulatan dari `evaluation/final/ringkasan_test.json` bagian `total`.

| Metrik | Nilai mentah |
|---|---:|
| `box_p` | 0,8850735547755999 |
| `box_r` | 0,7805736991191967 |
| `box_f1` | 0,8295455559732847 |
| `box_map50` | 0,8541196336724688 |
| `box_map5095` | 0,6477190263615329 |
| `mask_p` | 0,8907641021745532 |
| `mask_r` | 0,7822356736376641 |
| `mask_f1` | 0,8329797380618063 |
| `mask_map50` | 0,8475512387723771 |
| `mask_map5095` | 0,6117560521272606 |

### Nilai mentah akurasi tingkat gambar

| Indikator | Nilai mentah |
|---|---:|
| Jumlah gambar evaluasi | 312 |
| Gambar salah | 61 |
| `akurasi_tingkat_gambar` | 0,8045 |
| `presisi_mikro_gambar` | 0,922 |
| `recall_mikro_gambar` | 0,9098 |
| `f1_mikro_gambar` | 0,9159 |
| `f1_makro_gambar` | 0,9143 |

Jumlah gambar salah per varian:

| Varian | Gambar salah |
|---|---:|
| gerak_diagonal | 15 |
| gerak_horizontal | 20 |
| gerak_vertikal | 11 |
| getar | 15 |
| Total | 61 |

### Nilai mentah per kelas

| Kelas | Box P | Box R | Box mAP50 | Box mAP50-95 | Mask P | Mask R | Mask mAP50 | Mask mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pohon | 0,9846308092896334 | 1,0 | 0,995 | 0,9044289681099335 | 0,9852311366998912 | 1,0 | 0,995 | 0,8779504155763667 |
| mobil | 0,8977227397813299 | 0,7504810223014423 | 0,8456219367043477 | 0,5856976576013708 | 0,9153411133010018 | 0,7636846234338663 | 0,8448957447049819 | 0,5415880875912391 |
| motor | 0,9129262729881418 | 0,7907326690240791 | 0,8882323616367929 | 0,6385073092584529 | 0,9481858585069705 | 0,8178674102348811 | 0,9181640452954154 | 0,5801310784415681 |
| orang | 0,8582778957590607 | 0,7366548042704626 | 0,8081254651312417 | 0,5864025487005654 | 0,8273520603209127 | 0,7046263345195729 | 0,762822789011519 | 0,5308559823536135 |
| lubang | 0,7718100560598334 | 0,625 | 0,7336184048899628 | 0,5235586481373415 | 0,7777103420439897 | 0,625 | 0,7168736148499693 | 0,5282546966735155 |

### Data mentah dataset

| Item | Nilai |
|---|---:|
| Gambar train | 2.778 |
| Background train | 101 |
| File train rusak | 0 |
| Gambar validasi | 312 |
| Background validasi | 12 |
| File validasi rusak | 0 |
| Overlap gambar train dan validasi | 0 |
| Total instance validasi | 1.072 |
| Jumlah kelas | 5 |

Jumlah gambar dan instance validasi per kelas:

| Kelas | Gambar | Instance |
|---|---:|---:|
| pohon | 76 | 76 |
| mobil | 87 | 269 |
| motor | 61 | 358 |
| orang | 93 | 281 |
| lubang | 60 | 88 |
| Total | 377 | 1.072 |

Catatan: total gambar per kelas adalah jumlah kehadiran kelas pada gambar validasi, sehingga nilainya lebih besar dari 312 karena satu gambar dapat memuat beberapa kelas.

### Akurasi per kelas

| Kelas | Gambar | Instance | Box P | Box R | Box F1 | Box mAP50 | Box mAP50-95 | Mask P | Mask R | Mask F1 | Mask mAP50 | Mask mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| pohon | 76 | 76 | 0,9846 | 1,0000 | 0,9923 | 0,9950 | 0,9044 | 0,9852 | 1,0000 | 0,9926 | 0,9950 | 0,8780 |
| mobil | 87 | 269 | 0,8977 | 0,7505 | 0,8175 | 0,8456 | 0,5857 | 0,9153 | 0,7637 | 0,8327 | 0,8449 | 0,5416 |
| motor | 61 | 358 | 0,9129 | 0,7907 | 0,8474 | 0,8882 | 0,6385 | 0,9482 | 0,8179 | 0,8782 | 0,9182 | 0,5801 |
| orang | 93 | 281 | 0,8583 | 0,7367 | 0,7928 | 0,8081 | 0,5864 | 0,8274 | 0,7046 | 0,7611 | 0,7628 | 0,5309 |
| lubang | 60 | 88 | 0,7718 | 0,6250 | 0,6907 | 0,7336 | 0,5236 | 0,7777 | 0,6250 | 0,6930 | 0,7169 | 0,5283 |

### Akurasi tingkat gambar per kelas

| Kelas | TP | FP | FN | TN | Akurasi | Presisi | Recall | F1 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| pohon | 74 | 0 | 2 | 236 | 0,9936 | 1,0000 | 0,9737 | 0,9867 |
| mobil | 86 | 10 | 1 | 215 | 0,9647 | 0,8958 | 0,9885 | 0,9399 |
| motor | 60 | 4 | 1 | 247 | 0,9840 | 0,9375 | 0,9836 | 0,9600 |
| orang | 71 | 0 | 22 | 219 | 0,9295 | 1,0000 | 0,7634 | 0,8659 |
| lubang | 52 | 15 | 8 | 237 | 0,9263 | 0,7761 | 0,8667 | 0,8189 |

### Akurasi per varian dataset validasi

| Varian | Gambar | Box P | Box R | Box mAP50 | Box mAP50-95 | Mask P | Mask R | Mask mAP50 | Mask mAP50-95 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| gerak_diagonal | 78 | 0,8967 | 0,7746 | 0,8481 | 0,6320 | 0,9092 | 0,7850 | 0,8558 | 0,6132 |
| gerak_horizontal | 81 | 0,9046 | 0,7707 | 0,8566 | 0,6514 | 0,8943 | 0,7642 | 0,8465 | 0,6097 |
| gerak_vertikal | 76 | 0,8787 | 0,7911 | 0,8536 | 0,6532 | 0,9084 | 0,7863 | 0,8435 | 0,6109 |
| getar | 77 | 0,9074 | 0,7463 | 0,8616 | 0,6625 | 0,9172 | 0,7413 | 0,8468 | 0,6233 |

### Log saat training

Tabel berikut diambil dari `results.csv` dan log konsol training. Nilai loss adalah rata-rata epoch, sedangkan P, R, dan mAP adalah metrik validasi pada epoch tersebut.

| Epoch | Waktu kumulatif (detik) | Train box loss | Train seg loss | Train cls loss | Box P | Box R | Box mAP50 | Box mAP50-95 | Mask mAP50 | Mask mAP50-95 | Val box loss | Val seg loss |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 239,9 | 1,7667 | 2,9770 | 2,4139 | 0,6273 | 0,6203 | 0,6303 | 0,3846 | 0,6064 | 0,3682 | 1,5216 | 2,3380 |
| 25 | 5.209,8 | 1,2707 | 1,8983 | 1,0250 | 0,8446 | 0,7601 | 0,8157 | 0,5813 | 0,7859 | 0,5332 | 1,2465 | 1,8143 |
| 50 | 11.283,2 | 1,1094 | 1,6256 | 0,8177 | 0,8549 | 0,7687 | 0,8544 | 0,6223 | 0,8381 | 0,5865 | 1,1872 | 1,6694 |
| 75 | 16.371,0 | 0,9988 | 1,4697 | 0,6952 | 0,8807 | 0,7896 | 0,8613 | 0,6353 | 0,8491 | 0,6172 | 1,1383 | 1,5942 |
| 99 | 29.656,7 | 0,8301 | 1,2032 | 0,5005 | 0,8916 | 0,7696 | 0,8504 | 0,6427 | 0,8430 | 0,6128 | 1,0879 | 1,6335 |
| 100 | 29.825,4 | 0,8191 | 1,1944 | 0,4887 | 0,8823 | 0,7776 | 0,8493 | 0,6431 | 0,8404 | 0,6108 | 1,0804 | 1,6340 |

Ringkasan log konsol:

| Tahap | Catatan log |
|---|---|
| Pemindaian dataset train | 2.778 gambar, 101 background, 0 corrupt |
| Pemindaian dataset validasi | 312 gambar, 12 background, 0 corrupt |
| Mulai training | 100 epoch, optimizer AdamW, AMP aktif, deterministic |
| Akhir training | 100 dari 100 epoch selesai, tidak ada early stopping |
| Model akhir | 2.704.755 parameter, 9,1 GFLOPs |
| Evaluasi akhir | 312 gambar validasi, 5 kelas |
| Waktu inferensi validasi | 0,5 ms praproses, 11,9 ms inferensi, 1,6 ms pascaproses per gambar |
| Pengukuran kecepatan | 17,21 ms/gambar, median 17,31 ms, maksimum 29,01 ms, sekitar 58,1 FPS |

### Status quality gate

Quality gate memakai ambang 98% untuk `box_p`, `box_map50`, `mask_p`, dan `mask_map50` pada setiap kelas.

| Kelas | Box P | Box mAP50 | Mask P | Mask mAP50 | Status |
|---|---:|---:|---:|---:|---|
| pohon | 0,9846 | 0,9950 | 0,9852 | 0,9950 | Lulus seluruh metrik wajib |
| mobil | 0,8977 | 0,8456 | 0,9153 | 0,8449 | Belum lulus |
| motor | 0,9129 | 0,8882 | 0,9482 | 0,9182 | Belum lulus |
| orang | 0,8583 | 0,8081 | 0,8274 | 0,7628 | Belum lulus |
| lubang | 0,7718 | 0,7336 | 0,7777 | 0,7169 | Belum lulus |

Hasil quality gate adalah `passed: false` dan `deployed: false`. Pipeline tidak mengganti bobot aktif secara otomatis. Checkpoint terbaik tetap disalin manual ke `models/best.pt` untuk kebutuhan serving.

Laporan lengkap tersedia di:

```text
data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.txt
data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.json
data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/val_class_metrics.csv
data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/
```

## Alur kerja fuzzy logic

Fuzzy logic mengubah hasil segmentasi menjadi skor urgensi 0 sampai 100. Implementasi berada di `fuzzysugeno.py`.

### Tahapan

1. Gambar diterima server, lalu dijalankan melalui YOLO26n-seg pada `imgsz=512`.
2. Setiap objek menghasilkan kelas, confidence, bounding box, dan mask.
3. Objek dengan confidence di bawah `VEST_CONF` dibuang. Ambang kandidat lubang adalah 0,35.
4. Objek dengan confidence di bawah `VEST_CONF_RAGU` tetap dikirim di JSON, tetapi ditandai `ragu: true`.
5. Objek `ragu` ditampilkan di tampilan kamera sebagai kotak kandidat, tetapi tidak dipakai untuk ringkasan, peringatan, memori, atau penyimpanan Supabase.
6. Jarak objek diestimasi dari geometri kamera (tinggi 1,00 m dan kemiringan 10 derajat). Jika ada sensor ultrasonik di depan, jarak kamera dan ultrasonik difusikan dengan nilai minimum hingga 3,00 m.
7. Arah objek ditentukan dari posisi tengah bounding box: kiri, depan, atau kanan.
8. Tingkat bahaya kelas ditetapkan: lubang, motor, dan mobil bernilai 10; orang dan pohon bernilai 6.
9. Tingkat keterhalangan jalur dihitung dari irisan mask objek dengan koridor jalan di depan pengguna.
10. Tiga variabel fuzzy dihitung: jarak, bahaya, dan jalur.
11. Sebanyak 26 aturan Sugeno dievaluasi dengan operator minimum.
12. Jika objek yakin berada di depan pada jarak kurang dari 0,50 m, buzzer browser berbunyi terus sampai objek tidak lagi terdeteksi dekat. Buzzer berhenti otomatis jika hasil deteksi tidak diperbarui selama 1,5 detik.
12. Defuzzifikasi memakai rata-rata berbobot nilai singleton untuk menghasilkan skor urgensi.
13. Skor urgensi dipetakan menjadi level AMAN, INFO, WASPADA, atau BAHAYA.
14. Level menentukan pola getar dan rencana suara.
15. `PelacakGerak` menaksir status bergerak, diam, atau netral untuk mobil, motor, dan orang.
16. `IngatanHalangan` menyimpan objek lubang yang sempat terlihat agar tetap diperingatkan beberapa saat setelah keluar dari frame.

### Variabel dan fungsi keanggotaan

| Variabel | Himpunan | Rentang trapesium |
|---|---|---|
| jarak | sangat_dekat | -1, 0, 0,90, 1,50 |
| jarak | dekat | 0,90, 1,50, 2,20, 3,00 |
| jarak | sedang | 2,20, 3,00, 3,50, 4,50 |
| jarak | jauh | 3,50, 4,50, 99, 100 |
| bahaya | rendah | -1, 0, 3, 5 |
| bahaya | sedang | 3, 5, 6, 8 |
| bahaya | tinggi | 6, 8, 10, 11 |
| jalur | luar | -1, 0, 0,10, 0,35 |
| jalur | sebagian | 0,10, 0,35, 0,50, 0,75 |
| jalur | penuh | 0,50, 0,75, 1, 2 |

### Aturan fuzzy

| Kelompok aturan | Jumlah aturan | Contoh keluaran singleton |
|---|---:|---|
| Sangat dekat dan bahaya tinggi | 2 | 100 |
| Dekat dan bahaya tinggi | 2 | 90 dan 75 |
| Sedang dan bahaya tinggi | 2 | 60 dan 45 |
| Jauh dan bahaya tinggi | 1 | 30 |
| Sangat dekat dan bahaya sedang | 2 | 85 dan 65 |
| Dekat dan bahaya sedang | 2 | 65 dan 50 |
| Sedang dan bahaya sedang | 2 | 40 dan 30 |
| Jauh dan bahaya sedang | 1 | 15 |
| Sangat dekat dan bahaya rendah | 2 | 60 dan 40 |
| Dekat dan bahaya rendah | 2 | 40 dan 25 |
| Sedang dan bahaya rendah | 1 | 15 |
| Jauh dan bahaya rendah | 1 | 5 |
| Objek sangat dekat di luar jalur | 3 | 40, 25, dan 10 |
| Objek dekat, sedang, atau jauh di luar jalur | 3 | 5 |

### Pemetaan level dan getar

| Skor urgensi | Level | Getar |
|---:|---|---|
| 75 sampai 100 | BAHAYA | PWM 255, interval 150 ms, getar cepat terus-menerus |
| 50 sampai kurang dari 75 | WASPADA | PWM 120, interval 600 ms, getar berdenyut pelan |
| 25 sampai kurang dari 50 | INFO | PWM 80, interval 1.000 ms, denyut tunggal lemah |
| 0 sampai kurang dari 25 | AMAN | PWM 0, getar mati |

### Pelacak gerak dan memori

| Modul | Perilaku |
|---|---|
| `PelacakGerak` | Membandingkan perubahan jarak antar-frame untuk mobil, motor, dan orang |
| Ambang bergerak | Kecepatan mendekat minimal 1,8 m/detik |
| Ambang diam | Perubahan jarak maksimal 0,4 m/detik |
| Sampel minimal | 3 sampel berturut-turut |
| Umur sampel | 1,5 detik |
| `IngatanHalangan` | Menyimpan lubang yang sempat terlihat, umur maksimal 2,5 detik |
| Kecepatan jalan acuan | 1,2 m/detik |

### Perencana suara

Perencana suara memilih objek dengan level dan urgensi tertinggi. Kalimat dirakit dari klip berikut:

1. Klip awal `awal_waspada` atau `awal_bahaya` bila level minimal WASPADA.
2. Klip `benda_{kelas}_{arah}_{gerak}`.
3. Klip jarak `jarak_{bucket}` dengan bucket 5 sampai 50 meter.
4. Klip solusi `solusi_{aksi}`, misalnya lurus, pelan, pelan kiri, berhenti, atau berhenti kanan.

Jika klip gerak belum tersedia, sistem memakai fallback `benda_{kelas}_{arah}_netral`. Jika tidak ada deteksi, sistem memakai klip `jalur_aman`.

## Alur API, web, dan Supabase

### Alur dari kamera sampai dashboard

1. Browser membuka `/` atau `/app`. FastAPI menyajikan build React dari `web/react/dist/`.
2. Jika `VEST_API_KEY` aktif, server memasang cookie sesi HttpOnly bernama `vestcare_sesi`.
3. Komponen `CameraCapture` membuka kamera dan mengirim frame ke `POST /deteksi` sekitar satu kali per detik. Pratinjau mempertahankan seluruh bidang gambar (tanpa crop/zoom), dan model membatasi deteksi ke lima kelas target: pohon, mobil, motor, orang, dan lubang.
4. Firmware ESP32-S3 N16R8 dengan OV3660 mengirim JPEG untuk inferensi ke `POST /deteksi` dan frame preview ke `POST /api/esp32/frame`, menggunakan header `X-API-Key`. Dashboard mengambil snapshot terbaru melalui `GET /api/esp32/frame/latest` dan hasil/bounding box melalui `GET /api/deteksi/latest`; frame tidak ditumpuk dalam antrean.
5. Setiap request divalidasi dengan `X-API-Key` atau cookie sesi. Ukuran gambar dibatasi 10 MB dan resolusi 40 megapiksel.
6. Server menjalankan YOLO26n-seg, fuzzy Sugeno, pelacak gerak, dan perencana suara.
7. Respons berisi daftar deteksi, level tertinggi, urgensi, status ragu, dan rencana suara.
   Objek di luar lima kelas utama, seperti helm, dapat dimasukkan sebagai data penunjang di `data/datasets/penunjang/dataset_helm.zip`; saat training, labelnya dipetakan ke kelas internal dan tidak ditampilkan sebagai kelas utama. Model perlu dilatih ulang dengan contoh helm agar dapat menahan prediksi helm yang keliru sebagai mobil.
8. Server menulis riwayat ke `data/runtime/riwayat.jsonl`.
9. Server menyinkronkan deteksi ke Supabase melalui REST API dengan service-role key.
10. Saat startup, server memakai perangkat yang sudah tercatat di tabel `devices` (atau `VEST_SUPABASE_DEVICE_ID` bila diisi); perangkat baru hanya dibuat jika belum ada.
11. Untuk setiap frame, server mengambil baris terakhir per objek, memperbarui baris yang sudah ada dengan `PATCH`, menambah baris baru dengan `POST`, dan menghapus duplikat dengan `DELETE`.
12. Semua objek dalam satu frame memakai `created_at` yang sama sehingga dapat dikelompokkan sebagai satu batch.
13. Frame dengan signature objek, level, dan arah yang sama dilewati selama 10 detik untuk mencegah duplikasi.
14. Dashboard membaca `devices`, `detections`, dan `gps_log` melalui `GET /dashboard/data`. Server memakai service-role key dan cookie sesi HttpOnly, sehingga kunci rahasia tidak pernah masuk ke browser.
15. Jika Supabase belum lengkap atau sedang offline, dashboard memakai fallback `GET /riwayat`.
16. Dashboard memuat ulang perangkat dan riwayat setiap 10 detik. Telemetri didorong lewat SSE dan tetap dipolling setiap 500 ms agar tunnel yang menahan SSE tidak membuat status macet. Status rompi online jika telemetri atau frame kamera baru diterima dalam 15 detik; dashboard memeriksa snapshot kamera setiap 100 ms dan menerima hasil deteksi ESP32 lewat SSE.

Audio bukan diputar saat dashboard dimulai. Saat kamera ESP32 aktif, peringatan dari `POST /deteksi` diputar melalui output audio browser dan tidak diulang pada setiap frame. TWS dapat dipakai bila dipasangkan ke ponsel/komputer yang membuka dashboard dan dipilih sebagai output audio. ESP32-S3 tidak mengirim audio langsung ke TWS.

### Tabel alur data

| Tahap | Komponen | Masukan | Keluaran | Media |
|---|---|---|---|---|
| Akuisisi | `CameraCapture.jsx` | Frame kamera browser | Blob gambar dan `jarak_m` | HTTP multipart ke `/deteksi` |
| Akuisisi | ESP32-S3 N16R8 + OV3660 | Frame kamera | JPEG dan `X-API-Key` | HTTP multipart ke `/deteksi` |
| Inferensi | `InferensiVest` | Gambar RGB | Box, mask, confidence | Memori server |
| Keputusan | `fuzzysugeno.py` | Box, mask, jarak | Deteksi, urgensi, level, getar | Memori server |
| Suara | `PerencanaSuara` | Daftar deteksi | Rencana segmen dan teks | Memori server |
| Riwayat lokal | `_simpan_riwayat` | Hasil deteksi | Baris JSONL | `data/runtime/riwayat.jsonl` |
| Sinkronisasi | `_simpan_deteksi_supabase` | Hasil deteksi | Baris `detections` | Supabase REST |
| Baca web | `useVestData.js` | `GET /dashboard/data`, SSE `/api/telemetri/stream`, `GET /riwayat` | State dashboard realtime | HTTP same-origin + cookie sesi |
| Fallback web | FastAPI | Perangkat atau Supabase kosong | Data dashboard | `/riwayat` dan polling `/api/telemetri` |

### Tabel Supabase yang dipakai

| Tabel | Kolom yang dibaca atau ditulis | Fungsi |
|---|---|---|
| `devices` | `id`, `name`, `student_name`, `school`, `battery`, `online`, `last_seen` | Identitas dan status perangkat |
| `detections` | `id`, `device_id`, `object`, `distance_m`, `confidence`, `urgency`, `lat`, `lng`, `urgency_score`, `created_at` | Riwayat objek terdeteksi |
| `gps_log` | `id`, `device_id`, `lat`, `lng`, `accuracy`, `created_at` | Posisi terakhir perangkat |

Catatan skema:

- Server menyimpan posisi GPS valid dari telemetri Wemos ke `gps_log`; dashboard mengutamakan posisi live dan tidak menampilkan posisi tersimpan ketika perangkat online tetapi GPS belum mendapat fix.
- Peta dashboard memakai koordinat GPS live dari ESP32-S3 saja; posisi lama dari riwayat/Supabase tidak dipakai sebagai pengganti fix GPS. Fix dianggap aktif selama data lokasi diperbarui dalam 5 detik terakhir. Jika koordinat belum tersedia, dashboard meminta pengguna membawa rompi ke area terbuka karena sinyal GPS sulit diterima di dalam ruangan.
- Latitude dan longitude dikirim sebagai derajat desimal (`lat`, `lng`), sesuai urutan yang dipakai peta Google Maps.
- Peta dashboard memakai Google Maps. Bila `GOOGLE_MAPS_API_KEY` diisi, peta memakai Google Maps JavaScript API sehingga marker rompi, jejak perjalanan, dan marker objek bergerak realtime. Bila kunci belum diisi, dashboard otomatis memakai Google Maps mode embed dan tetap menampilkan koordinat, jarak, satelit, HDOP, kecepatan, dan waktu GPS dari Wemos.
- Marker objek pada peta adalah perkiraan dari arah (`kiri`/`depan`/`kanan`) dan jarak deteksi terhadap posisi rompi. Bila baris deteksi sudah memiliki `lat`/`lng`, koordinat itu yang dipakai.
- Jejak perjalanan disimpan di memori server (maksimal 300 titik) dan ikut dikirim pada setiap event SSE maupun `/dashboard/data`.
- Kolom `urgency` memakai nilai `Tinggi`, `Sedang`, atau `Rendah`. Kolom `urgency_score` memakai skor fuzzy 0 sampai 100.
- Deteksi `umum` dari sensor ultrasonik tetap tampil di dashboard dan riwayat lokal, tetapi tidak ditulis ke tabel `detections` karena constraint tabel hanya menerima lima kelas model.
- Repo tidak menyertakan migrasi SQL. Pastikan tabel dan kolom di atas sudah ada di proyek Supabase.
- Aktifkan Row Level Security. Dashboard tidak lagi membaca tabel langsung dari browser; data diambil melalui `/dashboard/data` memakai service-role key di server.
- Service-role key hanya boleh berada di `.env` root dan tidak boleh masuk ke bundle frontend.

### Konfigurasi environment

Backend, dibaca dari `.env` root:

| Kunci | Fungsi |
|---|---|
| `VEST_API_KEY` | Kunci API minimal 32 karakter untuk `X-API-Key` dan penandatanganan cookie sesi |
| `VEST_MODEL_PATH` | Path bobot model, default `models/best.pt` |
| `VEST_IMGSZ` | Ukuran inferensi, default 512 |
| `VEST_CONF` | Ambang confidence deteksi, default 0,35 |
| `VEST_CONF_RAGU` | Ambang penanda ragu, default 0,50 |
| `VEST_SUARA_FOLDER` | Folder pustaka suara, default `data/runtime/audio/cache_ardi` |
| `VEST_RIWAYAT_PATH` | Path riwayat JSONL, default `data/runtime/riwayat.jsonl` |
| `VEST_RIWAYAT_MAX_BYTES` | Batas ukuran riwayat sebelum diputar, default 5 MB (minimum 256 KB) |
| `VEST_RIWAYAT_KEEP_ENTRIES` | Jumlah entri terbaru yang disimpan saat rotasi, default 4.000 |
| `VEST_CORS_ORIGINS` | Daftar origin frontend terpisah dipisah koma; default `*` untuk same-origin |
| `VEST_PUBLIC_URL` | URL HTTPS publik eksplisit untuk balasan discovery ESP32; jika kosong, API memakai `RAILWAY_PUBLIC_DOMAIN` di Railway |
| `VEST_HOST` | Host server, default `0.0.0.0` |
| `VEST_PORT` | Port server, default `8080` |
| `PORT` | Port yang disediakan platform deploy seperti Railway; mengesampingkan `VEST_PORT` |
| `VEST_ENABLE_LAN_DISCOVERY` | Aktifkan listener UDP LAN; default aktif lokal dan dimatikan dalam image Railway |
| `GOOGLE_MAPS_API_KEY` | Kunci Google Maps JavaScript API untuk marker, jejak, dan objek realtime; bila kosong dashboard memakai mode embed |
| `VEST_MAP_DEFAULT_LAT` | Latitude pusat peta saat GPS belum fix, default `-8.1689` |
| `VEST_MAP_DEFAULT_LNG` | Longitude pusat peta saat GPS belum fix, default `113.7020` |
| `VEST_MAP_ZOOM` | Zoom awal peta Google Maps, default `17` |
| `SUPABASE_URL` | URL proyek Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key untuk penulisan backend |
| `VEST_SUPABASE_DEVICE_ID` | UUID perangkat nyata di tabel `devices`; bila kosong, server memakai perangkat pertama yang sudah ada |

Frontend, dibaca dari `web/react/.env.local`:

| Kunci | Fungsi |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` atau `VITE_SUPABASE_URL` | URL proyek Supabase (opsional, untuk realtime di masa depan) |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` atau `VITE_SUPABASE_ANON_KEY` | Publishable atau anon key (opsional, bukan untuk menulis data) |
| `VITE_GOOGLE_MAPS_API_KEY` | Alternatif kunci Google Maps saat build; kunci runtime `GOOGLE_MAPS_API_KEY` di `.env` server lebih dulu dipakai agar tidak perlu rebuild |

### Endpoint API

| Method | Path | Keterangan |
|---|---|---|
| `GET` | `/info` | Info versi, model, `imgsz`, `conf`, `conf_ragu`, status engine |
| `GET` | `/status` | Status server, engine, suara, dan koneksi Supabase |
| `GET` | `/sesi` | Perbarui cookie sesi browser tanpa memuat ulang dashboard |
| `GET` | `/healthz` | Liveness probe proses API |
| `GET` | `/readyz` | Readiness probe engine, API key, dan dashboard |
| `GET` | `/` | Dashboard React VestCare |
| `GET` | `/app` | Alias dashboard React VestCare |
| `GET` | `/docs` | Dokumentasi OpenAPI |
| `GET` | `/dashboard/data` | Data perangkat, deteksi, GPS, dan jejak dari Supabase/server |
| `GET` | `/config` | Konfigurasi publik dashboard: titik pusat peta, zoom, dan kunci Google Maps |
| `POST` | `/api/telemetri` | Telemetri jarak dan GPS dari Wemos; endpoint publik tanpa API key |
| `GET` | `/api/telemetri` | Telemetri terakhir, status online, dan jejak GPS |
| `GET` | `/api/telemetri/stream` | Server-Sent Events telemetri realtime untuk peta Google Maps |
| `GET` | `/api/deteksi/latest` | Hasil deteksi kamera terbaru dan status kesegarannya |
| `GET` | `/api/deteksi/stream` | Server-Sent Events hasil deteksi terbaru |
| `POST` | `/api/esp32/frame` | Menerima frame JPEG terbaru dari kamera ESP32 |
| `GET` | `/api/esp32/frame/latest` | Snapshot JPEG terbaru dengan cache ETag |
| `GET` | `/api/esp32/status` | Ketersediaan frame ESP32 untuk pemilihan sumber kamera dashboard |
| `GET` | `/api/esp32/stream` | MJPEG stream frame ESP32 untuk klien non-browser |
| `POST` | `/deteksi` | Upload gambar multipart dan `jarak_m` opsional |
| `POST` | `/deteksi/suara` | Sama seperti `/deteksi`, dengan rencana suara |
| `POST` | `/peringatan` | JSON `{ "skor_risiko": 0..1, "jarak_m": ... }` |
| `GET` | `/riwayat?limit=20` | Riwayat deteksi lokal terakhir |
| `GET` | `/suara/pratinjau` | Contoh rencana suara |
| `GET` | `/suara/{nama_berkas}` | Berkas klip suara yang diizinkan |

Jika `VEST_API_KEY` aktif, sertakan header `X-API-Key` pada setiap request yang diproteksi. Browser memakai cookie sesi HttpOnly yang dipasang saat halaman utama dibuka.

### Pengujian dengan Postman

Gunakan `http://127.0.0.1:8080` sebagai base URL lokal. Untuk menguji melalui
Cloudflare Quick Tunnel, gunakan URL HTTPS yang dicetak oleh `server.py`.

1. `GET /status` memeriksa kesiapan server dan model.
2. `POST /deteksi` memakai **Body → form-data**: `gambar` bertipe **File** dan
   `jarak_m` bertipe **Text** (opsional, dalam meter). Jangan mengatur
   `Content-Type` secara manual; Postman akan menambahkan multipart boundary.
3. Jika `VEST_API_KEY` diaktifkan, tambahkan header `X-API-Key` dengan nilai dari
   `.env` untuk request yang diproteksi.
4. `GET /riwayat?limit=20` menampilkan hasil terbaru dalam bentuk JSON
   `{"total": ..., "ditampilkan": ..., "data": [...]}`.

Respons `POST /deteksi` berisi `id`, `waktu`, `sumber`, ringkasan hasil inferensi,
daftar `deteksi`, dan status sinkronisasi Supabase. Jika upload gagal, periksa
status HTTP dan field `detail` pada respons validasi FastAPI.

## Struktur proyek

| Path | Fungsi |
|---|---|
| `server.py` | Entry point untuk menjalankan API, dashboard, Cloudflare Quick Tunnel, dan UDP discovery ESP32 |
| `server_rest_api.py` | Aplikasi FastAPI, endpoint, engine YOLO, fuzzy, suara, riwayat, dan Supabase |
| `fuzzysugeno.py` | Fuzzy Sugeno, `analisis_hasil`, `PelacakGerak`, `IngatanHalangan`, dan penanda ragu |
| `start_train.py` | Entry point pipeline training |
| `train_semua.py` | Pipeline training 5 kelas, quality gate, evaluasi akhir, dan pembersihan run lama |
| `start_eval.py` | Evaluasi model per kelas dan per varian dataset |
| `dataset_gabungan.yaml` | Konfigurasi dataset gabungan 5 kelas |
| `models/best.pt` | Bobot aktif yang dipakai server |
| `web/react/` | Dashboard React, hasil build disajikan dari `web/react/dist/` |
| `web/react/src/useVestData.js` | Pembacaan `/dashboard/data`, SSE telemetri, dan fallback `/riwayat` |
| `web/react/src/components/CameraCapture.jsx` | Kamera, pengiriman frame, kotak objek, dan pemutaran suara |
| `web/react/src/components/GpsMap.jsx` | Peta Google Maps realtime, marker objek, jejak GPS, dan panel telemetri Wemos |
| `library/suara-natural-ai/` | Pustaka klip suara, perakit kalimat, dan contoh integrasi |
| `data/results/runs/segment/runs/` | Artefak training, laporan, dan evaluasi |
| `data/datasets/` | Dataset sumber, utama, dan penunjang |
| `data/results/` | Hasil training, evaluasi, split, dan log |
| `data/runtime/` | Riwayat server, URL publik, dan cache audio |
| `hardware/arduino/` | Firmware Wemos |
| `data/runtime/riwayat.jsonl` | Riwayat deteksi lokal, tidak di-commit |

## Cara menjalankan

### Prasyarat

- Python 3.10 atau lebih baru dan virtual environment `.venv`.
- Dependensi utama: `ultralytics`, `fastapi`, `uvicorn`, `pillow`, `numpy`, `python-multipart`.
- Untuk suara: `pip install -r library/suara-natural-ai/requirements_pemutar.txt`, membutuhkan `pygame-ce`.
- Untuk tunnel publik: `cloudflared` tersedia di `PATH`, terpasang pada lokasi
  standar Windows `C:\Program Files (x86)\cloudflared\cloudflared.exe`, atau
  ditetapkan melalui `CLOUDFLARED_EXECUTABLE`.
- Node.js dan npm untuk membangun dashboard React.

### Training

```powershell
python start_train.py
```

Pipeline akan:

1. Menyiapkan split train dan validasi dari dataset gabungan.
2. Melatih `yolo26n-seg.pt` selama 100 epoch pada `imgsz=512`.
3. Menjalankan quality gate per kelas.
4. Melakukan evaluasi akhir dan menulis laporan ke folder run.
5. Menghapus run lama serta checkpoint duplikat setelah training selesai.

### Evaluasi

```powershell
python start_eval.py --dataset dataset_gabungan.yaml --split val
```

Opsi lain: `--model`, `--out`, `--imgsz`, `--batch`, `--conf`, `--contoh`, `--n-kecepatan`, dan `--device`.

### Server API dan dashboard

Isi `.env` terlebih dahulu. Contoh kunci yang dipakai:

```text
VEST_API_KEY=<kunci acak minimal 32 karakter>
VEST_MODEL_PATH=models/best.pt
VEST_IMGSZ=512
VEST_CONF=0.35
VEST_CONF_RAGU=0.50
VEST_HOST=0.0.0.0
VEST_PORT=8080
GOOGLE_MAPS_API_KEY=<kunci-google-maps-javascript-api>
VEST_MAP_DEFAULT_LAT=-8.1689
VEST_MAP_DEFAULT_LNG=113.7020
VEST_MAP_ZOOM=17
SUPABASE_URL=https://<proyek>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
VEST_SUPABASE_DEVICE_ID=<uuid-perangkat-di-tabel-devices>
```

Jalankan:

```powershell
cd web/react
npm install
npm run build
cd ..\..
python server.py
```

Dengan `VEST_HOST=0.0.0.0`, server dapat menerima koneksi lokal dan memulai Cloudflare Quick Tunnel. URL `trycloudflare.com` langsung menampilkan dashboard React, sedangkan `/app` tetap menjadi alias. Dokumentasi interaktif tersedia di `/docs`. URL publik terakhir juga disimpan di `data/runtime/public_url.txt`. ESP32-S3 memakai domain Railway sebagai default; untuk server lokal, set `VEST_USE_LAN_DISCOVERY=1` agar memakai discovery UDP port `4211` pada LAN yang sama. Build dashboard perlu diperbarui dengan `npm run build` setiap kali source React berubah.

Request GET dan POST dicatat di terminal dengan metode, path, status HTTP, dan waktu proses, misalnya `[HTTP] GET /status -> 200 (3.2 ms)`. Query string, header, dan isi request tidak dicatat.

### Deploy Railway

Dockerfile repository membangun dashboard React dan API FastAPI dalam satu
service. `railway.json` menetapkan builder Dockerfile, health check `/readyz`,
restart on failure, dan satu replica. `.railwayignore` mencegah virtualenv,
dataset, dan hasil training ikut diunggah, tetapi tetap menyertakan
`models/best.pt` dan pustaka audio. Peringatan deprecation untuk `railway.json`
tidak menggagalkan deploy; migrasikan setelah service dibuat melalui perintah
Railway CLI. Railway mempertahankan domain service saat restart/redeploy biasa;
domain berubah hanya jika domain/service dihapus atau diganti. Sketch ESP32-S3
memakai domain ini sebagai default; `VEST_SERVER_URL` di
`hardware/arduino/esp32_s3/secrets.h` hanya perlu diisi untuk override.
Alamat API tidak dapat ditemukan dari API key saja. Railway menyediakan
`RAILWAY_PUBLIC_DOMAIN` setelah domain publik dibuat; API memakai nilai itu
otomatis untuk balasan discovery jika `VEST_PUBLIC_URL` tidak diatur.

1. Pastikan project dan environment terhubung (`railway link`), lalu jalankan
   `railway up` untuk mengunggah dan deploy kode lokal. File `.railwayignore`
   mengecualikan virtualenv dan data training yang tidak diperlukan.
2. Pada service, buka **Settings → Networking → Public Networking** dan pilih
   **Generate Domain** bila belum ada. Atur `VEST_API_KEY` sebagai Railway
   Variable; nilainya harus sama dengan key di `secrets.h` ESP32.
3. Set `VEST_MODEL_PATH=models/best.pt`. Atur `SUPABASE_URL` dan
   `SUPABASE_SERVICE_ROLE_KEY` hanya jika Supabase dipakai.
4. Untuk mempertahankan riwayat lokal, tambahkan Railway Volume pada `/data` dan
   set `VEST_RIWAYAT_PATH=/data/riwayat.jsonl`. Tanpa volume, riwayat lokal
   hilang saat container diganti; data live kamera/telemetri disimpan di memori.
   Riwayat aktif dibatasi otomatis ke sekitar 5 MB (4.000 entri terbaru) dan
   file sebelumnya disalin ke `riwayat.jsonl.1`.
   Pustaka suara Ardi pada `data/runtime/audio/cache_ardi` disertakan dalam
   image melalui `.dockerignore`; pastikan folder itu ada saat build (atau sudah
   di-commit). Jika memakai volume tersendiri, set
   `VEST_SUARA_FOLDER=/data/audio`; tanpa klip, inferensi dan kamera tetap jalan
   tetapi audio dashboard dinonaktifkan dengan pesan yang jelas.
5. Setelah service tersedia, jalankan `railway domain` untuk membuat domain
   publik. Salin URL yang tampil (mis.
   `https://nama-service.up.railway.app`) ke `VEST_SERVER_URL` bila ingin
   override default, lalu build dan flash firmware. Domain service
   tidak berubah saat redeploy biasa; jika domain dibuat ulang atau service
   diganti, perbarui nilai firmware. Dashboard dan API menggunakan domain yang
   sama, sehingga browser memakai cookie sesi same-origin.

Di Railway Service Settings, atur health check path ke `/readyz`; service hanya
siap ketika model, API key, dan hasil build dashboard tersedia. Pertahankan satu
replica karena frame kamera dan telemetri live berada di memori proses. Gunakan
resource CPU/RAM yang cukup untuk PyTorch CPU; latensi inferensi dan kestabilan
jaringan menentukan kelancaran realtime, jadi tidak dapat dijamin nol gangguan.
Untuk CPU kecil, turunkan `VEST_IMGSZ` (misalnya 416) agar hasil deteksi lebih
cepat muncul; naikkan lagi bila akurasi lebih penting.
Untuk menjalankan lokal, tetap gunakan `python server.py`; perintah itu yang
menyalakan Cloudflare Quick Tunnel dan discovery UDP LAN.

Peta dashboard memakai Google Maps. Untuk Railway, tambahkan `GOOGLE_MAPS_API_KEY` pada **Service → Variables** dengan key Google Maps JavaScript API yang dibatasi ke domain dashboard dan API Maps JavaScript. Restart atau deploy ulang service agar konfigurasi server terbaca melalui `/config`; build ulang frontend tidak diperlukan. Untuk server lokal, pastikan variabel tersedia pada environment proses server. Bila key kosong atau ditolak, dashboard otomatis memakai Google Maps mode embed agar lokasi perangkat tetap terlihat.

### Menghubungkan Wemos ke server dan dashboard

1. Sambungkan komputer/server dan Wemos ke jaringan Wi-Fi yang sama. Jalankan server dengan `VEST_HOST=0.0.0.0` dan port yang sesuai.
2. Saat portal konfigurasi `Wemos_Setup` muncul, isi Wi-Fi saja. Wemos memakai URL tetap di `hardware/arduino/wemos/wemos.ino`; jika URL Quick Tunnel berubah, perbarui `SERVER_URL` ke URL dari `data/runtime/public_url.txt` dan flash ulang firmware. ESP32-S3 memakai domain Railway yang ditetapkan pada sketch/secrets header (bukan melalui portal); discovery UDP hanya untuk mode LAN lokal.
3. Endpoint `POST /api/telemetri` menerima kiriman publik tanpa `VEST_API_KEY` agar Wemos tidak memerlukan konfigurasi key. Jangan gunakan endpoint ini untuk data sensitif: siapa pun yang mengetahui URL server dapat mengirim telemetri palsu. Endpoint API lain tetap mengikuti autentikasi server.
4. Wemos mengirim jarak ultrasonik dan GPS melalui HTTPS ke `/api/telemetri` setiap 5 detik. Sertifikat TLS diverifikasi dan waktu sertifikat disinkronkan lewat NTP; jangan matikan verifikasi TLS. Dashboard pada URL Cloudflare yang sama akan menampilkan status perangkat dan lokasi. Periksa Serial Monitor 115200 baud untuk status HTTP.

Wemos hanya menyimpan kredensial Wi-Fi melalui WiFiManager. Firmware memverifikasi HTTPS menggunakan trust anchor ISRG Root X2. Jika koneksi gagal, periksa detail `[TLS] BearSSL` dan waktu perangkat di Serial Monitor; jangan menonaktifkan verifikasi sertifikat.

### Deteksi dari kamera tanpa dashboard

```powershell
python library/suara-natural-ai/jalankan_fuzzy.py --sumber 0
```

Gunakan `--sumber` untuk indeks kamera atau path video. Contoh integrasi tanpa kamera tersedia di `library/suara-natural-ai/contoh_integrasi.py`.

## Artefak dan log

| Artefak | Path |
|---|---|
| Log training root | `data/results/logs/training_semua_20261107_154452_851599.log` |
| Log run | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/training.log` |
| Log mentah | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/raw/training.log` |
| Laporan training | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.txt` |
| Laporan JSON | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.json` |
| Metrik per kelas | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/val_class_metrics.csv` |
| Evaluasi akhir | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/` |
| Log evaluasi | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/evaluation_20261108_000253.log` |
| Ringkasan akurasi | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/laporan_akurasi.txt` |
| Kecepatan | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/kecepatan.json` |
| Bobot terbaik | `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/weights/best.pt` |

### Ukuran artefak mentah

| File | Ukuran byte | Ukuran perkiraan |
|---|---:|---:|
| `data/results/logs/training_semua_20261107_154452_851599.log` | 12.800.220 | 12,2 MiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/training.log` | 12.800.220 | 12,2 MiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/raw/training.log` | 12.800.220 | 12,2 MiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/results.csv` | 18.044 | 17,6 KiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/raw/results.csv` | 18.044 | 17,6 KiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.json` | 11.019 | 10,8 KiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.txt` | 1.911 | 1,9 KiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/val_class_metrics.csv` | 906 | 0,9 KiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/evaluation_20261108_000253.log` | 33.212 | 32,4 KiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/ringkasan_test.json` | 7.282 | 7,1 KiB |
| `data/results/runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/kecepatan.json` | 191 | 0,2 KiB |

### Contoh baris log mentah

Baris pertama dan terakhir `raw/results.csv`:

```csv
epoch,time,train/box_loss,train/seg_loss,train/cls_loss,train/l1_loss,train/sem_loss,metrics/precision(B),metrics/recall(B),metrics/mAP50(B),metrics/mAP50-95(B),metrics/precision(M),metrics/recall(M),metrics/mAP50(M),metrics/mAP50-95(M),val/box_loss,val/seg_loss,val/cls_loss,val/l1_loss,val/sem_loss,lr/pg0,lr/pg1,lr/pg2
1,239.938,1.76673,2.97699,2.41388,0.01774,2.57882,0.62727,0.6203,0.63025,0.38464,0.59989,0.61753,0.60636,0.36824,1.52163,2.33796,1.66756,0.02639,0,0.000332854,0.000332854,0.0670475
100,29825.4,0.81905,1.19443,0.48865,0.00821,0.16891,0.88227,0.77763,0.8493,0.64305,0.90166,0.76424,0.84035,0.61078,1.08035,1.63396,0.7739,0.01567,0,1.99e-05,1.99e-05,1.99e-05
```

Cuplikan log konsol saat training:

```text
[INFO] Kelas: pohon, mobil, motor, orang, lubang | train: 2778 gambar | val: 312 gambar
[INFO] Resolusi       : 512px | batch: 4 | epoch maks: 100
[INFO] GPU            : NVIDIA GeForce GTX 1650 with Max-Q Design
Starting training for 100 epochs...
100 epochs completed in 8.285 hours.
```

## Catatan

- `dataset_gabungan.yaml` memakai path absolut `C:/dataset vestcare (rompi-cerdas)`. Sesuaikan path bila repo dipindahkan ke mesin lain.
- File `.env` tidak di-commit. Jangan menuliskan kunci API asli ke README atau file yang di-commit.
- Quality gate 98% belum terpenuhi. Gunakan hasil ini sebagai baseline untuk perbaikan dataset, anotasi, dan training berikutnya.
- Repo ini tidak memakai Git LFS. Bobot dan artefak run disimpan langsung agar hasil training dapat direproduksi dan diaudit.
- Tabel Supabase harus dibuat terlebih dahulu sesuai kolom pada bagian skema. Tanpa tabel yang sesuai, server tetap berjalan, tetapi sinkronisasi akan gagal dan statusnya terlihat pada `/status` serta dialog kamera.
