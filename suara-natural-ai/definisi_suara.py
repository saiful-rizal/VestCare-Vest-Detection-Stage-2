

from __future__ import annotations







import re



from dataclasses import dataclass



from typing import Optional







from fuzzysugeno import BAHAYA_KELAS







SKEMA = 3



ARAH = ("depan", "kiri", "kanan")



TINGKAT = ("info", "waspada", "bahaya")



GERAK = ("netral", "bergerak", "diam")



KELAS_GERAK = ()



AKSI = ("lurus", "pelan", "berhenti", "pelan_kiri", "pelan_kanan", "berhenti_kiri", "berhenti_kanan")



BUCKET_JARAK = tuple(range(5, 55, 5))



KUNCI_AMAN = "jalur_aman"







NAMA_LISAN: dict[str, tuple[str, frozenset]] = {



"lubang": ("lubang", frozenset({"lubang"})),



"motor":  ("sepeda motor", frozenset({"motor"})),



"mobil":  ("mobil", frozenset({"mobil", "kendaraan"})),



"orang":  ("orang", frozenset({"orang", "seseorang", "pejalan"})),



"pohon":  ("pohon", frozenset({"pohon"})),



"umum":   ("rintangan", frozenset({"rintangan", "benda", "halangan"})),



}



DESKRIPSI_ARAH = {"depan": "tepat di depan pengguna", "kiri": "di sisi kiri pengguna",



"kanan": "di sisi kanan pengguna"}











KATA_BERGERAK = frozenset({"melaju", "bergerak", "melintas", "melintasi", "mendekat", "berjalan", "lewat", "cepat"})



KATA_DIAM = frozenset({"parkir", "terparkir", "diam", "berdiri", "berhenti"})



KATA_PELAN = frozenset({"pelan", "perlahan", "lambat", "kurangi"})



KATA_GESER = frozenset({"geser", "bergeser", "menepi", "belok", "pindah", "menghindar", "minggir"})



KATA_BERHENTI = frozenset({"berhenti", "stop"})



KATA_LURUS = frozenset({"lurus", "lanjut", "terus"})







KATA_AKSI = {



"lurus": ((KATA_LURUS,), None),



"pelan": ((KATA_PELAN,), None),



"berhenti": ((KATA_BERHENTI,), None),



"pelan_kiri": ((KATA_PELAN, KATA_GESER), "kiri"),



"pelan_kanan": ((KATA_PELAN, KATA_GESER), "kanan"),



"berhenti_kiri": ((KATA_BERHENTI, KATA_GESER), "kiri"),



"berhenti_kanan": ((KATA_BERHENTI, KATA_GESER), "kanan"),



}



DESKRIPSI_AKSI = {



"lurus": "Jalur aman; pengguna boleh melanjutkan berjalan lurus. Jangan menyebut kiri atau kanan.",



"pelan": "Pengguna berjalan lebih pelan dan berhati-hati. Jangan menyebut kiri atau kanan.",



"berhenti": "Pengguna harus berhenti sekarang. Jangan menyebut kiri atau kanan.",



"pelan_kiri": "Pengguna berjalan pelan, bergeser ke KIRI, lalu melanjutkan berjalan. Sebut kata kiri.",



"pelan_kanan": "Pengguna berjalan pelan, bergeser ke KANAN, lalu melanjutkan berjalan. Sebut kata kanan.",



"berhenti_kiri": "Pengguna berhenti dahulu, lalu bergeser ke KIRI. Sebut kata kiri.",



"berhenti_kanan": "Pengguna berhenti dahulu, lalu bergeser ke KANAN. Sebut kata kanan.",



}











@dataclass(frozen=True)



class Tingkat:



emosi: str



prioritas: int



cooldown: float



mendesak: bool











PENGATURAN_TINGKAT: dict[str, Tingkat] = {



"info": Tingkat("ramah", 2, 5.0, False),



"waspada": Tingkat("waspada", 3, 3.5, False),



"bahaya": Tingkat("darurat", 5, 2.0, True),



}











@dataclass(frozen=True)



class Skenario:



kunci: str



jenis: str



emosi: str



jumlah: int



maks_kata: int



deskripsi: str = ""



kelas: str = ""



arah: str = ""



gerak: str = ""



aksi: str = ""



kata_benda: frozenset = frozenset()











def daftar_kelas() -> list[str]:



return list(BAHAYA_KELAS) + ["umum"]











def kunci_awal(tingkat: str) -> str: return f"awal_{tingkat}"



def kunci_benda(kelas: str, arah: str, gerak: str) -> str: return f"benda_{kelas}_{arah}_{gerak}"



def kunci_jarak(n: int) -> str: return f"jarak_{n:02d}"



def kunci_solusi(aksi: str) -> str: return f"solusi_{aksi}"











def bucket_jarak(meter: float) -> int:







if meter < 0.75:



return 5



return min(50, int(meter * 2 + 0.5) * 5)











def bangun_skenario(jumlah: int = 3) -> dict[str, Skenario]:



sk: dict[str, Skenario] = {}



for t in ("waspada", "bahaya"):



sk[kunci_awal(t)] = Skenario(kunci_awal(t), "awal", PENGATURAN_TINGKAT[t].emosi, jumlah, 4)



for kelas in daftar_kelas():



nama, kata = NAMA_LISAN.get(kelas, (kelas, frozenset({kelas.lower()})))



for arah in ARAH:



for gerak in (GERAK if kelas in KELAS_GERAK else ("netral",)):



n = jumlah if gerak == "netral" else max(1, jumlah - 1)



k = kunci_benda(kelas, arah, gerak)



sk[k] = Skenario(k, "benda", "waspada", n, 10, f"{nama} {DESKRIPSI_ARAH[arah]}",



kelas=kelas, arah=arah, gerak=gerak, kata_benda=kata)



for n in BUCKET_JARAK:



k = kunci_jarak(n)



sk[k] = Skenario(k, "jarak", "waspada", min(jumlah, 2), 6)



for aksi in AKSI:



k = kunci_solusi(aksi)



emosi = "darurat" if aksi.startswith("berhenti") else "waspada" if aksi.startswith("pelan") else "tenang"



sk[k] = Skenario(k, "solusi", emosi, jumlah, 10, DESKRIPSI_AKSI[aksi], aksi=aksi)



sk[KUNCI_AMAN] = Skenario(KUNCI_AMAN, "aman", "tenang", jumlah, 10,



"Jalur di depan sudah bebas rintangan; pengguna boleh melanjutkan berjalan.")



return sk











def _kata(teks: str) -> list[str]:



return re.findall(r"[\w-]+", teks.lower())











def valid(teks: str, s: Skenario) -> bool:







kata = _kata(teks)



rendah = teks.lower()



if not kata or len(kata) > s.maks_kata or re.search(r"\d", rendah):



return False







def ada(grup) -> bool:



return any(k in tok for tok in kata for k in grup)







if s.jenis == "benda":



if not any(k in rendah for k in s.kata_benda) or s.arah not in kata:



return False



if any(a in kata for a in ARAH if a != s.arah):



return False



b, d = ada(KATA_BERGERAK), ada(KATA_DIAM)



if s.gerak == "bergerak":



return b and not d



if s.gerak == "diam":



return d and not b



return not b and not d



if s.jenis == "solusi":



grup, sisi = KATA_AKSI[s.aksi]



if not all(ada(g) for g in grup):



return False



lain = {"kiri", "kanan"} - ({sisi} if sisi else set())



if any(x in kata for x in lain) or (sisi and sisi not in kata):



return False



if sisi is None and ada(KATA_GESER):



return False



return True











def tekanan_sambung(s: Skenario) -> bool:







return s.jenis in ("benda", "jarak")











def bersihkan_akhir(teks: str) -> str:



return teks.strip().rstrip(".!?,;: ")