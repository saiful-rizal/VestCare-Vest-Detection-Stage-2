


import sys



import time







import numpy as np







from fuzzysugeno import analisis_hasil



from pemutar_peringatan import PelacakGerak, PemutarPeringatan







LEBAR, TINGGI = 640, 480



KELAS = {"lubang": 0, "motor": 1, "mobil": 2, "orang": 3, "pohon": 4}











class _Box:



def __init__(self, kelas, xyxy):



self.cls, self.conf, self.xyxy = KELAS[kelas], 0.9, np.array([xyxy], dtype=float)











class _Res:



names = {v: k for k, v in KELAS.items()}



orig_shape = (TINGGI, LEBAR)



masks = None







def __init__(self, *kotak):



self.boxes = list(kotak) if kotak else None











KIRI, DEPAN, KANAN = [40, 150, 150, 330], [280, 150, 360, 330], [490, 150, 600, 330]











def main() -> None:



folder = sys.argv[1] if len(sys.argv) > 1 else "cache_suara"



pemutar = PemutarPeringatan(folder)



pelacak = PelacakGerak()







def frame(res, jarak):



daftar = analisis_hasil(res, jarak_fn=lambda box, nama: jarak)



pelacak.perbarui(daftar)



teks = pemutar.umumkan_analisis(daftar)



ringkas = ", ".join(f"{d['kelas']} {d['arah']} {d['level']} {d['jarak_m']:.1f} m"



f"{' ' + d['gerak'] if d.get('gerak') else ''}" for d in daftar) or "kosong"



print(f"{ringkas:<52} -> {teks if teks else '-'}")







print("1) Pohon di depan, jauh")



frame(_Res(_Box("pohon", DEPAN)), 4.2)



time.sleep(1.5)



print("2) Mobil mendekat cepat dari kiri (pelacak membaca perubahan jarak antar frame)")



for j in (5.0, 4.0, 3.0, 2.2, 1.5, 1.2):



frame(_Res(_Box("mobil", KIRI)), j)



time.sleep(0.3)



pemutar.tunggu_selesai()



print("3) Lubang tepat di depan")



frame(_Res(_Box("lubang", DEPAN)), 1.0)



pemutar.tunggu_selesai()



print("4) Semua bersih")



for _ in range(25):



frame(_Res(), 0)



time.sleep(0.1)



pemutar.tunggu_selesai()











if __name__ == "__main__":



main()
