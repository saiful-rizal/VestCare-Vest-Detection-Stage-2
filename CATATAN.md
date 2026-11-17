# Cara pakai (urutan)

## Susunan folder

- `library/`: modul fuzzy dan pustaka suara.
- `web/`: halaman web statis, aplikasi React (`web/react/`), dan arsip web.
- `data/datasets/`: dataset utama, penunjang, dan dataset sumber.
- `data/results/`: hasil evaluasi dan run training/split.
- `data/runtime/`: riwayat server, URL publik, dan cache audio.
- `data/archive/`: arsip proyek lama.
- `hardware/arduino/`: firmware Wemos.

1. Salin file ke folder proyek (timpa yang lama). `split_dataset.py` adalah file BARU.
   Untuk web: salin `web/react/src/components/CameraCapture.jsx` dan timpa folder `web/react/dist`.
2. Cek pembagian data dulu (tanpa training):
   `python start_train.py --siapkan-data-saja`
3. Training penuh: `python start_train.py`
   - seed split dipilih otomatis (hasil dicetak + disimpan di `data/results/runs/dataset_splits/*/split_manifest.json`)
   - beberapa seed training: `python start_train.py --seeds-latih 0,42,123`
4. Evaluasi ulang di data test kapan saja: `python start_eval.py --split test`.
   Hasil evaluasi default disimpan di `data/results/hasil_08/`.
5. Restart `server_rest_api.py` (server otomatis membaca `models/best.pt` + `models/ambang_conf.json`).

## Arsitektur model

- Training memakai `cfg/yolo26n-seg-semua-c3k.yaml`: semua layer `C3k2` memakai `c3k=True`
  (satu layer terakhir tetap memakai varian attention `attn=True`, sesuai desain YOLO26).
- Bobot pretrained `yolo26n-seg.pt` tetap dimuat sejauh bentuk layernya cocok; dua blok
  `C3k2` yang berubah dilatih dari nol.
- Karena arsitektur berubah, model lama `models/best.pt` tidak kompatibel penuh.
  Jalankan `python start_train.py` untuk melatih ulang dan memasang model baru.
