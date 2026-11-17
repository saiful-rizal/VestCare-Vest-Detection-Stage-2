# Suara Natural untuk Peringatan Rintangan (skema 3, selaras Fuzzy Sugeno)

Suara sekarang **dirakit dari klip** sesuai keluaran `fuzzysugeno.py` (versi 2): benda apa, di arah mana,
(bergerak atau diam), berapa meter, dan apa yang harus dilakukan pengguna.

```
[awalan]   [benda + arah + gerak]                [jarak]               [solusi]
 Awas!   +  Ada mobil melaju cepat di sebelah kiri + sekitar satu meter + berhenti, lalu geser ke kanan.
```

## 1. Isi paket

| Berkas | Fungsi |
|---|---|
| `fuzzysugeno.py`, `uji_fuzzysugeno.py` | Fuzzy Sugeno versi 2 Anda (tidak diubah) dan ujinya |
| `definisi_suara.py` | Definisi skenario, aturan validasi kalimat (dipakai pembuat pustaka) |
| `teks_bawaan.py` | Kalimat bawaan: awalan dan jarak (selalu), sisanya untuk `--tanpa-llm` |
| `siapkan_pustaka.py` | Membuat pustaka klip (Gemini + Edge TTS), `--periksa` untuk cek kelengkapan |
| `llm.py`, `suara_natural.py` | Penyedia LLM (Gemini pindah model otomatis saat 503) dan TTS |
| `pemutar_peringatan.py` | Perakit dan pemutar (hanya butuh pygame), `PelacakGerak`, `pilih_aksi` |
| `contoh_integrasi.py` | Contoh fuzzy -> suara, dan kerangka YOLO |
| `uji_suara.py` | Uji otomatis tanpa internet dan tanpa kartu suara |

## 2. Cara kerja

**Benda** (90 klip): kelas dari `BAHAYA_KELAS` + `umum`, 3 arah. Untuk `mobil`, `motor`, `orang` ada tiga
keadaan: netral (tidak menyebut gerak), bergerak ("mobil melaju cepat", "orang berjalan"), diam
("mobil parkir", "orang berdiri"). Kelas lain hanya netral.

**Jarak** (10 klip): `jarak_m` dari fuzzy dibulatkan ke 0,5 m terdekat, diucapkan "kurang dari satu meter",
"sekitar satu meter", ... "sekitar lima meter".

**Solusi** (7 klip), dipilih `pilih_aksi()` dari level, arah, dan sisi mana yang kosong:

| Benda | INFO | WASPADA | BAHAYA |
|---|---|---|---|
| Kiri / kanan | lurus | pelan, geser ke sisi berlawanan | berhenti, geser ke sisi berlawanan |
| Depan | pelan | pelan ke sisi kosong (bila kedua kosong: `SISI_DEFAULT`) | berhenti (+ sisi bila hanya satu yang kosong) |

Arahan **selalu menjauh dari benda**. Bila sisi berlawanan juga ada bendanya, hanya "pelan" atau "berhenti".
Benda yang `bergerak` pada level INFO diberi arahan "pelan".

**Awalan**: "Hati-hati" (WASPADA) dan "Awas" (BAHAYA). INFO tanpa awalan. Level AMAN tidak diucapkan; setelah
semua benda AMAN selama 1,5 detik, diputar "jalur aman".

**Tangga jarak untuk mobil dan motor** (`TanggaJarak`, aktif bawaan): fuzzy menilai kendaraan di samping AMAN
sampai ~1,5 m, dan pemutar hanya memakai cooldown waktu, jadi dulu baru bicara saat sudah sangat dekat. Kini:

| Tahap | Jarak | Level minimal | Kapan diucapkan |
|---|---|---|---|
| 1 | <= 5,0 m (pertama terlihat) | INFO | segera saat pertama terlihat |
| 2 | <= 3,5 m | WASPADA | sekali, saat melewati batas |
| 3 | <= 2,5 m | WASPADA | sekali, saat melewati batas |
| 4 | <= 1,5 m | BAHAYA | sekali, saat melewati batas |

Di antara dua tahap kendaraan tidak diulang-ulang berdasarkan waktu. Level fuzzy yang lebih tinggi tetap dipakai, dan
BAHAYA dari fuzzy sendiri tetap boleh berulang menurut cooldown (tidak dibisukan). Kendaraan yang `gerak == "diam"`
(parkir) paling tinggi INFO. Bila kendaraan menjauh lebih dari batas + 0,6 m lalu mendekat lagi, diingatkan lagi.
Tahap hanya dianggap sudah diumumkan bila suaranya benar-benar terputar, jadi yang tertunda oleh suara berprioritas
lebih tinggi dicoba lagi. "Jalur aman" tidak diucapkan selama kendaraan masih dalam jangkauan tangga.
Matikan dengan `PemutarPeringatan(folder, tangga=False)`; setel lewat `TANGGA_JARAK`, `KELAS_TANGGA`, `HISTERESIS_M`
di `pemutar_peringatan.py`. Tidak perlu membuat ulang pustaka klip.

**Gerak** (opsional): fuzzy dan YOLO per frame tidak tahu mobil melaju atau parkir. `PelacakGerak` menaksirnya
dari perubahan jarak antar frame. Tanpa sensor kecepatan pengguna ia hanya mengenali "bergerak" (mendekat lebih
cepat dari orang berjalan). Dengan `kecepatan_pengguna_fn` (IMU/penghitung langkah) ia juga mengenali "diam".
Jarak kamera berderau, jadi hasilnya perkiraan; jalur lain: isi `d["gerak"]` dari pelacak YOLO Anda sendiri.

## 3. Menjalankan (Windows PowerShell)

```powershell
pip install -r requirements.txt            # butuh FFmpeg terpasang
$env:GEMINI_API_KEY="kunci-baru-anda"
python siapkan_pustaka.py --suara id-ID-ArdiNeural --folder cache_ardi
python siapkan_pustaka.py --folder cache_ardi --periksa
python pemutar_peringatan.py simulasi --folder cache_ardi
python contoh_integrasi.py cache_ardi
python uji_suara.py
```

Pustaka lama (skema 2) di folder yang sama dibuat ulang otomatis. Suara kedua dengan kalimat yang sama, tanpa Gemini:
`python siapkan_pustaka.py --suara id-ID-GadisNeural --folder cache_gadis --teks-dari cache_ardi`.
Tanpa LLM sama sekali: tambahkan `--tanpa-llm`.

## 4. Menyetel

- `JEDA_SEGMEN_MS`, `PAD_AWAL_MS`, `SISI_DEFAULT` di `pemutar_peringatan.py`.
- Prioritas dan cooldown per level: `PENGATURAN_TINGKAT` di `definisi_suara.py` (lalu jalankan ulang
  `siapkan_pustaka.py`).
- Kelas baru di `BAHAYA_KELAS`: jalankan `siapkan_pustaka.py` lagi (hanya klip baru yang dibuat).

## 5. Batasan

- Klip disintesis terpisah, jadi intonasi antar klip tidak sehalus satu kalimat utuh. Dengarkan hasilnya dan
  setel jeda; klip benda dan jarak sengaja diakhiri koma agar nada tidak turun penuh.
- Kamera hanya dibaca sampai `KAMERA_MAKS_M` = 5 m. Mobil yang melaju cepat menempuh 5 m menuju 1,5 m hanya dalam
  sekitar satu detik, jadi tangga bersifat tetap menurut jarak, bukan menurut waktu tabrakan. Bila perlu, tahap bisa
  dibuat lebih awal untuk kendaraan `bergerak` (kecepatan mendekat sudah dihitung `PelacakGerak`).
- Jarak, gerak, dan sisi kosong berasal dari estimasi kamera/ultrasonik; arahan adalah bantuan, bukan jaminan.
- Fuzzy belum memakai informasi gerak, jadi mobil yang melaju di sisi samping tetap bertingkat INFO
  (arahan "pelan" ditambahkan di pemutar). Untuk membuatnya lebih tinggi, ubah aturan di `fuzzysugeno.py`.
