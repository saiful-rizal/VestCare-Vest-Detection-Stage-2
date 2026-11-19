# VestCare ESP32-S3 N16R8 + OV3660

Sketch ini mengambil frame JPEG dari kamera OV3660 bawaan board ESP32-S3 N16R8
setiap sekitar 800 ms, mengirimnya ke `POST /deteksi` pada server VestCare
sebagai multipart form, lalu menyimpan ringkasan hasil di halaman bawaan ESP32.
Server menjalankan model YOLO; hasil disimpan sebagai riwayat dan ditampilkan
pada dashboard melalui polling `GET /dashboard/data`.

## Persiapan

- Arduino IDE dengan package board **esp32 by Espressif Systems**.
- Pilih board **ESP32S3 Dev Module** dan aktifkan PSRAM **OPI PSRAM**.
- Pasang library **WiFiManager**. `esp_camera` sudah disertakan pada package
  ESP32 Arduino.
- Salin `secrets.h.example` menjadi `secrets.h`, lalu isi
  `VEST_API_KEY` menggunakan nilai `VEST_API_KEY` dari `.env` server. Jangan
  commit atau membagikan `secrets.h`.
- Periksa `SERVER_URL` pada sketch dan sesuaikan jika alamat publik server
  berubah.

Pin kamera menggunakan mapping DVP umum untuk board ESP32-S3 N16R8 yang
kompatibel dengan `CAMERA_MODEL_ESP32S3_EYE`: XCLK GPIO15, SCCB GPIO4/5,
data GPIO8-12 dan 16-18, VSYNC GPIO6, HREF GPIO7, serta PCLK GPIO13.
XCLK disetel ke 10 MHz untuk kestabilan OV3660. Pin kamera tidak boleh dipakai
untuk sensor lain. Board ini tidak memiliki cukup GPIO bebas untuk wiring GPS
dan HC-SR04 seperti pada sketch Wemos; telemetri dari Wemos terpisah tetap dapat
dipakai server untuk lokasi dan jarak.

Endpoint deteksi dilindungi autentikasi API key. Jika key kosong atau tidak
cocok, server akan menolak gambar dan Serial Monitor menampilkan status HTTP.

Saat Wi-Fi belum dikonfigurasi, perangkat membuat access point
`VestCare-ESP32S3` dengan kata sandi `12345678`. Hubungkan ponsel ke access
point itu, lalu pilih Wi-Fi yang memiliki akses ke server. Buka Serial Monitor
pada 115200 baud untuk memeriksa inisialisasi kamera dan hasil request deteksi.

Untuk menampilkan stream ESP32 pada dashboard React, isi
`VITE_ESP32_STREAM_URL` di `web/react/.env` dengan URL
`http://IP_ESP32:81/stream`, lalu jalankan ulang build/development server:

```powershell
cd web/react
npm run build
```
