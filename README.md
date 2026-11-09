<p align="center">
  <img src="assets/vestcare-title.svg" alt="VestCare - Rompi Cerdas (Stage 2)" width="900">
</p>

Sistem peringatan rintangan untuk rompi cerdas berbasis segmentasi YOLO26n, logika fuzzy Sugeno, dan suara natural Bahasa Indonesia. Model mendeteksi lima kelas, yaitu pohon, mobil, motor, orang, dan lubang. Hasil deteksi dipetakan menjadi arah, jarak, tingkat risiko, instruksi suara, serta riwayat perangkat pada Supabase.

## Ringkasan sistem

| Komponen | Keterangan |
|---|---|
| Model visi | YOLO26n-seg, 5 kelas, keluaran bounding box dan mask |
| Logika keputusan | Fuzzy Sugeno orde-nol dengan 26 aturan |
| Keluaran peringatan | Level AMAN, INFO, WASPADA, BAHAYA; getar; instruksi suara |
| Suara | Klip Bahasa Indonesia dari `suara-natural-ai/cache_ardi` |
| API | FastAPI, autentikasi API key atau cookie sesi HttpOnly |
| Web | Dashboard React + Vite yang disajikan langsung oleh FastAPI |
| Penyimpanan | Riwayat lokal JSONL dan sinkronisasi ke Supabase |
| Perangkat | Satu perangkat virtual server dengan UUID tetap |

## Hasil training terbaru

Run yang dipublikasikan:

```text
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/
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
| Checkpoint terbaik | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/weights/best.pt` |

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
| Manifest train | `runs/dataset_splits/train.txt` |
| Manifest validasi | `runs/dataset_splits/val.txt` |

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
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.txt
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.json
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/val_class_metrics.csv
runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/
```

## Alur kerja fuzzy logic

Fuzzy logic mengubah hasil segmentasi menjadi skor urgensi 0 sampai 100. Implementasi berada di `fuzzysugeno.py`.

### Tahapan

1. Gambar diterima server, lalu dijalankan melalui YOLO26n-seg pada `imgsz=512`.
2. Setiap objek menghasilkan kelas, confidence, bounding box, dan mask.
3. Objek dengan confidence di bawah `VEST_CONF` dibuang. Ambang khusus lubang adalah 0,80.
4. Objek dengan confidence di bawah `VEST_CONF_RAGU` tetap dikirim di JSON, tetapi ditandai `ragu: true`.
5. Objek `ragu` diabaikan oleh ringkasan, memori, perencana suara, penyimpanan Supabase, dan tampilan UI.
6. Jarak objek diestimasi dari geometri kamera. Jika ada sensor ultrasonik di depan, jarak kamera dan ultrasonik difusikan dengan nilai minimum.
7. Arah objek ditentukan dari posisi tengah bounding box: kiri, depan, atau kanan.
8. Tingkat bahaya kelas ditetapkan: lubang, motor, dan mobil bernilai 10; orang dan pohon bernilai 6.
9. Tingkat keterhalangan jalur dihitung dari irisan mask objek dengan koridor jalan di depan pengguna.
10. Tiga variabel fuzzy dihitung: jarak, bahaya, dan jalur.
11. Sebanyak 26 aturan Sugeno dievaluasi dengan operator minimum.
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

1. Browser membuka `/` atau `/app`. FastAPI menyajikan build React dari `vest-care-react/dist/`.
2. Jika `VEST_API_KEY` aktif, server memasang cookie sesi HttpOnly bernama `vestcare_sesi`.
3. Komponen `CameraCapture` membuka kamera dan mengirim frame ke `POST /deteksi` sekitar satu kali per detik.
4. Setiap request divalidasi dengan `X-API-Key` atau cookie sesi. Ukuran gambar dibatasi 10 MB dan resolusi 40 megapiksel.
5. Server menjalankan YOLO26n-seg, fuzzy Sugeno, pelacak gerak, dan perencana suara.
6. Respons berisi daftar deteksi, level tertinggi, urgensi, status ragu, dan rencana suara.
7. Server menulis riwayat ke `data/riwayat.jsonl`.
8. Server menyinkronkan deteksi ke Supabase melalui REST API dengan service-role key.
9. Saat startup, server membuat atau memperbarui perangkat virtual `VestCare Server` pada tabel `devices`.
10. Untuk setiap frame, server mengambil baris terakhir per objek, memperbarui baris yang sudah ada dengan `PATCH`, menambah baris baru dengan `POST`, dan menghapus duplikat dengan `DELETE`.
11. Semua objek dalam satu frame memakai `created_at` yang sama sehingga dapat dikelompokkan sebagai satu batch.
12. Frame dengan signature objek, level, dan arah yang sama dilewati selama 10 detik untuk mencegah duplikasi.
13. Dashboard membaca `devices`, `detections`, dan `gps_log` memakai `@supabase/supabase-js` dan publishable atau anon key.
14. Jika perangkat belum terlihat atau Supabase belum lengkap, dashboard memakai fallback `GET /status`, `GET /dashboard/data`, dan `GET /riwayat`.
15. Dashboard memuat ulang data setiap 10 detik. Hasil kamera terbaru langsung memperbarui tampilan tanpa menunggu polling.

### Tabel alur data

| Tahap | Komponen | Masukan | Keluaran | Media |
|---|---|---|---|---|
| Akuisisi | `CameraCapture.jsx` | Frame kamera | Blob gambar dan `jarak_m` | HTTP multipart ke `/deteksi` |
| Inferensi | `InferensiVest` | Gambar RGB | Box, mask, confidence | Memori server |
| Keputusan | `fuzzysugeno.py` | Box, mask, jarak | Deteksi, urgensi, level, getar | Memori server |
| Suara | `PerencanaSuara` | Daftar deteksi | Rencana segmen dan teks | Memori server |
| Riwayat lokal | `_simpan_riwayat` | Hasil deteksi | Baris JSONL | `data/riwayat.jsonl` |
| Sinkronisasi | `_simpan_deteksi_supabase` | Hasil deteksi | Baris `detections` | Supabase REST |
| Baca web | `useVestData.js` | Tabel Supabase | State dashboard | `supabase-js` |
| Fallback web | FastAPI | Perangkat atau Supabase kosong | Data dashboard | `/dashboard/data`, `/riwayat` |

### Tabel Supabase yang dipakai

| Tabel | Kolom yang dibaca atau ditulis | Fungsi |
|---|---|---|
| `devices` | `id`, `name`, `student_name`, `school`, `battery`, `online`, `last_seen` | Identitas dan status perangkat |
| `detections` | `id`, `device_id`, `object`, `distance_m`, `confidence`, `urgency`, `lat`, `lng`, `urgency_score`, `created_at` | Riwayat objek terdeteksi |
| `gps_log` | `id`, `device_id`, `lat`, `lng`, `accuracy`, `created_at` | Posisi terakhir perangkat |

Catatan skema:

- Server hanya menulis `devices` dan `detections`. Tabel `gps_log` dibaca oleh dashboard dan harus diisi oleh perangkat atau proses lain.
- Kolom `urgency` memakai nilai `Tinggi`, `Sedang`, atau `Rendah`. Kolom `urgency_score` memakai skor fuzzy 0 sampai 100.
- Repo tidak menyertakan migrasi SQL. Pastikan tabel dan kolom di atas sudah ada di proyek Supabase.
- Aktifkan Row Level Security dan policy `SELECT` yang sesuai untuk pembacaan browser.
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
| `VEST_SUARA_FOLDER` | Folder pustaka suara, default `suara-natural-ai/cache_ardi` |
| `VEST_RIWAYAT_PATH` | Path riwayat JSONL, default `data/riwayat.jsonl` |
| `VEST_HOST` | Host server, default `127.0.0.1` |
| `VEST_PORT` | Port server, default `8080` |
| `SUPABASE_URL` | URL proyek Supabase |
| `SUPABASE_SERVICE_ROLE_KEY` | Service-role key untuk penulisan backend |
| `VEST_SUPABASE_DEVICE_ID` | UUID perangkat virtual, opsional |

Frontend, dibaca dari `vest-care-react/.env.local`:

| Kunci | Fungsi |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` atau `VITE_SUPABASE_URL` | URL proyek Supabase untuk browser |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` atau `VITE_SUPABASE_ANON_KEY` | Publishable atau anon key untuk pembacaan browser |

### Endpoint API

| Method | Path | Keterangan |
|---|---|---|
| `GET` | `/info` | Info versi, model, `imgsz`, `conf`, `conf_ragu`, status engine |
| `GET` | `/status` | Status server, engine, suara, dan koneksi Supabase |
| `GET` | `/` | Dashboard React VestCare |
| `GET` | `/app` | Alias dashboard React VestCare |
| `GET` | `/docs` | Dokumentasi OpenAPI |
| `GET` | `/dashboard/data` | Data perangkat, deteksi, dan GPS langsung dari Supabase |
| `POST` | `/deteksi` | Upload gambar multipart dan `jarak_m` opsional |
| `POST` | `/deteksi/suara` | Sama seperti `/deteksi`, dengan rencana suara |
| `POST` | `/peringatan` | JSON `{ "skor_risiko": 0..1, "jarak_m": ... }` |
| `GET` | `/riwayat?limit=20` | Riwayat deteksi lokal terakhir |
| `GET` | `/suara/pratinjau` | Contoh rencana suara |
| `GET` | `/suara/{nama_berkas}` | Berkas klip suara yang diizinkan |

Jika `VEST_API_KEY` aktif, sertakan header `X-API-Key` pada setiap request yang diproteksi. Browser memakai cookie sesi HttpOnly yang dipasang saat halaman utama dibuka.

## Struktur proyek

| Path | Fungsi |
|---|---|
| `server_rest_api.py` | Server FastAPI, engine YOLO, fuzzy, suara, riwayat, Supabase, dan tunnel ngrok |
| `fuzzysugeno.py` | Fuzzy Sugeno, `analisis_hasil`, `PelacakGerak`, `IngatanHalangan`, dan penanda ragu |
| `start_train.py` | Entry point pipeline training |
| `train_semua.py` | Pipeline training 5 kelas, quality gate, evaluasi akhir, dan pembersihan run lama |
| `start_eval.py` | Evaluasi model per kelas dan per varian dataset |
| `dataset_gabungan.yaml` | Konfigurasi dataset gabungan 5 kelas |
| `models/best.pt` | Bobot aktif yang dipakai server |
| `vest-care-react/` | Dashboard React, hasil build disajikan dari `vest-care-react/dist/` |
| `vest-care-react/src/useVestData.js` | Pembacaan Supabase dan fallback API |
| `vest-care-react/src/components/CameraCapture.jsx` | Kamera, pengiriman frame, kotak objek, dan pemutaran suara |
| `suara-natural-ai/` | Pustaka klip suara, perakit kalimat, dan contoh integrasi |
| `runs/segment/runs/` | Artefak training, laporan, dan evaluasi |
| `data/riwayat.jsonl` | Riwayat deteksi lokal, tidak di-commit |

## Cara menjalankan

### Prasyarat

- Python 3.10 atau lebih baru dan virtual environment `.venv`.
- Dependensi utama: `ultralytics`, `fastapi`, `uvicorn`, `pillow`, `numpy`, `python-multipart`.
- Untuk suara: `pip install -r suara-natural-ai/requirements_pemutar.txt`, membutuhkan `pygame-ce`.
- Untuk tunnel publik: `ngrok` tersedia di `PATH`.
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
VEST_HOST=127.0.0.1
VEST_PORT=8080
SUPABASE_URL=https://<proyek>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

Jalankan:

```powershell
cd vest-care-react
npm install
npm run build
cd ..
python server_rest_api.py
```

Server membuka API lokal dan tunnel ngrok. URL utama ngrok langsung menampilkan dashboard React, sedangkan `/app` tetap menjadi alias. Dokumentasi interaktif tersedia di `/docs`. Build dashboard perlu diperbarui dengan `npm run build` setiap kali source React berubah.

### Deteksi dari kamera tanpa dashboard

```powershell
python suara-natural-ai/jalankan_fuzzy.py --sumber 0
```

Gunakan `--sumber` untuk indeks kamera atau path video. Contoh integrasi tanpa kamera tersedia di `suara-natural-ai/contoh_integrasi.py`.

## Artefak dan log

| Artefak | Path |
|---|---|
| Log training root | `training_semua_20261107_154452_851599.log` |
| Log run | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/training.log` |
| Log mentah | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/raw/training.log` |
| Laporan training | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.txt` |
| Laporan JSON | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.json` |
| Metrik per kelas | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/val_class_metrics.csv` |
| Evaluasi akhir | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/` |
| Log evaluasi | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/evaluation_20261108_000253.log` |
| Ringkasan akurasi | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/laporan_akurasi.txt` |
| Kecepatan | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/kecepatan.json` |
| Bobot terbaik | `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/weights/best.pt` |

### Ukuran artefak mentah

| File | Ukuran byte | Ukuran perkiraan |
|---|---:|---:|
| `training_semua_20261107_154452_851599.log` | 12.800.220 | 12,2 MiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/training.log` | 12.800.220 | 12,2 MiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/raw/training.log` | 12.800.220 | 12,2 MiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/results.csv` | 18.044 | 17,6 KiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/raw/results.csv` | 18.044 | 17,6 KiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.json` | 11.019 | 10,8 KiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/training_report.txt` | 1.911 | 1,9 KiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/reports/val_class_metrics.csv` | 906 | 0,9 KiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/evaluation_20261108_000253.log` | 33.212 | 32,4 KiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/ringkasan_test.json` | 7.282 | 7,1 KiB |
| `runs/segment/runs/semua_kelas_yolo26n_20261107_154452/evaluation/final/kecepatan.json` | 191 | 0,2 KiB |

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
