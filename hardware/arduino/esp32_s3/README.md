# VestCare ESP32-S3 N16R8 + OV3660

Sketch ini mengambil frame JPEG dari kamera OV3660 bawaan board ESP32-S3 N16R8.
Frame stream dikirim lewat kanal terpisah ke server, sementara frame untuk
inferensi dikirim ke `POST /deteksi` sebagai multipart form. Hasil deteksi
disimpan sebagai riwayat dan ditampilkan pada dashboard melalui polling
`GET /dashboard/data`.

## Persiapan

- Arduino IDE dengan package board **esp32 by Espressif Systems** versi 4.0.0
  atau lebih baru; sketch memakai CA bundle bawaan ESP32 untuk verifikasi HTTPS.
- Pilih board **ESP32S3 Dev Module** dan aktifkan PSRAM **OPI PSRAM**.
- Pasang library **WiFiManager**. `esp_camera` sudah disertakan pada package
  ESP32 Arduino.
- Komputer server memasang `cloudflared` dan menjalankan `python server.py`.
- Salin `secrets.h.example` menjadi `secrets.h`, lalu isi
  `VEST_API_KEY` dengan key acak minimal 32 karakter yang sama dengan Railway
  Variable `VEST_API_KEY`. Template sengaja tidak berisi key aktif. Jangan
  commit atau membagikan `secrets.h`; API key tidak dimasukkan lewat portal
  Wi-Fi.
- URL default firmware mengarah ke domain Railway aktif. `VEST_SERVER_URL`
  dapat diisi untuk mengganti server; perubahan URL atau key berlaku setelah
  firmware dibangun dan di-flash ulang. Untuk server lokal di LAN, kosongkan
  `VEST_SERVER_URL` dan set `VEST_USE_LAN_DISCOVERY` ke `1` di `secrets.h`.
  Discovery UDP hanya berfungsi jika perangkat dan server berada di LAN yang
  sama, dan responsnya ditandatangani dengan `VEST_API_KEY`.

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
point itu, lalu masukkan SSID dan kata sandi Wi-Fi melalui portal. URL server
dan API key tidak dimasukkan ke portal. Jika memakai discovery lokal, pastikan
server dan ESP32 tersambung ke LAN yang sama.

Jika URL Quick Tunnel berubah, ESP32 akan mendapatkan URL terbaru lewat
discovery otomatis bila `VEST_USE_LAN_DISCOVERY` aktif dan server serta ESP32
berada di LAN yang sama. Railway memakai domain service yang tetap, jadi tidak
memerlukan discovery lokal. Dengan URL tetap Railway, firmware mencoba ulang
request berikutnya tanpa discovery. Pada mode discovery, kegagalan API memicu
discovery ulang paling cepat setiap 15 detik. Pemeriksaan jalur jaringan tidak menahan task telemetri.
Jika proses `cloudflared` berhenti, `server.py` mencoba menjalankannya kembali;
Quick Tunnel yang baru dapat menghasilkan URL berbeda.
Port UDP `4211` harus diizinkan pada LAN agar discovery berfungsi.
Komputer server mengizinkan koneksi keluar ke internet; `python server.py`
menjalankan API lokal dan Cloudflare Quick Tunnel.

Jaringan Wi-Fi ESP32 harus memiliki internet dan mengizinkan koneksi keluar TCP
`443`. Port TCP `VEST_PORT` (default `8080`) adalah tujuan tunnel lokal.
Serial Monitor 115200 baud menampilkan status discovery dan request deteksi.
Jika request gagal, firmware memeriksa HTTPS
`/status`; `HTTP=200` berarti TLS perangkat ke server publik berhasil. Untuk
memeriksa server dan tunnel sebelum menguji perangkat, buka URL dari
`data/runtime/public_url.txt` ditambah `/status`; respons HTTP 200 berarti
server publik aktif.
Firmware memakai satu worker deteksi agar heap internal ESP32 tersisa untuk
HTTPS/TLS. Jika log tetap menunjukkan `connection refused` sementara `/status`
server publik HTTP 200, periksa baris `[NETCHECK]` pada Serial Monitor dan
pastikan jaringan ESP32 mengizinkan koneksi keluar TCP 443.

Dashboard memeriksa snapshot terbaru melalui `GET /api/esp32/frame/latest`
setiap 150 ms dan hanya mengunduh ulang frame saat ETag berubah. ESP32 mengirim
frame JPEG melalui `POST /api/esp32/frame` dengan target interval 150 ms tanpa
menunggu inferensi YOLO selesai;
server menyimpan satu frame terbaru agar antrean tidak menumpuk. Hasil dan
bounding box diperbarui dari deteksi terbaru. Status perangkat tetap online
selama telemetri atau frame baru diterima server. Pastikan firmware ESP32 dan
server menggunakan endpoint publik yang sama jika dashboard dibuka dari
jaringan lain; latensi internet tetap memengaruhi kelancaran gambar.

## Suara peringatan Ardi di website

ESP32-S3 mengirim frame ke `POST /deteksi` dengan `sesi=esp32s3-camera`.
Server menyimpan hasil terbaru beserta rencana segmen suara dari pustaka Ardi;
dashboard React mengambilnya melalui `GET /api/deteksi/latest` lalu memutar
setiap segmen dari `GET /suara/{nama_berkas}`. Untuk itu, jalankan
`python server.py` dan pastikan pustaka tersedia di
`data/runtime/audio/cache_ardi/manifest.json` beserta klip-klipnya. Lokasi
alternatif dapat diatur dengan `VEST_SUARA_FOLDER`.

Suara Ardi diputar oleh browser pada perangkat yang membuka dashboard. Izinkan
audio saat memulai tampilan kamera dan arahkan output browser ke speaker atau
TWS perangkat tersebut. Halaman stream lokal ESP32 (`http://<alamat-esp32>/`)
hanya memiliki suara browser sederhana; ESP32 tidak mengirim audio ke speaker
sendiri dan tidak perlu mengunduh klip suara.
