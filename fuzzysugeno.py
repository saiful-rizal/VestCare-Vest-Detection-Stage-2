import math
from collections.abc import Mapping, Sequence

import time

import numpy as np

KELAS_ID_KE_NAMA: dict[int, str] = {
    0: "pohon",
    1: "mobil",
    2: "motor",
    3: "orang",
    4: "lubang",
}

BAHAYA_KELAS = {
    "lubang": 10,
    "motor": 10,
    "mobil": 10,
    "orang": 6,
    "pohon": 6,
}

BAHAYA_DEFAULT = 5

KECEPATAN_JALAN_MS = 1.2

JARAK_KRITIS_M = 0.90

JARAK_TENGAH_M = 1.50

HFOV_DEG = 65.0

RASIO_GAMBAR = 3 / 4

VFOV_DEG = math.degrees(2 * math.atan(math.tan(math.radians(HFOV_DEG / 2)) * RASIO_GAMBAR))

TINGGI_KAMERA_M = 1.30

TILT_BAWAH_DEG = 15.0

KAMERA_MIN_M = round(TINGGI_KAMERA_M / math.tan(math.radians(VFOV_DEG / 2 + TILT_BAWAH_DEG)), 2)

KAMERA_MAKS_M = 5.0

US_MIN_M = 0.03

US_MAKS_M = 3.0

JARAK_TAK_DIKETAHUI_M = 2.0

SETENGAH_KORIDOR_M = 0.45
CONF_MIN_KELAS = {"lubang": 0.80}


def validasi_nama_kelas(
    nama_kelas: Mapping[object, object] | Sequence[object],
) -> dict[int, str]:
    if isinstance(nama_kelas, Mapping):
        nama_kelas_normal = {
            int(class_id): str(name) for class_id, name in nama_kelas.items()
        }
    elif isinstance(nama_kelas, Sequence) and not isinstance(nama_kelas, (str, bytes)):
        nama_kelas_normal = dict(enumerate(map(str, nama_kelas)))
    else:
        raise ValueError("Daftar kelas model tidak valid.")

    if nama_kelas_normal != KELAS_ID_KE_NAMA:
        raise ValueError(f"Urutan kelas model tidak cocok: {nama_kelas_normal}")

    return nama_kelas_normal


GETAR = {
    "AMAN":    {"pwm": 0,   "interval_ms": 0,    "pola": "mati"},
    "INFO":    {"pwm": 80,  "interval_ms": 1000, "pola": "denyut tunggal lemah"},
    "WASPADA": {"pwm": 120, "interval_ms": 600,  "pola": "berdenyut pelan"},
    "BAHAYA":  {"pwm": 255, "interval_ms": 150,  "pola": "terus-menerus cepat"},
}


def _angka_terbatas(nilai, nama):
    try:
        angka = float(nilai)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{nama} harus berupa angka hingga.") from error

    if not math.isfinite(angka):
        raise ValueError(f"{nama} harus berupa angka hingga.")

    return angka


def trap(x, a, b, c, d):
    x, a, b, c, d = (
        _angka_terbatas(nilai, nama)
        for nilai, nama in ((x, "x"), (a, "a"), (b, "b"), (c, "c"), (d, "d"))
    )

    if x < a or x > d:
        return 0.0

    if b <= x <= c:
        return 1.0

    if x < b:
        return (x - a) / (b - a) if b > a else 1.0

    return (d - x) / (d - c) if d > c else 1.0


def fuzzifikasi(jarak, bahaya, jalur):
    jarak = _angka_terbatas(jarak, "jarak")
    bahaya = _angka_terbatas(bahaya, "bahaya")
    jalur = _angka_terbatas(jalur, "jalur")

    return {
        "jarak": {
            "sangat_dekat": trap(jarak, -1, 0, JARAK_KRITIS_M, JARAK_TENGAH_M),
            "dekat": trap(jarak, JARAK_KRITIS_M, JARAK_TENGAH_M, 2.2, 3.0),
            "sedang": trap(jarak, 2.2, 3.0, 3.5, 4.5),
            "jauh": trap(jarak, 3.5, 4.5, 99, 100),
        },
        "bahaya": {
            "rendah": trap(bahaya, -1, 0, 3, 5),
            "sedang": trap(bahaya, 3, 5, 6, 8),
            "tinggi": trap(bahaya, 6, 8, 10, 11),
        },
        "jalur": {
            "luar": trap(jalur, -1, 0, 0.1, 0.35),
            "sebagian": trap(jalur, 0.1, 0.35, 0.5, 0.75),
            "penuh": trap(jalur, 0.5, 0.75, 1, 2),
        },
    }


ATURAN = [
    ("sangat_dekat", "tinggi", "penuh", 100), ("sangat_dekat", "tinggi", "sebagian", 100),
    ("dekat", "tinggi", "penuh", 90), ("dekat", "tinggi", "sebagian", 75),
    ("sedang", "tinggi", "penuh", 60), ("sedang", "tinggi", "sebagian", 45),
    ("jauh", "tinggi", None, 30),
    ("sangat_dekat", "sedang", "penuh", 85), ("sangat_dekat", "sedang", "sebagian", 65),
    ("dekat", "sedang", "penuh", 65), ("dekat", "sedang", "sebagian", 50),
    ("sedang", "sedang", "penuh", 40), ("sedang", "sedang", "sebagian", 30),
    ("jauh", "sedang", None, 15),
    ("sangat_dekat", "rendah", "penuh", 60), ("sangat_dekat", "rendah", "sebagian", 40),
    ("dekat", "rendah", "penuh", 40), ("dekat", "rendah", "sebagian", 25),
    ("sedang", "rendah", None, 15), ("jauh", "rendah", None, 5),
    ("sangat_dekat", "tinggi", "luar", 40), ("sangat_dekat", "sedang", "luar", 25),
    ("sangat_dekat", "rendah", "luar", 10),
    ("dekat", None, "luar", 5), ("sedang", None, "luar", 5), ("jauh", None, "luar", 5),
]


def sugeno(jarak, bahaya, jalur):
    mu = fuzzifikasi(jarak, bahaya, jalur)

    num = den = 0.0

    for j, b, p, z in ATURAN:
        w = min(mu["jarak"][j] if j else 1.0, mu["bahaya"][b] if b else 1.0, mu["jalur"][p] if p else 1.0)

        num += w * z

        den += w

    return num / den if den > 1e-9 else 0.0


def level(u):
    u = _angka_terbatas(u, "urgensi")

    return "BAHAYA" if u >= 75 else "WASPADA" if u >= 50 else "INFO" if u >= 25 else "AMAN"


def estimasi_jarak_kamera(xyxy, tinggi_gambar):
    f_y = (tinggi_gambar / 2) / math.tan(math.radians(VFOV_DEG / 2))

    sudut = TILT_BAWAH_DEG + math.degrees(math.atan((xyxy[3] - tinggi_gambar / 2) / f_y))

    if sudut < 1.0:
        return None

    return TINGGI_KAMERA_M / math.tan(math.radians(sudut))


UKURAN_KELAS_M = {"orang": 0.5, "pohon": 0.3, "motor": 0.7, "mobil": 1.5}


def rentang_kamera(lebar_px=640, px_min=24):
    f = (lebar_px / 2) / math.tan(math.radians(HFOV_DEG / 2))

    hasil = {k: {"dekat": KAMERA_MIN_M, "jauh": f * dim / px_min} for k, dim in UKURAN_KELAS_M.items()}

    hasil["lubang"] = {"dekat": KAMERA_MIN_M, "jauh": math.sqrt(f * TINGGI_KAMERA_M * 0.5 / px_min)}

    return hasil


def koridor_untuk_jarak(jarak):
    d = max(float(jarak), 0.4)

    frac = (SETENGAH_KORIDOR_M / d) / (2 * math.tan(math.radians(HFOV_DEG / 2)))

    frac = max(0.06, min(frac, 0.5))

    return (0.5 - frac, 0.5 + frac)


def keterhalangan(mask_poly, w, h, koridor=(0.30, 0.70), y_atas=0.45):
    if mask_poly is None or len(mask_poly) < 3:
        return 0.0

    poly = np.asarray(mask_poly, np.float64)

    try:
        import cv2
    except ImportError:
        x1, x2 = poly[:, 0].min(), poly[:, 0].max()

        y1, y2 = poly[:, 1].min(), poly[:, 1].max()

        lebar_obj = x2 - x1

        if lebar_obj <= 0 or y2 <= y_atas * h:
            return 0.0

        ix = max(0.0, min(x2, koridor[1] * w) - max(x1, koridor[0] * w))

        return float(ix / lebar_obj)

    m = np.zeros((h, w), np.uint8)

    cv2.fillPoly(m, [poly.astype(np.int32)], 1)

    m[:int(y_atas * h), :] = 0

    kor = np.zeros_like(m)

    kor[:, int(koridor[0] * w):int(koridor[1] * w)] = 1

    luas = m.sum()

    return float((m & kor).sum() / luas) if luas else 0.0


def arah(cx_norm):
    return "kiri" if cx_norm < 0.4 else "kanan" if cx_norm > 0.6 else "depan"


def fusi_jarak(jarak_kam, jarak_us, pos, terpotong=False):
    kam = None if jarak_kam is None else max(0.0, float(jarak_kam))

    if terpotong:
        kam = KAMERA_MIN_M if kam is None else min(kam, KAMERA_MIN_M)

    if kam is not None:
        kam = min(kam, KAMERA_MAKS_M)

    if jarak_us is not None and pos == "depan":
        if kam is None:
            return jarak_us, "ultrasonik"

        return min(kam, jarak_us), "kamera+ultrasonik"

    if kam is None:
        return JARAK_TAK_DIKETAHUI_M, "default"

    return kam, "kamera"


def _us_valid(jarak_us):
    if jarak_us is None:
        return None

    try:
        j = float(jarak_us)
    except (TypeError, ValueError):
        return None

    return j if US_MIN_M <= j <= US_MAKS_M else None


def _entri(kelas, jarak, bahaya, jalur, conf, pos, sumber):
    u = sugeno(jarak, bahaya, jalur)

    lv = level(u)

    return {"kelas": kelas, "jarak_m": round(jarak, 2), "bahaya": bahaya, "jalur": round(jalur, 2),
        "conf": round(conf, 2), "urgensi": round(u, 1), "level": lv, "arah": pos,
        "sumber": sumber, "getar": GETAR[lv],
        "pesan": f"{lv}: {kelas} {pos}, sekitar {jarak:.1f} meter"}


KELAS_TAHAN = ("lubang",)


class IngatanHalangan:
    def __init__(self, kecepatan=KECEPATAN_JALAN_MS, umur_maks=2.5,
                 jarak_picu=KAMERA_MIN_M + 1.0, waktu_fn=time.monotonic):
        self.kecepatan, self.umur_maks, self.jarak_picu, self._waktu = kecepatan, umur_maks, jarak_picu, waktu_fn

        self._simpan = {}

    def perbarui(self, daftar):
        kini = self._waktu()

        terlihat = {(d["kelas"], d["arah"]) for d in daftar}

        for d in daftar:
            if (d["kelas"] in KELAS_TAHAN and d["level"] != "AMAN" and d["sumber"] != "ingatan"
                    and d["jarak_m"] <= self.jarak_picu):
                self._simpan[(d["kelas"], d["arah"])] = (kini, d)

        tambahan = []

        for kunci, (t, d) in list(self._simpan.items()):
            if kunci in terlihat:
                continue

            umur = kini - t

            sisa = d["jarak_m"] - self.kecepatan * umur

            if umur > self.umur_maks or sisa <= 0.2:
                del self._simpan[kunci]

                continue

            tambahan.append(_entri(d["kelas"], sisa, d["bahaya"], d["jalur"], d["conf"], d["arah"], "ingatan"))

        return daftar + tambahan


def analisis_hasil(res, jarak_fn=None, conf_min=0.35, jarak_us=None, ingatan=None):
    h, w = res.orig_shape
    nama_kelas = validasi_nama_kelas(res.names)

    us = _us_valid(jarak_us)

    out = []

    if res.boxes is not None and len(res.boxes) > 0:
        polys = res.masks.xy if res.masks is not None else [None] * len(res.boxes)

        for box, poly in zip(res.boxes, polys):
            conf = float(box.conf)

            if conf < conf_min:
                continue

            class_id = int(box.cls)
            if class_id not in nama_kelas:
                raise ValueError(f"Class ID model tidak dikenal: {class_id}")
            nama = nama_kelas[class_id]
            if conf < CONF_MIN_KELAS.get(nama, conf_min):
                continue

            xyxy = box.xyxy[0].tolist()
            bbox = [
                round(max(0.0, min(1.0, float(xyxy[0]) / w)), 4),
                round(max(0.0, min(1.0, float(xyxy[1]) / h)), 4),
                round(max(0.0, min(1.0, float(xyxy[2]) / w)), 4),
                round(max(0.0, min(1.0, float(xyxy[3]) / h)), 4),
            ]

            pos = arah((xyxy[0] + xyxy[2]) / 2 / w)

            kam = jarak_fn(xyxy, nama) if jarak_fn is not None else estimasi_jarak_kamera(xyxy, h)

            jarak, sumber = fusi_jarak(kam, us, pos, terpotong=xyxy[3] >= 0.98 * h)

            bahaya = BAHAYA_KELAS.get(nama, BAHAYA_DEFAULT)

            if poly is None:
                poly = np.array([[xyxy[0], xyxy[1]], [xyxy[2], xyxy[1]], [xyxy[2], xyxy[3]], [xyxy[0], xyxy[3]]])

            jalur = keterhalangan(poly, w, h, koridor=koridor_untuk_jarak(jarak))

            entri = _entri(nama, jarak, bahaya, jalur, conf, pos, sumber)
            entri["bbox"] = bbox
            out.append(entri)

    if us is not None and not any(d["arah"] == "depan" for d in out):
        e = _entri("umum", us, BAHAYA_DEFAULT, 1.0, 0.0, "depan", "ultrasonik")

        if e["level"] != "AMAN":
            out.append(e)

    if ingatan is not None:
        out = ingatan.perbarui(out)

    return sorted(out, key=lambda d: -d["urgensi"])


def hitung_peringatan(skor_risiko, jarak_m=None):
    skor_risiko = max(0.0, min(1.0, _angka_terbatas(skor_risiko, "skor_risiko")))

    if jarak_m is None:
        if skor_risiko >= 0.75:
            tingkat = "bahaya"

        elif skor_risiko >= 0.45:
            tingkat = "waspada"

        else:
            tingkat = "aman"

        nilai = skor_risiko * 100.0

        ket = "jarak_m=None -> fallback tanpa fuzzy jarak"

    else:
        jarak_m = max(0.0, _angka_terbatas(jarak_m, "jarak_m"))

        bahaya = skor_risiko * 10.0

        u = sugeno(jarak_m, bahaya, 1.0)

        nilai = u

        if u >= 75:
            tingkat = "bahaya"

        elif u >= 50:
            tingkat = "waspada"

        elif u >= 25:
            tingkat = "info"

        else:
            tingkat = "aman"

        ket = f"Sugeno orde-nol: urgensi={u:.1f}"

    return {
        "tingkat": tingkat,
        "nilai_crisp": round(nilai / 100.0, 4),
        "getar": GETAR[tingkat.upper()],
        "keterangan": ket,
    }


if __name__ == "__main__":
    print(f"KAMERA_MIN_M={KAMERA_MIN_M} m  KAMERA_MAKS_M={KAMERA_MAKS_M} m  VFOV={VFOV_DEG:.1f} deg\n")

    uji = [("pohon", 2.0, 0.9), ("lubang", 2.0, 0.8), ("orang", 4.5, 0.9),
           ("motor", 3.5, 0.9), ("mobil", 3.5, 0.9),
           ("motor", 0.5, 0.0), ("pohon", 0.5, 0.0), ("motor", 2.0, 0.0)]

    print(f"{'kelas':<12}{'jarak':>6}{'jalur':>7}{'urgensi':>9}  level")

    for k, j, p in uji:
        u = sugeno(j, BAHAYA_KELAS.get(k, BAHAYA_DEFAULT), p)

        print(f"{k:<12}{j:>6.1f}{p:>7.2f}{u:>9.1f}  {level(u)}")
