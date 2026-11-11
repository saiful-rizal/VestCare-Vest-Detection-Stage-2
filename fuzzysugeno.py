import math
from collections.abc import Mapping
from typing import Any, Callable, Optional, Sequence, cast

import time

import numpy as np

KELAS_ID_KE_NAMA: dict[int, str] = {
    0: "pohon",
    1: "mobil",
    2: "motor",
    3: "orang",
    4: "lubang",
}
KELAS_INTERNAL_MODEL: dict[int, str] = {5: "__non_target_internal__"}

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

CONF_RAGU_DEFAULT = 0.50

KELAS_GERAK = ("mobil", "motor", "orang")


def validasi_nama_kelas(
    nama_kelas: Mapping[int, str] | list[str] | tuple[str, ...],
) -> dict[int, str]:
    if isinstance(nama_kelas, Mapping):
        nama_kelas_normal = {
            int(class_id): str(name) for class_id, name in nama_kelas.items()
        }
    else:
        nama_kelas_normal = dict(enumerate(map(str, nama_kelas)))

    if nama_kelas_normal not in (
        KELAS_ID_KE_NAMA,
        {**KELAS_ID_KE_NAMA, **KELAS_INTERNAL_MODEL},
    ):
        raise ValueError(f"Urutan kelas model tidak cocok: {nama_kelas_normal}")

    return nama_kelas_normal


GETAR: dict[str, dict[str, int | str]] = {
    "AMAN":    {"pwm": 0,   "interval_ms": 0,    "pola": "mati"},
    "INFO":    {"pwm": 80,  "interval_ms": 1000, "pola": "denyut tunggal lemah"},
    "WASPADA": {"pwm": 120, "interval_ms": 600,  "pola": "berdenyut pelan"},
    "BAHAYA":  {"pwm": 255, "interval_ms": 150,  "pola": "terus-menerus cepat"},
}


def _angka_terbatas(nilai: Any, nama: str) -> float:
    try:
        angka = float(nilai)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError(f"{nama} harus berupa angka hingga.") from error

    if not math.isfinite(angka):
        raise ValueError(f"{nama} harus berupa angka hingga.")

    return angka


def trap(x: float, a: float, b: float, c: float, d: float) -> float:
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


def fuzzifikasi(jarak: float, bahaya: float, jalur: float) -> dict[str, dict[str, float]]:
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


ATURAN: list[tuple[str | None, str | None, str | None, int]] = [
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


def sugeno(jarak: float, bahaya: float, jalur: float) -> float:
    mu = fuzzifikasi(jarak, bahaya, jalur)

    num = den = 0.0

    for j, b, p, z in ATURAN:
        w = min(mu["jarak"][j] if j else 1.0, mu["bahaya"][b] if b else 1.0, mu["jalur"][p] if p else 1.0)

        num += w * z

        den += w

    return num / den if den > 1e-9 else 0.0


def level(u: float) -> str:
    u = _angka_terbatas(u, "urgensi")

    return "BAHAYA" if u >= 75 else "WASPADA" if u >= 50 else "INFO" if u >= 25 else "AMAN"


def estimasi_jarak_kamera(xyxy: Sequence[float], tinggi_gambar: int) -> Optional[float]:
    f_y = (tinggi_gambar / 2) / math.tan(math.radians(VFOV_DEG / 2))

    sudut = TILT_BAWAH_DEG + math.degrees(math.atan((xyxy[3] - tinggi_gambar / 2) / f_y))

    if sudut < 1.0:
        return None

    return TINGGI_KAMERA_M / math.tan(math.radians(sudut))


UKURAN_KELAS_M = {"orang": 0.5, "pohon": 0.3, "motor": 0.7, "mobil": 1.5}


def rentang_kamera(lebar_px: int = 640, px_min: int = 24) -> dict[str, dict[str, float]]:
    f = (lebar_px / 2) / math.tan(math.radians(HFOV_DEG / 2))

    hasil = {k: {"dekat": KAMERA_MIN_M, "jauh": f * dim / px_min} for k, dim in UKURAN_KELAS_M.items()}

    hasil["lubang"] = {"dekat": KAMERA_MIN_M, "jauh": math.sqrt(f * TINGGI_KAMERA_M * 0.5 / px_min)}

    return hasil


def koridor_untuk_jarak(jarak: float) -> tuple[float, float]:
    d = max(float(jarak), 0.4)

    frac = (SETENGAH_KORIDOR_M / d) / (2 * math.tan(math.radians(HFOV_DEG / 2)))

    frac = max(0.06, min(frac, 0.5))

    return (0.5 - frac, 0.5 + frac)


def keterhalangan(
    mask_poly: Optional[np.ndarray | Sequence[Sequence[float]]],
    w: int,
    h: int,
    koridor: tuple[float, float] = (0.30, 0.70),
    y_atas: float = 0.45,
) -> float:
    if mask_poly is None or len(mask_poly) < 3:
        return 0.0

    poly = np.asarray(mask_poly, np.float64)

    try:
        import cv2
    except ImportError:
        x1, x2 = poly[:, 0].min(), poly[:, 0].max()

        y2 = poly[:, 1].max()

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


def arah(cx_norm: float) -> str:
    return "kiri" if cx_norm < 0.4 else "kanan" if cx_norm > 0.6 else "depan"


def fusi_jarak(
    jarak_kam: Optional[float],
    jarak_us: Optional[float],
    pos: str,
    terpotong: bool = False,
) -> tuple[float, str]:
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


def _us_valid(jarak_us: Any) -> Optional[float]:
    if jarak_us is None:
        return None

    try:
        j = float(jarak_us)
    except (TypeError, ValueError, OverflowError):
        return None

    return j if US_MIN_M <= j <= US_MAKS_M else None


def _entri(
    kelas: str,
    jarak: float,
    bahaya: float,
    jalur: float,
    conf: float,
    pos: str,
    sumber: str,
) -> dict[str, Any]:
    u = sugeno(jarak, bahaya, jalur)

    lv = level(u)

    return {"kelas": kelas, "jarak_m": round(jarak, 2), "bahaya": bahaya, "jalur": round(jalur, 2),
        "conf": round(conf, 2), "urgensi": round(u, 1), "level": lv, "arah": pos,
        "sumber": sumber, "getar": GETAR[lv], "gerak": "netral", "ragu": False,
        "pesan": f"{lv}: {kelas} {pos}, sekitar {jarak:.1f} meter"}


KELAS_TAHAN = ("lubang",)


class IngatanHalangan:
    def __init__(
        self,
        kecepatan: float = KECEPATAN_JALAN_MS,
        umur_maks: float = 2.5,
        jarak_picu: float = KAMERA_MIN_M + 1.0,
        waktu_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kecepatan, self.umur_maks, self.jarak_picu, self._waktu = kecepatan, umur_maks, jarak_picu, waktu_fn

        self._simpan: dict[tuple[str, str], tuple[float, dict[str, Any]]] = {}

    def perbarui(self, daftar: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kini = self._waktu()

        terlihat = {(d["kelas"], d["arah"]) for d in daftar}

        for d in daftar:
            if (d["kelas"] in KELAS_TAHAN and d["level"] != "AMAN" and d["sumber"] != "ingatan"
                    and not d.get("ragu") and d["jarak_m"] <= self.jarak_picu):
                self._simpan[(d["kelas"], d["arah"])] = (kini, d)

        tambahan: list[dict[str, Any]] = []

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


class PelacakGerak:
    """Menaksir gerak objek dari perubahan jarak dan posisi antar frame.

    Perubahan posisi kotak deteksi menangkap gerak menyamping yang tidak terlihat
    dari jarak, sedangkan perubahan jarak menangkap objek yang mendekat.
    """

    def __init__(
        self,
        kelas: Sequence[str] = KELAS_GERAK,
        ambang_cepat_ms: float = 1.8,
        ambang_diam_ms: float = 0.4,
        ambang_posisi_per_detik: float = 0.05,
        ambang_posisi_diam_per_detik: float = 0.025,
        min_sampel: int = 3,
        umur_maks: float = 1.5,
        waktu_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.kelas = tuple(kelas)
        self.ambang_cepat = float(ambang_cepat_ms)
        self.ambang_diam = float(ambang_diam_ms)
        self.ambang_posisi = float(ambang_posisi_per_detik)
        self.ambang_posisi_diam = float(ambang_posisi_diam_per_detik)
        self.min_sampel = max(1, int(min_sampel))
        self.umur_maks = float(umur_maks)
        self._waktu = waktu_fn
        self._s: dict[int, dict[str, Any]] = {}
        self._id_berikutnya = 0

    def perbarui(self, daftar: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kini = self._waktu()
        terpakai: set[int] = set()

        for d in daftar:
            d.setdefault("gerak", "netral")

            kelas, arah, j = d.get("kelas"), d.get("arah"), d.get("jarak_m")
            if kelas not in self.kelas or j is None or d.get("sumber") == "ingatan" or d.get("ragu"):
                continue

            bbox = d.get("bbox")
            pusat: tuple[float, float] | None = None
            if isinstance(bbox, (list, tuple)):
                coordinates: list[float] = []
                for value in cast(Sequence[object], bbox):
                    if not isinstance(value, (int, float)):
                        break
                    coordinate = float(value)
                    if not math.isfinite(coordinate):
                        break
                    coordinates.append(coordinate)
                    if len(coordinates) > 4:
                        break
                if len(coordinates) == 4:
                    pusat = ((coordinates[0] + coordinates[2]) / 2, (coordinates[1] + coordinates[3]) / 2)

            kandidat: tuple[float, int, dict[str, Any]] | None = None
            for id_objek, calon in self._s.items():
                if id_objek in terpakai or calon["kelas"] != kelas or kini - calon["t"] > self.umur_maks:
                    continue
                pusat_lama = calon["pusat"]
                if pusat is not None and pusat_lama is not None:
                    selisih = math.hypot(pusat[0] - pusat_lama[0], pusat[1] - pusat_lama[1])
                    if selisih > 0.35:
                        continue
                elif calon["arah"] != arah:
                    continue
                else:
                    selisih = 0.0
                if kandidat is None or selisih < kandidat[0]:
                    kandidat = (selisih, id_objek, calon)

            if kandidat is None:
                id_objek = self._id_berikutnya
                self._id_berikutnya += 1
                self._s[id_objek] = {
                    "kelas": kelas, "arah": arah, "t": kini, "j": float(j),
                    "pusat": pusat, "v_jarak": None, "v_posisi": None,
                    "gerak": 0, "diam": 0,
                }
                terpakai.add(id_objek)
                continue

            _, id_objek, st = kandidat
            terpakai.add(id_objek)
            dt = kini - st["t"]
            if dt < 0.05:
                continue

            v_jarak = (st["j"] - float(j)) / dt
            st["v_jarak"] = v_jarak if st["v_jarak"] is None else 0.5 * st["v_jarak"] + 0.5 * v_jarak
            v_posisi = None
            if pusat is not None and st["pusat"] is not None:
                v_posisi = math.hypot(pusat[0] - st["pusat"][0], pusat[1] - st["pusat"][1]) / dt
                st["v_posisi"] = v_posisi if st["v_posisi"] is None else 0.5 * st["v_posisi"] + 0.5 * v_posisi
            elif pusat is not None:
                st["v_posisi"] = None
            st["t"], st["j"], st["pusat"], st["arah"] = kini, float(j), pusat, arah

            posisi_bergerak = st["v_posisi"] is not None and st["v_posisi"] >= self.ambang_posisi
            posisi_diam = st["v_posisi"] is None or st["v_posisi"] <= self.ambang_posisi_diam
            st["gerak"] = st["gerak"] + 1 if st["v_jarak"] >= self.ambang_cepat or posisi_bergerak else 0
            st["diam"] = st["diam"] + 1 if abs(st["v_jarak"]) <= self.ambang_diam and posisi_diam else 0

            if st["gerak"] >= self.min_sampel:
                d["gerak"] = "bergerak"
            elif st["diam"] >= 2 * self.min_sampel:
                d["gerak"] = "diam"

        for id_objek in [k for k, st in self._s.items() if kini - st["t"] > self.umur_maks]:
            del self._s[id_objek]

        return daftar


def analisis_hasil(
    res: Any,
    jarak_fn: Optional[Callable[[Sequence[float], str], Optional[float]]] = None,
    conf_min: float = 0.35,
    jarak_us: Optional[float] = None,
    ingatan: Optional[IngatanHalangan] = None,
    conf_ragu: float = CONF_RAGU_DEFAULT,
) -> list[dict[str, Any]]:
    h, w = res.orig_shape
    nama_kelas = validasi_nama_kelas(res.names)

    us = _us_valid(jarak_us)

    out: list[dict[str, Any]] = []

    if res.boxes is not None and len(res.boxes) > 0:
        polys = res.masks.xy if res.masks is not None else [None] * len(res.boxes)

        for index, box in enumerate(res.boxes):
            poly = polys[index] if index < len(polys) else None
            conf = float(box.conf)

            if conf < conf_min:
                continue

            class_id = int(box.cls)
            if class_id not in nama_kelas:
                raise ValueError(f"Class ID model tidak dikenal: {class_id}")
            if class_id not in KELAS_ID_KE_NAMA:
                continue
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
            entri["ragu"] = conf < conf_ragu
            entri["bbox"] = bbox
            out.append(entri)

    if us is not None and not any(d["arah"] == "depan" for d in out):
        e = _entri("umum", us, BAHAYA_DEFAULT, 1.0, 0.0, "depan", "ultrasonik")

        if e["level"] != "AMAN":
            out.append(e)

    if ingatan is not None:
        out = ingatan.perbarui(out)

    return sorted(out, key=lambda d: -d["urgensi"])


def hitung_peringatan(
    skor_risiko: float,
    jarak_m: Optional[float] = None,
) -> dict[str, Any]:
    skor_risiko = max(0.0, min(1.0, _angka_terbatas(skor_risiko, "skor_risiko")))

    if jarak_m is None:
        nilai = skor_risiko * 100.0
        tingkat = level(nilai).lower()

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
