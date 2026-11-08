# Vest-Care Dashboard (React + Vite + Tailwind)

    npm install
    npm run dev      # http://localhost:5173
    npm run build    # hasil di dist/

- Data dashboard dibaca dari tabel Supabase `devices`, `detections`, dan `gps_log` melalui `src/useVestData.js`.
- Atur `VITE_SUPABASE_URL` dan `VITE_SUPABASE_ANON_KEY` di `.env.local` pada folder ini. Gunakan publishable/anon key, aktifkan RLS, dan buat policy baca yang sesuai; jangan gunakan `service_role` key di browser.
- Hasil kamera dikirim ke tabel `detections` untuk perangkat terbaru yang dapat dibaca oleh dashboard. Saat kamera live, data yang sama disimpan maksimal sekali tiap 10 detik; perubahan objek atau level urgensi disimpan langsung. Kebijakan RLS juga harus mengizinkan `INSERT`; deteksi yang gagal disimpan akan menampilkan pesan pada dialog kamera.
- Profil siswa: objek `profile` di `src/data.js`.
- Foto: `src/assets/img/student.png` dan `avatar.png`.
- Peta & font butuh internet.
- Tombol kamera membuka kamera dan menjalankan deteksi otomatis berkala ke endpoint same-origin `/deteksi`, menampilkan kotak objek serta hasil deteksi; autentikasi memakai cookie sesi HttpOnly dari server.
- Dashboard menampilkan objek yang terdeteksi pada frame terakhir, bukan data deteksi contoh.
- Saat kamera aktif, frame dikirim kira-kira setiap detik. Semua kotak objek yang terdeteksi dan daftar deteksi diperbarui langsung; instruksi suara dari server diputar saat objek atau tingkat peringatan berubah.
- Izinkan akses kamera dan aktifkan suara browser saat membuka kamera. Suara tidak diputar ulang pada setiap frame.
- Jangan menaruh API key di variabel `VITE_*`, karena nilai tersebut dapat dimasukkan ke bundle browser.
