# API Cloudflare VestCare

Dokumen ini menjelaskan API publik VestCare yang diterbitkan melalui
**Cloudflare Tunnel**. API berjalan di FastAPI lokal pada `127.0.0.1:8000`,
kemudian Cloudflare menyediakan HTTPS publik tanpa membuka port router.

Ini bukan Cloudflare Worker. Model YOLO dan fuzzy tetap berjalan di komputer
server karena membutuhkan `models/best.pt` dan proses Python.

## 1. URL publik

URL Quick Tunnel yang aktif saat dokumen ini dibuat:

```
https://well-consists-ana-touch.trycloudflare.com
```

URL Quick Tunnel bersifat sementara dan berubah setiap kali tunnel dijalankan
ulang. URL terbaru juga ditulis otomatis ke:

```
data/public_url.txt
```

Untuk URL permanen, gunakan named tunnel dengan domain sendiri dan
`CLOUDFLARED_TOKEN` seperti dijelaskan pada bagian 8.

## 2. Arsitektur

```
Klien (curl, ponsel, aplikasi)
        |
        | HTTPS
        v
Cloudflare Edge
        |
        | Tunnel keluar (cloudflared)
        v
FastAPI 127.0.0.1:8000
        |
        v
YOLO26n-Seg + Fuzzy Sugeno + output suara
```

Cloudflare Tunnel membuat koneksi keluar dari komputer server. Port 8000 tidak
perlu dibuka di firewall dan tidak perlu alamat IP publik.

## 3. Autentikasi

Ada dua cara mengakses endpoint operasi.

### 3.1 Halaman web `/app` tanpa API key

Saat pengguna membuka `/app`, server menerbitkan cookie sesi `vestcare_sesi`
yang ditandatangani HMAC memakai `VEST_API_KEY`. Cookie bersifat `HttpOnly`,
`SameSite=Lax`, berlaku 12 jam, dan otomatis memakai atribut `Secure` bila
diakses melalui HTTPS (termasuk Cloudflare Tunnel).

Browser memakai cookie tersebut secara otomatis untuk `/deteksi`, `/riwayat`,
dan `/suara/...`. Pengguna ponsel tidak perlu mengetik API key.

### 3.2 Klien API dengan header

Klien non-browser memakai header:

```
X-API-Key: <VEST_API_KEY>
```

`VEST_API_KEY` diambil dari file `.env` dan wajib berupa string acak minimal 32
karakter. Kunci yang salah atau tidak dikirim menghasilkan HTTP 401.

Contoh header yang benar:

```powershell
$headers = @{ "X-API-Key" = "KUNCI_API_ANDA" }
```

Jangan membagikan `.env` atau kunci API. Karena `/app` menerbitkan sesi tanpa
meminta kunci, URL publik `/app` harus diperlakukan seperti kunci: siapa pun
yang mengetahui alamatnya dapat membuka halaman kamera. Untuk produksi,
lindungi dengan Cloudflare Access atau batasi akses di named tunnel.

## 4. Daftar endpoint

| Metode | Path | Autentikasi | Kegunaan |
|---|---|---|---|
| GET | `/` | Tidak | Informasi server dan status model |
| GET | `/app` | Tidak | Halaman kamera dan suara untuk ponsel |
| GET | `/status` | Tidak | Health check ringan |
| GET | `/docs` | Tidak | Dokumentasi interaktif Swagger UI |
| GET | `/redoc` | Tidak | Dokumentasi ReDoc |
| POST | `/deteksi` | Ya | Deteksi gambar, hitung urgensi, dan susun rencana suara |
| POST | `/deteksi/suara` | Ya | Deteksi dan putar suara di server |
| POST | `/peringatan` | Ya | Hitung fuzzy tanpa gambar |
| GET | `/riwayat` | Ya | Baca riwayat deteksi |
| GET | `/suara/pratinjau` | Ya | Rencana suara contoh untuk tes di `/app` |
| GET | `/suara/{berkas}` | Ya | Unduh satu klip MP3 Ardi |

Autentikasi "Ya" menerima header `X-API-Key` atau cookie sesi dari `/app`.
Batas unggahan gambar adalah 10 MB dan 40 megapiksel. Parameter `jarak_m` pada
`/deteksi` memiliki rentang 0.03 sampai 3.0 meter.

## 5. Contoh penggunaan

### 5.1 Health check

```powershell
curl.exe https://well-consists-ana-touch.trycloudflare.com/status
```

Respons:

```json
{
  "server": "VestCare API",
  "versi": "2.0.0",
  "engine_siap": true,
  "api_terproteksi": true,
  "pustaka_suara_siap": true,
  "waktu_server": "2026-11-07 10:09:40"
}
```

### 5.2 Fuzzy tanpa gambar

```powershell
curl.exe -X POST https://well-consists-ana-touch.trycloudflare.com/peringatan `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -H "Content-Type: application/json" `
  -d "{\"skor_risiko\":0.9,\"jarak_m\":1.0}"
```

Respons:

```json
{
  "skor_risiko": 0.9,
  "jarak_m": 1.0,
  "peringatan": {
    "tingkat": "bahaya",
    "nilai_crisp": 0.9833,
    "getar": {
      "pwm": 255,
      "interval_ms": 150,
      "pola": "terus-menerus cepat"
    },
    "keterangan": "Sugeno orde-nol: urgensi=98.3"
  }
}
```

### 5.3 Deteksi gambar

```powershell
curl.exe -X POST https://well-consists-ana-touch.trycloudflare.com/deteksi `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -F "gambar=@foto_jalan.jpg" `
  -F "jarak_m=0.8"
```

Respons ringkas:

```json
{
  "id": "926d9ea6c4c5",
  "waktu": "2026-11-07 10:10:53",
  "sumber": "deteksi",
  "jumlah_objek": 4,
  "level_tertinggi": "INFO",
  "urgensi_tertinggi": 40.0,
  "aksi_suara": null,
  "suara_diputar": false,
  "suara": {
    "level": "INFO",
    "teks": "lubang tepat di depan kira-kira satu meter Kurangi kecepatan dan berjalanlah lebih pelan",
    "aksi": "pelan",
    "segmen": [
      {
        "kunci": "benda_lubang_depan_netral",
        "teks": "lubang tepat di depan",
        "berkas": "benda_lubang_depan_netral_3.mp3",
        "url": "/suara/benda_lubang_depan_netral_3.mp3"
      },
      {
        "kunci": "jarak_10",
        "teks": "kira-kira satu meter",
        "berkas": "jarak_10_2.mp3",
        "url": "/suara/jarak_10_2.mp3"
      },
      {
        "kunci": "solusi_pelan",
        "teks": "Kurangi kecepatan dan berjalanlah lebih pelan",
        "berkas": "solusi_pelan_1.mp3",
        "url": "/suara/solusi_pelan_1.mp3"
      }
    ]
  },
  "deteksi": [
    {
      "kelas": "lubang",
      "arah": "depan",
      "jarak_m": 0.8,
      "urgensi": 40.0,
      "level": "INFO",
      "conf": 0.51,
      "sumber": "kamera+ultrasonik",
      "pesan": "INFO: lubang depan, sekitar 0.8 meter",
      "getar": {
        "pwm": 80,
        "interval_ms": 1000,
        "pola": "denyut tunggal lemah"
      }
    }
  ]
}
```

### 5.4 Deteksi dan suara server

```powershell
curl.exe -X POST https://well-consists-ana-touch.trycloudflare.com/deteksi/suara `
  -H "X-API-Key: KUNCI_API_ANDA" `
  -F "gambar=@foto_jalan.jpg" `
  -F "jarak_m=0.8"
```

Endpoint ini hanya memutar suara jika `VEST_TANPA_SUARA=0` dan perangkat server
memiliki speaker serta FFmpeg. Untuk penggunaan di ponsel, gunakan `/app`:
browser memutar klip Ardi dari `suara-natural-ai/cache_ardi` sesuai rencana
suara pada respons `/deteksi`.

### 5.5 Riwayat deteksi

```powershell
curl.exe "https://well-consists-ana-touch.trycloudflare.com/riwayat?limit=20" `
  -H "X-API-Key: KUNCI_API_ANDA"
```

Respons berisi `total`, `ditampilkan`, dan `data` berupa entri terbaru.

### 5.6 Halaman kamera ponsel

Buka:

```
https://well-consists-ana-touch.trycloudflare.com/app
```

Tidak perlu memasukkan API key. Server menerbitkan cookie sesi saat halaman
dibuka. Tekan **Aktifkan kamera belakang**, izinkan kamera, lalu tekan
**Deteksi dan putar suara Ardi**. Browser mengirim gambar ke `/deteksi` dan
memutar segmen MP3 Ardi sesuai level fuzzy (AMAN, INFO, WASPADA, atau BAHAYA).

Tekan **Tes suara Ardi** sekali untuk membuka izin audio browser. Tombol
**Putar ulang suara terakhir** mengulang rencana suara dari deteksi terakhir.

## 6. Format respons deteksi

Setiap entri pada array `deteksi` memiliki field berikut:

| Field | Tipe | Keterangan |
|---|---|---|
| `kelas` | string | pohon, mobil, motor, orang, atau lubang |
| `arah` | string | kiri, depan, atau kanan |
| `jarak_m` | number | estimasi jarak dalam meter |
| `urgensi` | number | nilai fuzzy 0 sampai 100 |
| `level` | string | AMAN, INFO, WASPADA, atau BAHAYA |
| `conf` | number | confidence YOLO 0 sampai 1 |
| `sumber` | string | kamera, ultrasonik, kamera+ultrasonik, default, atau ingatan |
| `pesan` | string | kalimat siap dibacakan |
| `getar` | object | `pwm`, `interval_ms`, dan `pola` untuk aktuator |

Tingkat urgensi:

| Level | Rentang |
|---|---|
| AMAN | 0 sampai kurang dari 25 |
| INFO | 25 sampai kurang dari 50 |
| WASPADA | 50 sampai kurang dari 75 |
| BAHAYA | 75 sampai 100 |

### 6.1 Rencana suara Ardi

Respons `/deteksi` dan `/deteksi/suara` memiliki field `suara`. Nilainya `null`
jika pustaka `suara-natural-ai/cache_ardi` belum siap, dan berisi objek berikut
jika tersedia:

| Field | Tipe | Keterangan |
|---|---|---|
| `level` | string | level fuzzy yang dipakai: AMAN, INFO, WASPADA, atau BAHAYA |
| `teks` | string | gabungan teks seluruh segmen |
| `aksi` | string | aksi yang dipilih, misalnya `pelan`, `berhenti`, atau `lurus` |
| `segmen` | array | daftar klip yang harus diputar berurutan |

Setiap segmen memiliki field:

| Field | Tipe | Keterangan |
|---|---|---|
| `kunci` | string | kunci manifest, misalnya `awal_bahaya` atau `jarak_10` |
| `teks` | string | teks klip |
| `berkas` | string | nama berkas MP3 di `cache_ardi` |
| `url` | string | URL relatif untuk memutar klip melalui `/suara/{berkas}` |

Urutan segmen mengikuti aturan fuzzy dan pustaka Ardi. Contoh untuk BAHAYA:

```text
awal_bahaya -> benda_lubang_depan_netral -> jarak_05 -> solusi_berhenti
```

Untuk level AMAN, rencana berisi klip `jalur_aman`. Varian klip dipilih acak
oleh server agar suara tidak selalu sama.

## 7. Kode error

| Kode | Penyebab |
|---|---|
| 400 | File gambar tidak valid atau tidak bisa dibaca |
| 401 | `X-API-Key` atau cookie sesi salah/tidak disertakan |
| 404 | Berkas suara tidak ada di pustaka |
| 413 | Gambar melebihi 10 MB atau 40 megapiksel |
| 422 | Body JSON atau parameter query tidak valid |
| 503 | `VEST_API_KEY` belum dikonfigurasi, engine model belum siap, atau pustaka suara belum siap |

Contoh respons 401:

```json
{
  "detail": "X-API-Key atau sesi web salah atau tidak disertakan."
}
```

## 8. Menjalankan dan menerbitkan API

### 8.1 Quick Tunnel

Prasyarat: `cloudflared` sudah terpasang dan `.env` berisi `VEST_API_KEY`.

```powershell
.\start_all.bat
```

Perintah tersebut menjalankan server FastAPI dan tunnel. URL publik akan muncul
di jendela tunnel dan disimpan ke `data/public_url.txt`.

Untuk menjalankan tunnel saja, pastikan server sudah aktif:

```powershell
.\run_tunnel.bat
```

### 8.2 Named tunnel dengan domain sendiri

1. Tambahkan domain ke Cloudflare.
2. Buat tunnel di dashboard Cloudflare Zero Trust.
3. Salin token tunnel ke `.env`:

```text
CLOUDFLARED_TOKEN=token-dari-cloudflare
```

4. Di dashboard Cloudflare Zero Trust, buat **Public Hostname** yang mengarah
   ke `http://127.0.0.1:8000`.
5. Jalankan:

```powershell
.\run_tunnel.bat
```

Skrip akan memakai `CLOUDFLARED_TOKEN` dan menjalankan
`cloudflared tunnel run --token ...`. Dengan cara ini, hostname dan DNS diatur
dari dashboard Cloudflare.

Alternatif tanpa token adalah menjalankan named tunnel dengan konfigurasi
lokal `cloudflared.yml`:

```yaml
tunnel: vestcare-tunnel
credentials-file: ~/.cloudflared/vestcare-tunnel.json

ingress:
  - hostname: api.domain-anda.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Jalankan konfigurasi tersebut secara manual:

```powershell
cloudflared tunnel --config cloudflared.yml run
```

Dengan named tunnel, URL publik mengikuti hostname yang didaftarkan di
Cloudflare, bukan URL `trycloudflare.com` sementara.

## 9. Catatan keamanan

1. Gunakan kunci API acak minimal 32 karakter. Jangan memakai contoh di
   `.env.example`.
2. Jangan commit `.env` atau membagikan isinya.
3. Quick Tunnel tidak memberikan autentikasi tambahan. Endpoint API tetap
   memerlukan `X-API-Key`, tetapi `/app` menerbitkan cookie sesi tanpa meminta
   kunci. Perlakukan URL `/app` sebagai rahasia dan gunakan Cloudflare Access
   untuk produksi.
4. Untuk produksi, gunakan named tunnel, batasi akses dengan Cloudflare Access,
   dan aktifkan logging.
5. Batasi ukuran unggahan dan lakukan validasi gambar di sisi klien sebelum
   mengirim ke API.
6. Ganti kunci API secara berkala dan pantau endpoint `/status` untuk memastikan
   engine model serta pustaka suara tetap siap.
7. Cookie sesi ditandatangani HMAC dan tidak dapat dipalsukan tanpa
   `VEST_API_KEY`. Cookie tetap `HttpOnly` agar tidak dapat dibaca JavaScript.

## 10. Pustaka suara Ardi

Klip suara berada di:

```text
suara-natural-ai/cache_ardi/
├── manifest.json
├── awal_bahaya_1.mp3
├── awal_waspada_1.mp3
├── benda_lubang_depan_netral_1.mp3
├── jarak_10_1.mp3
├── solusi_berhenti_1.mp3
└── ...
```

Folder ini disertakan di repositori agar `/app` langsung dapat memutar suara
Ardi. `manifest.json` berisi 38 kunci pesan untuk level, kelas, arah, jarak, dan
solusi. Jika pustaka dibuat ulang dengan `siapkan_pustaka.py`, sesuaikan
`VEST_SUARA_FOLDER` di `.env`:

```text
VEST_SUARA_FOLDER=suara-natural-ai/cache_ardi
```

Server memilih klip tanpa membutuhkan pygame atau speaker. Browser memutar
berkas MP3 melalui endpoint `/suara/{berkas}` menggunakan cookie sesi.
