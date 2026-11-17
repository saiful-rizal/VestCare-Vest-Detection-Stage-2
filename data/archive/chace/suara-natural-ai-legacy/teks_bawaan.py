

from __future__ import annotations







from definisi_suara import (BUCKET_JARAK, KUNCI_AMAN, NAMA_LISAN, Skenario, bersihkan_akhir, valid)







AWALAN = {



"awal_waspada": ["Hati-hati.", "Waspada.", "Perhatian."],



"awal_bahaya": ["Awas!", "Bahaya!", "Awas, hati-hati!"],



}



KATA_ANGKA = {5: "kurang dari satu", 10: "satu", 15: "satu setengah", 20: "dua", 25: "dua setengah",



30: "tiga", 35: "tiga setengah", 40: "empat", 45: "empat setengah", 50: "lima"}











def kalimat_jarak(n: int) -> list[str]:



if n == 5:



return ["kurang dari satu meter", "jaraknya kurang dari satu meter"]



return [f"sekitar {KATA_ANGKA[n]} meter", f"kira-kira {KATA_ANGKA[n]} meter"]











def _arah(a: str) -> tuple[str, str]:



return {"depan": ("di depan", "di depan"), "kiri": ("di sebelah kiri", "di kiri"),



"kanan": ("di sebelah kanan", "di kanan")}[a]











def kalimat_benda(kelas: str, arah: str, gerak: str) -> list[str]:



b = NAMA_LISAN.get(kelas, (kelas, None))[0]



panjang, pendek = _arah(arah)



kapital = b[0].upper() + b[1:]



kendaraan = kelas in ("mobil", "motor")



if gerak == "bergerak":



if kendaraan:



return [f"Ada {b} melaju cepat {panjang}", f"{kapital} bergerak {pendek}",



f"Ada {b} melintas {pendek}"]



return [f"Ada orang berjalan {panjang}", f"Orang bergerak {pendek}", f"Ada orang melintas {pendek}"]



if gerak == "diam":



if kendaraan:



return [f"Ada {b} parkir {panjang}", f"{kapital} terparkir {pendek}",



f"Ada {b} diam {pendek}"]



return [f"Ada orang berdiri {panjang}", f"Orang berdiri diam {pendek}", f"Ada orang diam {pendek}"]



return [f"Ada {b} {panjang}", f"Di {arah} ada {b}", f"{kapital} {pendek}"]











SOLUSI = {



"lurus": ["Silakan lanjut berjalan.", "Tetap lurus, lanjut berjalan.", "Jalan lurus saja, terus berjalan."],



"pelan": ["Berjalanlah pelan-pelan.", "Kurangi kecepatan.", "Jalan perlahan ya."],



"berhenti": ["Berhenti sekarang.", "Segera berhenti.", "Stop, berhenti dulu."],



"pelan_kiri": ["Pelan-pelan, geser ke kiri, lalu lanjut berjalan.",



"Silakan geser ke kiri perlahan, lalu berjalan.", "Kurangi kecepatan, menepi ke kiri."],



"pelan_kanan": ["Pelan-pelan, geser ke kanan, lalu lanjut berjalan.",



"Silakan geser ke kanan perlahan, lalu berjalan.", "Kurangi kecepatan, menepi ke kanan."],



"berhenti_kiri": ["Berhenti, lalu geser ke kiri.", "Stop, setelah itu menepi ke kiri.",



"Berhenti dulu, kemudian geser ke kiri."],



"berhenti_kanan": ["Berhenti, lalu geser ke kanan.", "Stop, setelah itu menepi ke kanan.",



"Berhenti dulu, kemudian geser ke kanan."],



}



AMAN = ["Jalur sudah aman, silakan lanjut berjalan.", "Aman di depan, silakan terus berjalan.",



"Jalur bebas di depan, Anda bisa berjalan."]











def teks_bawaan(s: Skenario) -> list[str]:







if s.jenis == "awal":



daftar = AWALAN[s.kunci]



elif s.jenis == "jarak":



daftar = kalimat_jarak(int(s.kunci.split("_")[1]))



elif s.jenis == "benda":



daftar = kalimat_benda(s.kelas, s.arah, s.gerak)



elif s.jenis == "solusi":



daftar = SOLUSI[s.aksi]



else:



daftar = AMAN



unik, terlihat = [], set()



for t in daftar:



if t.lower() not in terlihat and valid(t, s):



terlihat.add(t.lower())



unik.append(t)



return unik[:s.jumlah]











def hanya_bawaan(s: Skenario) -> bool:







return s.jenis in ("awal", "jarak")
