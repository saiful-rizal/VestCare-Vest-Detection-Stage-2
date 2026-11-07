

import asyncio



import itertools



import json



import os



import shutil



import sys



import tempfile



from pathlib import Path







os.environ.setdefault("SDL_AUDIODRIVER", "dummy")



os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")



sys.path.insert(0, str(Path(__file__).resolve().parent))







import definisi_suara as D



import pemutar_peringatan as P



import teks_bawaan as T







MATI = []



HARAP_SKENARIO = 38



HARAP_KLIP = 104











def d(kelas, level, arah, urgensi=50, jarak=2.0, gerak=None, sumber="kamera"):



return {"kelas": kelas, "level": level, "arah": arah, "urgensi": urgensi, "jarak_m": jarak,



"gerak": gerak, "sumber": sumber}











def uji_tabel_sama():



assert tuple(D.KELAS_GERAK) == tuple(P.KELAS_GERAK)



for m in [0, 0.3, 0.74, 0.75, 1.0, 1.24, 1.25, 1.5, 2.2, 2.75, 3.0, 4.74, 4.75, 5.0, 8.0]:



assert D.bucket_jarak(m) == P.bucket_jarak(m), m



assert D.bucket_jarak(0.5) == 5 and D.bucket_jarak(1.2) == 10 and D.bucket_jarak(2.0) == 20



assert D.bucket_jarak(5.0) == 50 and D.bucket_jarak(9) == 50











def uji_bawaan_valid_dan_lengkap():



sk = D.bangun_skenario()



n_gerak = len(D.KELAS_GERAK) * len(D.ARAH) * 2



assert len(sk) == HARAP_SKENARIO + n_gerak, len(sk)



assert sum(s.jumlah for s in sk.values()) == HARAP_KLIP + n_gerak * 2, sum(s.jumlah for s in sk.values())



for k, s in sk.items():



t = T.teks_bawaan(s)



assert len(t) == s.jumlah, (k, t)











def uji_validasi_menolak_klaim_salah():



sk = D.bangun_skenario()







mobil_bergerak = D.Skenario("x", "benda", "waspada", 3, 10, kelas="mobil", arah="kiri", gerak="bergerak",



kata_benda=D.NAMA_LISAN["mobil"][1])



orang_diam = D.Skenario("y", "benda", "waspada", 3, 10, kelas="orang", arah="kanan", gerak="diam",



kata_benda=D.NAMA_LISAN["orang"][1])



assert D.valid("Ada mobil melaju cepat di sebelah kiri", mobil_bergerak)



assert not D.valid("Ada mobil parkir di sebelah kiri", mobil_bergerak)



assert not D.valid("Ada mobil melaju di kanan", mobil_bergerak)



assert not D.valid("Ada mobil parkir di kiri", sk["benda_mobil_kiri_netral"])



assert not D.valid("Ada mobil di kiri sekitar 2 meter", sk["benda_mobil_kiri_netral"])



assert not D.valid("Ada mobil di depan dan kiri", sk["benda_mobil_kiri_netral"])



assert D.valid("Ada orang berdiri di kanan", orang_diam)



assert D.valid("Berhenti, lalu geser ke kanan.", sk["solusi_berhenti_kanan"])



assert not D.valid("Berhenti, lalu geser ke kiri.", sk["solusi_berhenti_kanan"])



assert not D.valid("Berhenti sekarang.", sk["solusi_berhenti_kanan"])



assert not D.valid("Berhenti, geser ke kiri.", sk["solusi_berhenti"])



assert D.valid("Pelan-pelan, geser ke kiri, lalu lanjut berjalan.", sk["solusi_pelan_kiri"])











def uji_pilih_aksi():



A = P.pilih_aksi







assert A(d("orang", "WASPADA", "kiri"), [d("orang", "WASPADA", "kiri")]) == "pelan_kanan"



assert A(d("mobil", "BAHAYA", "kiri"), [d("mobil", "BAHAYA", "kiri")]) == "berhenti_kanan"



assert A(d("mobil", "INFO", "kiri"), [d("mobil", "INFO", "kiri")]) == "lurus"







assert A(d("mobil", "INFO", "kiri", gerak="bergerak"), [d("mobil", "INFO", "kiri")]) == "lurus"



assert A(d("mobil", "INFO", "kiri", gerak="diam"), [d("mobil", "INFO", "kiri")]) == "lurus"







assert A(d("orang", "WASPADA", "kanan"), [d("orang", "WASPADA", "kanan")]) == "pelan_kiri"







semua = [d("mobil", "BAHAYA", "kiri"), d("pohon", "INFO", "kanan")]



assert A(semua[0], semua) == "berhenti"







assert A(d("pohon", "INFO", "depan"), [d("pohon", "INFO", "depan")]) == "pelan"



assert A(d("lubang", "BAHAYA", "depan"), [d("lubang", "BAHAYA", "depan")]) == "berhenti"



semua = [d("lubang", "BAHAYA", "depan"), d("orang", "INFO", "kiri")]



assert A(semua[0], semua) == "berhenti_kanan"



semua = [d("pohon", "WASPADA", "depan"), d("orang", "INFO", "kanan")]



assert A(semua[0], semua) == "pelan_kiri"



assert A(d("pohon", "WASPADA", "depan"), [d("pohon", "WASPADA", "depan")]) == "pelan_kanan"



assert P.pilih_aksi(d("pohon", "WASPADA", "depan"), [d("pohon", "WASPADA", "depan")], "kiri") == "pelan_kiri"



semua = [d("pohon", "WASPADA", "depan"), d("a", "INFO", "kiri"), d("b", "INFO", "kanan")]



assert A(semua[0], semua) == "pelan"







for lv, ar in itertools.product(("INFO", "WASPADA", "BAHAYA"), ("kiri", "kanan")):



aksi = A(d("x", lv, ar), [d("x", lv, ar)])



assert ar not in aksi.replace("_", " ").split(), (lv, ar, aksi)











class _Waktu:



def __init__(self): self.t = 100.0



def __call__(self): return self.t











def uji_pelacak_gerak():



if not P.KELAS_GERAK:







w = _Waktu()



p = P.PelacakGerak(kecepatan_pengguna_fn=lambda: 1.2, waktu_fn=w)



for j in (6.0, 5.0, 4.0, 3.0, 2.0, 1.0):



w.t += 0.5



daftar = [d("mobil", "INFO", "kiri", jarak=j)]



p.perbarui(daftar)



assert daftar[0]["gerak"] is None



daftar = [d("mobil", "INFO", "kanan", gerak="diam")]



p.perbarui(daftar)



assert daftar[0]["gerak"] == "diam"



return



w = _Waktu()



p = P.PelacakGerak(waktu_fn=w)



hasil = []



for j in (6.0, 5.0, 4.0, 3.0, 2.0):



w.t += 0.5



daftar = [d("mobil", "INFO", "kiri", jarak=j)]



p.perbarui(daftar)



hasil.append(daftar[0]["gerak"])



assert hasil[-1] == "bergerak" and hasil[0] is None, hasil







w2, p2 = _Waktu(), None



p2 = P.PelacakGerak(waktu_fn=w2)



for i in range(6):



w2.t += 0.5



daftar = [d("mobil", "INFO", "kiri", jarak=6.0 - 0.6 * i)]



p2.perbarui(daftar)



assert daftar[0]["gerak"] is None







w3 = _Waktu()



p3 = P.PelacakGerak(kecepatan_pengguna_fn=lambda: 1.2, waktu_fn=w3)



for i in range(10):



w3.t += 0.5



daftar = [d("mobil", "INFO", "kiri", jarak=6.0 - 0.6 * i)]



p3.perbarui(daftar)



assert daftar[0]["gerak"] == "diam", daftar







daftar = [d("pohon", "INFO", "kiri"), d("mobil", "INFO", "kanan", gerak="diam")]



p3.perbarui(daftar)



assert daftar[0]["gerak"] is None and daftar[1]["gerak"] == "diam"











def uji_rencana():



r = P.rencana_peringatan(d("mobil", "BAHAYA", "kiri", jarak=1.2, gerak="bergerak"),



[d("mobil", "BAHAYA", "kiri", jarak=1.2, gerak="bergerak")])



assert r["segmen"] == ["awal_bahaya", "benda_mobil_kiri_netral", "jarak_10", "solusi_berhenti_kanan"], r



r = P.rencana_peringatan(d("pohon", "INFO", "depan", jarak=3.4, gerak="bergerak"), [d("pohon", "INFO", "depan")])



assert r["segmen"] == ["benda_pohon_depan_netral", "jarak_35", "solusi_pelan"], r



r = P.rencana_peringatan(d("tiang", "WASPADA", "depan"), [d("tiang", "WASPADA", "depan")], ["mobil", "umum"])



assert r["segmen"][1] == "benda_umum_depan_netral"



assert P.rencana_peringatan(d("mobil", "AMAN", "kiri"), []) is None











def uji_tangga_jarak():



w = _Waktu()



tg = P.TanggaJarak(waktu_fn=w)



assert [tg.tahap(j) for j in (6.0, 5.0, 4.0, 3.5, 3.0, 2.5, 1.6, 1.5, 0.3)] == [0, 1, 1, 2, 2, 3, 3, 4, 4]







def frame(j, kelas="mobil", arah="kiri", level="AMAN", **kw):



w.t += 0.3



masuk = [d(kelas, level, arah, urgensi=5, jarak=j, **kw)]



keluar = tg.terapkan(masuk)



assert masuk[0]["level"] == level and "tahap" not in masuk[0]



return keluar[0]











e = frame(4.8)



assert e["level"] == "INFO" and e["tahap_baru"] and tg.boleh_bicara(e) and e["level_asli"] == "AMAN"







e = frame(4.6)



assert e["tahap_baru"]



tg.tandai(e)







for j in (4.4, 4.0, 3.6):



e = frame(j)



assert not e["tahap_baru"] and not tg.boleh_bicara(e), j



e = frame(3.4)



assert e["tahap_baru"] and e["level"] == "WASPADA"



tg.tandai(e)



e = frame(1.4)



assert e["tahap"] == 4 and e["tahap_baru"] and e["level"] == "BAHAYA"



tg.tandai(e)



assert not frame(1.3)["tahap_baru"]







for j in (2.0, 3.0, 3.3):



frame(j)



e = frame(1.4)



assert e["tahap_baru"], "setelah menjauh lalu mendekat lagi harus diingatkan lagi"







tg2 = P.TanggaJarak(waktu_fn=w)



e = tg2.terapkan([d("mobil", "AMAN", "kiri", jarak=1.2, gerak="diam")])[0]



assert e["level"] == "BAHAYA", e







tg2.tandai(tg2.terapkan([d("mobil", "BAHAYA", "depan", jarak=1.0, gerak="diam")])[0])



e = tg2.terapkan([d("mobil", "BAHAYA", "depan", jarak=0.9, gerak="diam")])[0]



assert e["level"] == "BAHAYA" and not e["tahap_baru"] and tg2.boleh_bicara(e)







e = tg2.terapkan([d("pohon", "AMAN", "kiri", jarak=1.0)])[0]



assert "tahap" not in e and tg2.boleh_bicara(e)



e = tg2.terapkan([d("mobil", "AMAN", "kiri", jarak=1.0, sumber="ingatan")])[0]



assert "tahap" not in e







tg3 = P.TanggaJarak(waktu_fn=w)



tg3.tandai(tg3.terapkan([d("motor", "AMAN", "kanan", jarak=2.0)])[0])



w.t += P.UMUR_TANGGA_S + 0.5



assert tg3.terapkan([d("motor", "AMAN", "kanan", jarak=2.0)])[0]["tahap_baru"]











def _tts_palsu():



from pydub import AudioSegment



from pydub.generators import Sine







async def sintesis(teks, suara, prosodi, percobaan=3):



return (AudioSegment.silent(200) + Sine(440).to_audio_segment(duration=30 * len(teks)).apply_gain(-10)



+ AudioSegment.silent(300))



return sintesis











def _bangun(folder, mode):



import siapkan_pustaka as S



import suara_natural as SN



SN.sintesis_segmen = _tts_palsu()



if mode == "llm":



sk = D.bangun_skenario()



panggilan = {"n": 0}







def llm_palsu(sistem, pengguna, penyedia=None, maks_token=2000):



panggilan["n"] += 1



data = json.loads(pengguna)



keluar = {}



for k, v in data.items():



bagus = T.teks_bawaan(sk[k])



salah = ["Ada mobil parkir dan melaju di depan 3 meter", "Berhenti, lalu geser ke kiri dan kanan"]



keluar[k] = salah + bagus



if panggilan["n"] == 1:



raise RuntimeError("HTTP 503")



return json.dumps(keluar)



S.minta_teks = llm_palsu



S.time.sleep = lambda x: None



asyncio.run(S.siapkan_pustaka(Path(folder), "id-ID-ArdiNeural", 3, False, 1, "wav", 22050))



else:



asyncio.run(S.siapkan_pustaka(Path(folder), "id-ID-ArdiNeural", 3, False, 1, "wav", 22050, None, None, True))



return S











def uji_pustaka_dan_pemutar():



try:



import pygame, pydub



except ImportError:



print("  (pygame/pydub tidak terpasang; uji pustaka dan pemutar dilewati)")



return



tmp = Path(tempfile.mkdtemp())



try:







S = _bangun(tmp / "llm", "llm")



_bangun(tmp / "bawaan", "bawaan")



for nama in ("llm", "bawaan"):



m = json.loads((tmp / nama / "manifest.json").read_text(encoding="utf-8"))



assert m["skema"] == 3 and len(m["pesan"]) == HARAP_SKENARIO and

sum(len(v) for v in m["pesan"].values()) == HARAP_KLIP



sk = D.bangun_skenario()



for k, ent in m["pesan"].items():



for e in ent:



assert D.valid(e["teks"], sk[k]) or sk[k].jenis in ("awal", "jarak"), (k, e["teks"])



assert S.periksa(tmp / nama)







from pydub import AudioSegment



klip = AudioSegment.from_file(tmp / "llm" / "jarak_20_1.wav")



assert len(klip) < 30 * len("sekitar dua meter,") + 150, len(klip)











kunci = set(m["pesan"])



for kelas, level, arah, gerak, jarak in itertools.product(



list(D.BAHAYA_KELAS) + ["tiang"], ("INFO", "WASPADA", "BAHAYA"), D.ARAH,



(None, "bergerak", "diam"), (0.1, 0.8, 1.3, 2.2, 3.9, 5.0)):



for lain in ([], [d("a", "INFO", "kiri")], [d("a", "INFO", "kanan")],



[d("a", "INFO", "kiri"), d("b", "WASPADA", "kanan")]):



top = d(kelas, level, arah, jarak=jarak, gerak=gerak)



r = P.rencana_peringatan(top, [top] + lain, list(D.BAHAYA_KELAS) + ["umum"])



hilang = [k for k in r["segmen"] if k not in kunci]



assert not hilang, (kelas, level, arah, gerak, jarak, hilang)











pem = P.PemutarPeringatan(str(tmp / "bawaan"), seed=1)



daftar = [d("mobil", "BAHAYA", "kiri", 90, 1.2, "bergerak")]



teks = pem.umumkan_analisis(daftar)



assert teks and "mobil" in teks.lower(), teks



assert "meter" in teks, teks



assert pem.umumkan_analisis(daftar) is None



pem.berhenti()



assert pem.umumkan_analisis(daftar) is None







pem2 = P.PemutarPeringatan(str(tmp / "bawaan"), seed=2)



assert pem2.umumkan_analisis([d("orang", "INFO", "kiri", 30, 3.0, "diam")])



assert pem2.sedang_berbunyi()



assert pem2.umumkan_analisis([d("orang", "INFO", "kanan", 30, 3.0)]) is None



teks = pem2.umumkan_analisis([d("lubang", "BAHAYA", "depan", 95, 0.6)])



assert teks and "lubang" in teks and "kurang dari satu meter" in teks, teks







r = pem2.susun_peringatan([d("lubang", "BAHAYA", "depan", 95, 0.6)])



_, snd, dur = pem2._rakit(r["segmen"])



assert 0.5 < dur < 20 and abs(snd.get_length() - dur) < 0.05, (dur, snd.get_length())







pem4 = P.PemutarPeringatan(str(tmp / "bawaan"), seed=4)



berbunyi = {}



for j in (5.0, 4.6, 4.2, 3.8, 3.4, 3.0, 2.6, 2.4, 2.0, 1.6, 1.4, 1.2, 1.0):



pem4.berhenti()



berbunyi[j] = pem4.umumkan_analisis([d("mobil", "AMAN", "kiri", 5, j)])



yang_bicara = [j for j, t in berbunyi.items() if t]



assert yang_bicara == [5.0, 3.4, 2.4, 1.4], yang_bicara



assert "meter" in berbunyi[5.0] and "kurang" not in berbunyi[1.4]







pem5 = P.PemutarPeringatan(str(tmp / "bawaan"), seed=5, tangga=False)



assert pem5.umumkan_analisis([d("mobil", "AMAN", "kiri", 5, 4.0)]) is None







pem6 = P.PemutarPeringatan(str(tmp / "bawaan"), seed=6)



assert pem6.umumkan_analisis([d("lubang", "BAHAYA", "depan", 95, 1.0)])



assert pem6.umumkan_analisis([d("mobil", "AMAN", "kiri", 5, 4.0)]) is None



pem6.berhenti()



assert pem6.umumkan_analisis([d("mobil", "AMAN", "kiri", 5, 3.9)])







pem7 = P.PemutarPeringatan(str(tmp / "bawaan"), seed=7)



pem7.umumkan_analisis([d("mobil", "AMAN", "kiri", 5, 4.0)])



pem7.berhenti()



assert pem7.umumkan_analisis([d("mobil", "AMAN", "kiri", 5, 4.0)]) is None



assert pem7._aman_sejak is None







pem3 = P.PemutarPeringatan(str(tmp / "bawaan"), seed=3)



assert pem3.umumkan_analisis([]) is None



pem3.umumkan_analisis([d("pohon", "INFO", "depan", 30, 3.0)])



pem3.berhenti()



assert pem3.umumkan_analisis([]) is None



pem3._aman_sejak -= P.JEDA_AMAN_S + 0.1



assert pem3.umumkan_analisis([]) and not pem3._perlu_aman



assert pem3.umumkan_analisis([]) is None







(tmp / "aneh").mkdir()



(tmp / "aneh" / "manifest.json").write_text(json.dumps({"skema": 1, "pesan": {}}))



try:



P.PemutarPeringatan(str(tmp / "aneh"))



raise AssertionError("seharusnya ditolak")



except SystemExit as e:



assert "paksa" in str(e)







(tmp / "lama").mkdir()



(tmp / "lama" / "bahaya_motor_depan_1.wav").write_bytes(b"x")



(tmp / "lama" / "manifest.json").write_text(json.dumps(



{"skema": 2, "pesan": {"bahaya_motor_depan": [{"teks": "x", "berkas": "bahaya_motor_depan_1.wav"}]}}))



_bangun(tmp / "lama", "bawaan")



assert json.loads((tmp / "lama" / "manifest.json").read_text())["skema"] == 3



assert not (tmp / "lama" / "bahaya_motor_depan_1.wav").exists()



finally:



shutil.rmtree(tmp, ignore_errors=True)











if __name__ == "__main__":



for nama, fn in list(globals().items()):



if nama.startswith("uji_") and callable(fn):



fn()



print(f"lulus  {nama}")



print("\nSemua uji lulus.")