# VestCare - Vest Detection System

## Arsitektur Model YOLO26n-SEG

Arsitektur ini berdasarkan model **YOLO26n-seg** yang merupakan versi nano (n) dari arsitektur YOLO untuk tugas segmentasi. Alur proses arsitektur secara menyeluruh dari input gambar hingga output deteksi adalah sebagai berikut:

### Alur Proses Arsitektur (Secara Menyeluruh)

```mermaid
flowchart LR
    I["Input Gambar 512x512x3"] --> C1["Conv P1/2\n3x3, stride 2"]
    C1 --> C2["Conv P2/4\n3x3, stride 2"]
    C2 --> B1["C3k2 P2/4\nBottleneck C3k2"]
    B1 --> C3["Conv P3/8\n3x3, stride 2"]
    C3 --> B2["C3k2 P3/8\nBottleneck C3k2"]
    B2 --> C4["Conv P4/16\n3x3, stride 2"]
    C4 --> B3["C3k2 P4/16\nBottleneck C3k2"]
    B3 --> C5["Conv P5/32\n3x3, stride 2"]
    C5 --> B4["C3k2 P5/32\nBottleneck C3k2"]
    B4 --> S["SPPF\nSpatial Pyramid Pooling Fast"]
    S --> A["C2PSA\nC2 dengan perhatian spasial"]
    A --> N["Neck\ngabungkan fitur P3/P4/P5"]
    N --> H["Head Segmentasi\nkelas, kotak, mask"]
    H --> O["Output: Deteksi\nClasses, Bounding Box, Mask"]
```

### Detail Tahapan Lapisan per Tahap

| Tahap / Lapisan | Ukuran Filter (Kernel) | Tinggi | Lebar | Fungsi |
|---|---|---|---|---|
| **Input** | - | 512 | 512 | Gambar RGB input 512x512x3 |
| **Conv P1/2** | 3x3 | - | - | Konvolusi awal dengan stride 2 untuk mengekstrak fitur dasar (tepi, tekstur); resolusi menjadi 1/2 dari input |
| **Conv P2/4** | 3x3 | - | - | Konvolusi kedua dengan stride 2; memperkaya fitur awal; resolusi menjadi 1/4 input |
| **C3k2 P2/4** | 3x3 (dalam blok) | - | - | Blok ekstraksi fitur berbasis bottleneck C3k2; mengolah pola awal dan meneruskan fitur ke lapisan selanjutnya |
| **Conv P3/8** | 3x3 | - | - | Konvolusi dengan stride 2; menurunkan resolusi ke skala 1/8 dari input |
| **C3k2 P3/8** | 3x3 (dalam blok) | - | - | Blok ekstraksi fitur C3k2 pada skala P3/8; memperkuat fitur objek kecil; keluarannya menjadi salah satu masukan neck |
| **Conv P4/16** | 3x3 | - | - | Konvolusi dengan stride 2; menurunkan resolusi ke skala 1/16 dari input |
| **C3k2 P4/16** | 3x3 (dalam blok) | - | - | Blok ekstraksi fitur C3k2 pada skala P4/16; memperkuat fitur objek sedang; keluarannya menjadi masukan neck |
| **Conv P5/32** | 3x3 | - | - | Konvolusi dengan stride 2; menurunkan resolusi ke skala 1/32 dari input untuk konteks yang lebih luas |
| **C3k2 P5/32** | 3x3 (dalam blok) | - | - | Blok ekstraksi fitur C3k2 pada skala P5/32; memperkuat fitur semantik objek besar sebelum SPPF |
| **SPPF** | Pooling bertingkat | - | - | Spatial Pyramid Pooling - Fast; menggabungkan konteks dari area/reseptif yang lebih luas secara efisien |
| **C2PSA** | 3x3 (dalam blok) | - | - | Blok C2 dengan perhatian spasial; memberikan bobot lebih pada area fitur penting sebelum fitur P5 diteruskan ke neck |
| **Neck** | - | - | - | Menggabungkan fitur dari P3, P4, dan P5 (multi-scale features) |
| **Head Segmentasi** | - | - | - | Memproses fitur multi-skala untuk menghasilkan prediksi: kelas objek, kotak pembatas (bounding box), dan mask segmenisasi |

### Fungsi Aktivasi

- **SiLU (Swish)** digunakan sebagai fungsi aktivasi utama di seluruh arsitektur YOLO26n-seg.
- Fungsi ini juga dikenal sebagai `swish` dan ditetapakan sebagai `nn.SiLU` dalam implementasi PyTorch.
- Fungsi SiLU didefinisikan sebagai: `f(x) = x * sigmoid(x)` atau `x / (1 + exp(-x))`.
- Fungsi aktivasi ini membantu model belajar fitur yang lebih baik dan memiliki properti yang lebih smooth dibanding ReLU klasik.

### Batch Normalization (BatchNorm)

- **Batch Normalization tersedia** di setiap konvolusi (Conv layer) di seluruh backbone arsitektur.
- Setiap lapisan Conv diikuti dengan BatchNorm untuk normalisasi output terhadap batch, yang membantu stabilisasi training dan mempercepat konvergensi.
- Struktur blok C3k2 juga menyertakan komponen normalisasi internal.
- Tidak ada layer secara eksplisit tanpa BatchNorm di susunan arsitektur standar ini.

### Acuan Sumber dan Framework

#### Arsitektur Dasar
- Arsitektur berdasarkan **YOLOv8-seg** dengan adaptasi untuk 5 kelas vestcare (lubang, mobil, motor, orang, pohon).
- Struktur backbone dan neck mengikuti definisi bawaan model YOLO26n-seg.
- Merujuk pada diagram dan penjelasan lengkap yang ada di jurnal serta Presentasi PowerPoint (PPT) yang telah dibagikan sebelumnya.
- Arsitektur default tanpa modifikasi tunai yang signifikan pada struktur utama.

#### Framework
- **PyTorch**: Implementasi model dan seluruh operasi training/evaluasi dilakukan menggunakan framework PyTorch melalui library Ultralytics YOLO.
- **Tensor**: Operasi tensor dilakukan di dalam PyTorch, termasuk forward pass, backward pass (backpropagation), dan semua operasi pada lapisan konvolusi, pooling, dan normalisasi.
- **Ultralytics YOLO**: Library pengubah yang menyediakan model YO26n-seg, fungsi training, validasi, dan evaluasi.
- **Python**: Semua kode server, inferensi, dan pengelolaan dataset ditulis dalam Python 3.

### Ringkasan Konfigurasi Training

| Parameter | Nilai |
|---|---|
| **Model** | yolo26n-seg.pt |
| **Ukuran Gambar** | 512 x 512 pixels |
| **Batch Size** | 4 |
| **Epochs** | 100 (maksimal) |
| **Optimizer** | AdamW |
| **Learning Rate (lr0)** | 0.001 |
| **Momentum** | 0.937 |
| **Weight Decay** | 0.0005 |
| **Device** | GPU 0 |
| **Seed** | 0 |
| **Deterministic** | True |

### Daftar Kelas Deteksi

Model mendeteksi 5 kelas utama plus kelas internal penolak objek:

| ID Kelas | Nama Kelas | Deskripsi |
|----------|------------|-----------|
| 0 | pohon | Pohon/plant deteksi |
| 1 | mobil | Kendaraan motor road |
| 2 | motor | Sepeda motor |
| 3 | orang | Orang/dewasa |
| 4 | lubang | Lubang/celah deteksi |
| 5 | __non_target_internal__ | Kelas internal untuk objek yang tidak target |

### Alur Proses dari Input hingga Output Deteksi

1. **Input**: Gambar RGB berukuran 512x512x3 dimasukkan ke model
2. **Backbone Feature Extraction**: Melalui rangkaian konvolusi (Conv) dan blok bottleneck (C3k2) dengan penurunan resolusi bertahap (stride 2) dari P1/2 hingga P5/32
   - Setiap lapisan diikuti Batch Normalization untuk stabilisasi
   - Fungsi aktivasi SiLU diterapkan setelah setiap konvolusi
3. **Context Enhancement**: Melalui SPPF (Spatial Pyramid Pooling Fast) untuk mengumpulkan konteks multi-skalanya dari area yang lebih luas
4. **Spatial Attention**: Melalui C2PSA (C2 dengan perhatian spasial) untuk menonjolkan fitur penting sebelum diteruskan ke neck
5. **Neck Integration**: Fitur dari P3, P4, dan P5 digabungkan di Neck layer untuk fitur multi-scale
6. **Head Segmentasi**: Produksi output berupa:
   - Klasifikasi kelas objek (5 kelas: lubang, mobil, motor, orang, pohon)
   - Bounding box (kotak pembatas) dengan confidence score
   - Mask segmenisasi (pengsegmentasian objek)
7. **Post-Processing**: Hasil deteksi di-analisis melalui:
   - Fuzzy logic Sugeno untuk menentukan urgensi level (AMAN/INFO/WASPADA/BAHAYA)
   - Pelacakan gerak pelacak untuk memonitor posisi objek
   - Generasi output suara berdasarkan deteksi dan level urgensi
8. **Output**: Deteksi lengkap dengan confidence score, kelas, mask, dan informasi urgensi yang diproses ke sistem suara

### Pipeline Inferensi Lengkap

```mermaid
flowchart LR
    Gambar["Input Gambar"] -->|Preprocessing| Model["YOLO26n-seg Model"]
    Model -->|Forward Pass| Deteksi["Hasil Deteksi Mentah"]
    Deteksi -->|analisis_hasil| PostProcessing["Post-Processing & Fuzzy Logic"]
    PostProcessing -->|Level Urgensi| Suara["Sistem Suara"]
    Suara -->|Output Audio| Antarmuka["Dashboard VestCare"]
```

### Sistem Post-Processing & Suara

Setelah model menghasilkan deteksi, langkah-langkah berikut dilakukan:

1. **analisis_hasil**: Mengolah output model untuk mengekstrak deteksi yang valid
2. **Pelacak Gerak**: Melacak gerak objek across frames untuk stabilitas deteksi
3. **validasi_nama_kelas**: Memastikan nama kelas sesuai ekspektasi
4. **Perencanaan Suara**: Menentukan segment suara yang sesuai berdasarkan:
   - Level ketegangan (level: AMAN/INFO/WASPADA/BAHAYA)
   - Arah objek (kiri, depan, kanan)
   - Jarak objek (5cm - 50cm dalam bucket 5)
   - Jenis objek (benda_xxx_xxx_netral)
5. **Generasi Suara**: Mengoutputkan klip suara yang sesuai untuknotifikasi pengguna

### Konfigurasi Sistem

| Setting | Nilai Default | Keterangan |
|---------|--------------|------------|
| **Confidence Threshold** | 0.35 | Ambang batas kepercayaan deteksi |
| **Confidence Ragu** | 0.50 | Ambang batas untuk kelas "ragu" |
| **Image Size** | 512 | Ukuran input gambar (px) |
| **API Key** | Di .env | Minimal 32 karakter acak |
| **Port** | 8080 | Port server API |
| **GPU Device** | 0 | Device GPU yang digunakan |
| **Supabase Connection** | Sesuai .env | Untuk menyimpan riwayat deteksi |

### Persyaratan Sistem

- **Python**: 3.9+ recommended
- **PyTorch**: Versi yang kompatibel dengan Ultralytics YOLO
- **Ultralytics YOLO**: Library untuk model dan training
- **FastAPI**: Framework server API
- **Uvicorn**: ASGI server
- **Cloudflare CLI** (opsional): Untuk tunnel publik
- **Supabase** (opsional): Untuk penyimpanan riwayat dan dashboard

### Cara Menjalankan

1. **Setup Environment**:
   ```bash
   cd VestCare-Vest-Detection-Stage-2
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Konfigurasi**:
   - Salin `.env.example` menjadi `.env`
   - Isi VEST_API_KEY dengan kunci acak 32+ karakter
   - Sesuaikan VEST_MODEL_PATH jika perlu

3. **Training Model** (jika perlu):
   ```bash
   python start_train.py
   # atau
   python server_rest_api.py train
   ```

4. **Jalankan Server**:
   ```bash
   python server.py
   # Server akan berjalan di http://127.0.0.1:8080
   # Dokumentasi API: http://127.0.0.1:8080/docs
   ```

5. **Test Deteksi**:
   ```bash
   # Melalui API
   curl -X POST "http://127.0.0.1:8080/api/deteksi/latest" \
        -H "X-API-Key: <API_KEY>" \
        -F "file=@gambar.jpg"
   ```

### Struktur Proyek Penting

```
VestCare-Vest-Detection-Stage-2/
├── models/           # File bobot model (.pt)
├── server.py         # Main FastAPI server
├── server_rest_api.py # REST API endpoints
├── train_semua.py    # Modul training utama
├── start_train.py    # Entry point training
├── start_eval.py     # Evaluasi model
├── data/             # Dataset dan konfigurasi
├── library/          # Library suara dan fuzzy logic
│   └── suara-natural-ai/ # Audio processing
├── web/              # Frontend dashboard React
├── .env              # Environment configuration
└── README.md        # Dokumentasi ini
```