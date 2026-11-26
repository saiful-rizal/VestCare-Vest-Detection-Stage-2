# Vest-Care Dashboard (React + Vite + Tailwind)

    npm install
    npm run dev      # http://localhost:5173
    npm run build    # hasil di dist/

- Data dashboard membaca `devices`, `detections`, dan `gps_log`; deteksi terakhir, urgensi, serta jumlah lima kelas dihitung dari batch deteksi terbaru. Panel riwayat menampilkan 20 objek terbaru dari Supabase, atau dari server saat perangkat belum terlihat.
- `.env.local` pada folder dashboard memakai `NEXT_PUBLIC_SUPABASE_URL` dan `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` untuk membaca data (alias `VITE_*` lama masih didukung). Nilai `NEXT_PUBLIC_*` masuk ke bundle browser; jangan taruh secret/service-role key di sana.
- Halaman login memakai Supabase Auth untuk email/kata sandi, pendaftaran, reset kata sandi, Google OAuth, dan login tamu anonim. Kredensial disimpan di `auth.users`; `profiles.password_hash` tidak digunakan untuk autentikasi. Migrasi `../../supabase/migrations/20261126105000_auth_profile_sync.sql` menghubungkan profil ke akun Auth, membuat profil bagi akun baru, dan menjaga akses tabel perangkat/deteksi melalui RLS.
- Pendaftaran email meminta nama siswa dan menyimpannya bersama email pada `profiles.full_name`; OAuth Google memakai nama akun Google. UUID Supabase menjadi ID akun, dan email unik mencegah satu alamat dipakai untuk beberapa akun.
- Login tamu tidak meminta email atau ID, tetapi Supabase membuat UID anonim; aktifkan Anonymous Sign-Ins di pengaturan Auth Supabase. Sesi tamu tetap memakai dashboard realtime, dengan akses data mengikuti RLS.
- Untuk mengaktifkan Google, buat OAuth Client bertipe Web di Google Cloud Console. Masukkan `https://vestcare-detection-object-production.up.railway.app` dan `http://localhost:5173` sebagai Authorized JavaScript origins, serta `https://ijdhxfogvgyumvgzeyim.supabase.co/auth/v1/callback` sebagai Authorized redirect URI. Isi Client ID dan Client Secret di Supabase Dashboard > Authentication > Sign In / Providers > Google. Pada Authentication > URL Configuration, izinkan URL produksi dan `http://localhost:5173` sebagai redirect URL. Login Google selalu kembali ke URL produksi, termasuk jika dimulai dari localhost. Jangan simpan Client Secret di frontend atau kirim melalui chat.
- Setiap hasil kamera disimpan server secara lokal dan dikirim server ke tabel `detections`. Backend membuat/memperbarui perangkat sementara `VestCare Server` dan mengaitkan setiap objek dengan `device_id` tetap. Objek dalam satu frame memakai timestamp sama agar dapat dikelompokkan sebagai batch. Frame identik dibatasi maksimal sekali tiap 10 detik; perubahan deteksi dikirim langsung.
- Saat server FastAPI mulai, backend otomatis menghubungi Supabase dan membuat/memperbarui perangkat virtual. Status koneksi tersedia di `/status`; bila koneksi startup gagal, server tetap berjalan dan menuliskan penyebabnya ke log.
- Untuk mengaktifkan penulisan, isi `SUPABASE_URL` dan `SUPABASE_SERVICE_ROLE_KEY` di `.env` root (lihat `.env.example`), lalu restart server. Service-role key hanya ada di backend. Pastikan tabel menerima kolom sesuai skema pada database; server akan menampilkan status kegagalan sinkronisasi pada dialog kamera.
- Profil siswa: objek `profile` di `src/data.js`.
- Foto: `src/assets/img/student.png` dan `avatar.png`.
- Peta & font butuh internet.
- Tombol kamera membuka kamera dan menjalankan deteksi otomatis berkala ke endpoint same-origin `/deteksi`, menampilkan kotak objek serta hasil deteksi; autentikasi memakai cookie sesi HttpOnly dari server.
- Dashboard menampilkan objek dari frame terakhir, bukan data deteksi contoh.
- Saat kamera aktif, frame dikirim kira-kira setiap detik. Semua kotak objek yang terdeteksi dan daftar deteksi diperbarui langsung; instruksi suara dari server diputar saat objek atau tingkat peringatan berubah.
- Izinkan akses kamera dan aktifkan suara browser saat membuka kamera. Suara tidak diputar ulang pada setiap frame.
- Untuk kamera ESP32, dashboard memeriksa snapshot terbaru dan hasil deteksi setiap 150 ms; cache ETag mencegah pengunduhan frame yang sama. Status telemetri diperbarui setiap 500 ms dan dianggap online saat telemetri atau frame kamera baru diterima server.
- Suara peringatan mengikuti output audio browser. Pasangkan TWS ke perangkat yang membuka dashboard dan jadikan TWS sebagai speaker utama perangkat.
- Aktifkan RLS dan policy `SELECT` yang sesuai untuk pembacaan browser.
