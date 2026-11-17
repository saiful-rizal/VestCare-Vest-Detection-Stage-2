import numpy as np

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import fuzzysugeno as F






LEBAR, TINGGI = 640, 480











class _Box:



    def __init__(self, kelas_id, conf, xyxy):



        self.cls, self.conf, self.xyxy = kelas_id, conf, np.array([xyxy], dtype=float)











class _Res:

    names = {**F.KELAS_ID_KE_NAMA, **F.KELAS_INTERNAL_MODEL}



    orig_shape = (TINGGI, LEBAR)



    masks = None







    def __init__(self, *deteksi):



        self.boxes = list(deteksi) if deteksi else None











def ada(daftar, kelas=None, level=None, sumber=None):



    return [d for d in daftar if (kelas is None or d["kelas"] == kelas) and (level is None or d["level"] == level)



    and (sumber is None or d["sumber"] == sumber)]











def uji_kompatibel_pemanggilan_lama():



    res = _Res(_Box(0, 0.9, [280, 150, 360, 330]))



    daftar = F.analisis_hasil(res, lambda box, nama: 2.0)



    assert len(daftar) == 1 and daftar[0]["kelas"] == "pohon" and daftar[0]["arah"] == "depan"



    for kunci in ("kelas", "level", "arah", "urgensi", "jarak_m", "jalur", "pesan"):



        assert kunci in daftar[0], kunci



    assert daftar[0]["level"] in ("INFO", "WASPADA", "BAHAYA")











def uji_fusi_ultrasonik():







    res = _Res(_Box(0, 0.9, [280, 150, 360, 330]))



    d = F.analisis_hasil(res, lambda b, n: 4.0, jarak_us=1.0)[0]



    assert d["jarak_m"] == 1.0 and d["sumber"] == "kamera+ultrasonik" and d["level"] == "BAHAYA", d







    res = _Res(_Box(2, 0.9, [20, 150, 120, 330]))



    daftar = F.analisis_hasil(res, lambda b, n: 3.0, jarak_us=0.5)



    d = ada(daftar, "motor")[0]



    assert d["arah"] == "kiri" and d["jarak_m"] == 3.0 and d["sumber"] == "kamera", d







    assert ada(daftar, "umum", "BAHAYA", "ultrasonik"), daftar











def uji_batas_kamera():







    res = _Res(_Box(3, 0.9, [260, 100, 380, 480]))



    d = F.analisis_hasil(res, lambda b, n: 4.0)[0]



    assert d["jarak_m"] <= F.KAMERA_MIN_M, d







    res = _Res(_Box(3, 0.9, [280, 150, 360, 330]))



    assert F.analisis_hasil(res, lambda b, n: 9.0)[0]["jarak_m"] == F.KAMERA_MAKS_M







    assert abs(F.estimasi_jarak_kamera([0, 0, 1, TINGGI], TINGGI) - F.KAMERA_MIN_M) < 0.05



    assert F.estimasi_jarak_kamera([0, 0, 1, TINGGI / 2], TINGGI) > 4.0



    assert F.estimasi_jarak_kamera([0, 0, 1, 20], TINGGI) is None







    res = _Res(_Box(4, 0.9, [270, 300, 370, 400]))



    d = F.analisis_hasil(res)[0]



    assert d["sumber"] == "kamera" and 1.5 < d["jarak_m"] < 3.5, d











def uji_penjaga_ultrasonik():



    kosong = _Res()



    assert F.analisis_hasil(kosong) == []



    d = F.analisis_hasil(kosong, jarak_us=0.6)



    assert len(d) == 1 and d[0]["kelas"] == "umum" and d[0]["level"] == "BAHAYA" and d[0]["sumber"] == "ultrasonik", d



    assert F.analisis_hasil(kosong, jarak_us=3.5) == []



    assert F.analisis_hasil(kosong, jarak_us=0.0) == []



    assert F.analisis_hasil(kosong, jarak_us=None) == []



    assert F.analisis_hasil(kosong, jarak_us="rusak") == []







    res = _Res(_Box(0, 0.9, [280, 150, 360, 330]))



    assert not ada(F.analisis_hasil(res, lambda b, n: 2.0, jarak_us=0.6), kelas="umum")











def uji_ingatan_lubang():



    jam = [0.0]



    ingatan = F.IngatanHalangan(waktu_fn=lambda: jam[0])







    res = _Res(_Box(4, 0.9, [270, 380, 370, 470]))



    d = F.analisis_hasil(res, lambda b, n: 1.6, ingatan=ingatan)



    assert ada(d, "lubang", sumber="kamera"), d







    jam[0] = 0.5



    d = F.analisis_hasil(_Res(), ingatan=ingatan)



    assert len(d) == 1 and d[0]["sumber"] == "ingatan" and abs(d[0]["jarak_m"] - 1.0) < 0.05, d



    assert d[0]["level"] != "AMAN"



    jam[0] = 1.0



    d = F.analisis_hasil(_Res(), ingatan=ingatan)



    assert len(d) == 1 and abs(d[0]["jarak_m"] - 0.4) < 0.05 and d[0]["level"] == "BAHAYA", d







    jam[0] = 1.2



    assert F.analisis_hasil(_Res(), ingatan=ingatan) == []







    ing2 = F.IngatanHalangan(kecepatan=0.0, waktu_fn=lambda: jam[0])



    jam[0] = 10.0



    F.analisis_hasil(res, lambda b, n: 1.6, ingatan=ing2)



    jam[0] = 11.0



    assert len(F.analisis_hasil(_Res(), ingatan=ing2)) == 1



    jam[0] = 13.0



    assert F.analisis_hasil(_Res(), ingatan=ing2) == []







    ing3 = F.IngatanHalangan(waktu_fn=lambda: jam[0])



    F.analisis_hasil(_Res(_Box(3, 0.9, [260, 100, 380, 460])), lambda b, n: 1.2, ingatan=ing3)



    assert F.analisis_hasil(_Res(), ingatan=ing3) == []











def uji_koridor():



    lebar = lambda j: F.koridor_untuk_jarak(j)[1] - F.koridor_untuk_jarak(j)[0]



    assert lebar(0.6) > lebar(1.5) > lebar(3.0) > lebar(5.0) > 0.1



    k = F.koridor_untuk_jarak(2.0)



    assert abs((k[0] + k[1]) / 2 - 0.5) < 1e-9


def uji_ingatan_dihapus_saat_bahaya_berakhir():
    jam = [0.0]
    ingatan = F.IngatanHalangan(kecepatan=0.0, waktu_fn=lambda: jam[0])
    bahaya = {
        "kelas": "lubang",
        "arah": "depan",
        "level": "BAHAYA",
        "sumber": "kamera",
        "ragu": False,
        "jarak_m": 1.0,
        "bahaya": 10,
        "jalur": 1.0,
        "conf": 0.9,
    }

    assert ingatan.perbarui([bahaya]) == [bahaya]
    jam[0] = 0.5
    aman = {**bahaya, "level": "AMAN", "jarak_m": 3.0}
    assert ingatan.perbarui([aman]) == [aman]
    jam[0] = 1.0
    assert ingatan.perbarui([]) == []











def uji_aturan():







    assert F.level(F.sugeno(0.5, 10, 0.0)) == "INFO"







    assert F.level(F.sugeno(4.5, 10, 0.0)) == "AMAN"







    for bahaya in (6, 10):



        nilai = [F.sugeno(j, bahaya, 1.0) for j in np.arange(0.2, 6.0, 0.1)]



        assert all(a >= b - 1e-9 for a, b in zip(nilai, nilai[1:])), bahaya







    for j in np.arange(0.0, 8.0, 0.05):



        for b in (0, 3, 5, 6, 8, 10):



            for p in np.arange(0.0, 1.01, 0.05):



                mu = F.fuzzifikasi(j, b, p)



                den = sum(min(mu["jarak"][a] if a else 1, mu["bahaya"][c] if c else 1, mu["jalur"][e] if e else 1)



                for a, c, e, _ in F.ATURAN)



                assert den > 1e-6, (j, b, p)











                def uji_cocok_pemutar():



                    try:



                        from pemutar_peringatan import kunci_dari_analisis



                    except ImportError:



                        print("  (pemutar_peringatan.py tidak ada di folder ini, uji kecocokan dilewati)")



                        return



                    kelas_dikenal = list(F.BAHAYA_KELAS) + ["umum"]



                    res = _Res(_Box(5, 0.9, [280, 150, 360, 330]))



                    d = F.analisis_hasil(res, lambda b, n: 1.0)[0]



                    assert kunci_dari_analisis(d, kelas_dikenal) == "bahaya_umum_depan", kunci_dari_analisis(d, kelas_dikenal)



                    d = F.analisis_hasil(_Res(), jarak_us=0.5)[0]



                    assert kunci_dari_analisis(d, kelas_dikenal) == "bahaya_umum_depan"











def uji_kelas_penunjang_dan_ambang_per_kelas():
    assert F.validasi_nama_kelas(_Res.names) == _Res.names

    sasaran = _Box(0, 0.65, [280, 150, 360, 330])
    penunjang = _Box(5, 0.9, [280, 150, 360, 330])
    tertolak = F.analisis_hasil(
        _Res(sasaran, penunjang),
        lambda box, nama: 1.0,
        conf_min=0.35,
        conf_kelas={"pohon": 0.60},
    )
    assert not ada(tertolak, "pohon"), tertolak

    diterima = F.analisis_hasil(
        _Res(sasaran),
        lambda box, nama: 1.0,
        conf_min=0.35,
        conf_kelas={"pohon": 0.60},
    )
    assert len(ada(diterima, "pohon")) == 1, diterima


if __name__ == "__main__":



    for nama, fn in list(globals().items()):



        if nama.startswith("uji_") and callable(fn):



            fn()
            print(f"lulus  {nama}")

print("\nSemua uji lulus.")
