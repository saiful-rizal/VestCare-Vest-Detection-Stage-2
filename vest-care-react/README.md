# Vest-Care Dashboard (React + Vite + Tailwind)

    npm install
    npm run dev      # http://localhost:5173
    npm run build    # hasil di dist/

- Data: `src/data.js` (contoh) dan `src/useVestData.js` (tempat sambung ke Supabase).
- Profil siswa: objek `profile` di `src/data.js`.
- Foto: `src/assets/img/student.png` dan `avatar.png`.
- Peta & font butuh internet.
- Tombol kamera membuka kamera dan menjalankan deteksi otomatis berkala ke endpoint same-origin `/deteksi`, menampilkan kotak objek serta hasil deteksi; autentikasi memakai cookie sesi HttpOnly dari server.
- Dashboard menampilkan objek yang terdeteksi pada frame terakhir, bukan data deteksi contoh.
- Saat kamera aktif, frame dikirim kira-kira setiap detik. Semua kotak objek yang terdeteksi dan daftar deteksi diperbarui langsung; instruksi suara dari server diputar saat objek atau tingkat peringatan berubah.
- Izinkan akses kamera dan aktifkan suara browser saat membuka kamera. Suara tidak diputar ulang pada setiap frame.
- Jangan menaruh API key di variabel `VITE_*`, karena nilai tersebut dapat dimasukkan ke bundle browser.
