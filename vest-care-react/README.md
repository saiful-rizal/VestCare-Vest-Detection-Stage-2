# Vest-Care Dashboard (React + Vite + Tailwind)

    npm install
    npm run dev      # http://localhost:5173
    npm run build    # hasil di dist/

- Data dashboard membaca `devices`, `detections`, dan `gps_log`; deteksi terakhir, urgensi, serta jumlah lima kelas dihitung dari batch deteksi terbaru. Panel riwayat menampilkan 20 objek terbaru dari Supabase, atau dari server saat perangkat belum terlihat.
- `.env.local` pada folder dashboard memakai `NEXT_PUBLIC_SUPABASE_URL` dan `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` untuk membaca data (alias `VITE_*` lama masih didukung). Nilai `NEXT_PUBLIC_*` masuk ke bundle browser; jangan taruh secret/service-role key di sana.
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
- Aktifkan RLS dan policy `SELECT` yang sesuai untuk pembacaan browser.
