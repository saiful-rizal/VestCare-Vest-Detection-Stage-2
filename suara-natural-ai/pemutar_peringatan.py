from __future__ import annotations

import argparse

import json

import os

import random

import sys

import time

from pathlib import Path

from typing import Iterable, Optional

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

FOLDER_DEFAULT = "cache_suara"

SKEMA_DIDUKUNG = (2, 3)

KELAS_UMUM = "umum"

KUNCI_AMAN = "jalur_aman"

JEDA_AMAN_S = 1.5

JEDA_SEGMEN_MS = 110

PAD_AWAL_MS = 120

SISI_DEFAULT = "kanan"

PRIORITAS_DEFAULT = 2

COOLDOWN_DEFAULT = 4.0

JEDA_ANTAR_PUTARAN_DETIK = 0.7

PRIORITAS_LEVEL = {"info": 2, "waspada": 3, "bahaya": 5}

COOLDOWN_LEVEL = {"info": 5.0, "waspada": 3.5, "bahaya": 2.0}

KELAS_TANGGA = ("mobil", "motor")

TANGGA_JARAK = ((5.0, "info"),
    (3.5, "waspada"),
    (2.5, "waspada"),
    (1.5, "bahaya"))

HISTERESIS_M = 0.6

UMUR_TANGGA_S = 2.0

URUTAN_LEVEL = {"aman": 0, "info": 1, "waspada": 2, "bahaya": 3}

KELAS_GERAK = ()


def bucket_jarak(meter: float) -> int:
    if meter < 0.75:
        return 5

    return min(50, int(meter * 2 + 0.5) * 5)


def kunci_dari_analisis(d: dict, kelas_dikenal: Optional[Iterable[str]] = None) -> Optional[str]:
    lv = str(d.get("level", "")).lower()

    if lv in ("", "aman"):
        return None

    kelas = str(d.get("kelas", ""))

    if kelas_dikenal is not None and kelas not in set(kelas_dikenal):
        kelas = KELAS_UMUM

    return f"{lv}_{kelas}_{d.get('arah', 'depan')}"


def pilih_aksi(teratas: dict, semua: list[dict], sisi_default: str = SISI_DEFAULT) -> str:
    lv = str(teratas.get("level", "")).lower()

    arah = teratas.get("arah", "depan")

    terisi = {d.get("arah") for d in semua if str(d.get("level", "")).upper() != "AMAN"} | {arah}

    if arah in ("kiri", "kanan"):
        lawan = "kanan" if arah == "kiri" else "kiri"

        if lv == "info":
            return "lurus"

        if lawan in terisi:
            return "berhenti" if lv == "bahaya" else "pelan"

        return ("berhenti_" if lv == "bahaya" else "pelan_") + lawan

    bebas = [s for s in ("kiri", "kanan") if s not in terisi]

    if lv == "info":
        return "pelan"

    if lv == "bahaya":
        return f"berhenti_{bebas[0]}" if len(bebas) == 1 else "berhenti"

    if len(bebas) == 1:
        return f"pelan_{bebas[0]}"

    if len(bebas) == 2:
        return f"pelan_{sisi_default}"

    return "pelan"


def rencana_peringatan(teratas: dict, semua: list[dict], kelas_dikenal: Optional[Iterable[str]] = None,
                       tersedia: Optional[set] = None, sisi_default: str = SISI_DEFAULT) -> Optional[dict]:
    lv = str(teratas.get("level", "")).lower()

    if lv in ("", "aman"):
        return None

    kelas = str(teratas.get("kelas", ""))

    if kelas_dikenal is not None and kelas not in set(kelas_dikenal):
        kelas = KELAS_UMUM

    arah = teratas.get("arah", "depan")

    gerak = "netral"

    benda = f"benda_{kelas}_{arah}_{gerak}"

    if tersedia is not None and benda not in tersedia:
        benda = f"benda_{kelas}_{arah}_netral"

    aksi = pilih_aksi(teratas, semua, sisi_default)

    segmen = []

    if lv in ("waspada", "bahaya"):
        segmen.append(f"awal_{lv}")

    segmen.append(benda)

    if teratas.get("jarak_m") is not None:
        segmen.append(f"jarak_{bucket_jarak(float(teratas['jarak_m'])):02d}")

    segmen.append(f"solusi_{aksi}")

    if tersedia is not None:
        segmen = [k for k in segmen if k in tersedia]

    return {"level": lv, "segmen": segmen, "aksi": aksi, "kunci": (lv, kelas, arah, gerak, aksi),
            "tahap_baru": bool(teratas.get("tahap_baru"))}


class PelacakGerak:
    def __init__(self, kecepatan_pengguna_fn=None, ambang_cepat_ms: float = 1.8, ambang_gerak_ms: float = 0.8,
                 ambang_diam_ms: float = 0.4, min_sampel: int = 3, umur_maks: float = 1.0,
                 waktu_fn=time.monotonic) -> None:
        self.kec_pengguna, self.ambang_cepat = kecepatan_pengguna_fn, ambang_cepat_ms

        self.ambang_gerak, self.ambang_diam = ambang_gerak_ms, ambang_diam_ms

        self.min_sampel, self.umur_maks, self._waktu = min_sampel, umur_maks, waktu_fn

        self._s: dict = {}

    def perbarui(self, daftar: list[dict]) -> list[dict]:
        kini = self._waktu()

        terlihat = set()

        for d in daftar:
            kelas, arah, j = d.get("kelas"), d.get("arah"), d.get("jarak_m")

            if kelas not in KELAS_GERAK or j is None or d.get("sumber") == "ingatan":
                continue

            k = (kelas, arah)

            terlihat.add(k)

            st = self._s.get(k)

            if st is None or kini - st["t"] > self.umur_maks:
                self._s[k] = {"t": kini, "j": float(j), "v": None, "gerak": 0, "diam": 0}

                continue

            dt = kini - st["t"]

            if dt < 0.05:
                continue

            v = (st["j"] - float(j)) / dt

            st["v"] = v if st["v"] is None else 0.5 * st["v"] + 0.5 * v

            st["t"], st["j"] = kini, float(j)

            if self.kec_pengguna is not None:
                vu = max(0.0, float(self.kec_pengguna() or 0.0))

                rel = abs(st["v"] - vu)

                st["gerak"] = st["gerak"] + 1 if rel >= self.ambang_gerak else 0

                st["diam"] = st["diam"] + 1 if rel <= self.ambang_diam else 0
            else:
                st["gerak"] = st["gerak"] + 1 if st["v"] >= self.ambang_cepat else 0

                st["diam"] = 0

            if not d.get("gerak"):
                if st["gerak"] >= self.min_sampel:
                    d["gerak"] = "bergerak"

                elif st["diam"] >= 2 * self.min_sampel:
                    d["gerak"] = "diam"

        for k in [k for k, st in self._s.items() if k not in terlihat and kini - st["t"] > self.umur_maks]:
            del self._s[k]

        return daftar


class TanggaJarak:
    def __init__(self, kelas=KELAS_TANGGA, tangga=TANGGA_JARAK, histeresis_m: float = HISTERESIS_M,
                 umur_maks: float = UMUR_TANGGA_S, waktu_fn=time.monotonic) -> None:
        self.kelas = tuple(kelas)

        self.tangga = tuple(sorted(tangga, key=lambda t: -t[0]))

        self.histeresis, self.umur_maks, self._waktu = histeresis_m, umur_maks, waktu_fn

        self._st: dict = {}

    def tahap(self, jarak: float) -> int:
        return sum(1 for batas, _ in self.tangga if jarak <= batas)

    def terapkan(self, daftar: list[dict]) -> list[dict]:
        kini = self._waktu()

        terlihat, keluar = set(), []

        for d in daftar:
            kelas, arah, j = d.get("kelas"), d.get("arah"), d.get("jarak_m")

            if kelas not in self.kelas or j is None or d.get("sumber") == "ingatan":
                keluar.append(d)

                continue

            k = (kelas, arah)

            terlihat.add(k)

            st = self._st.get(k)

            if st is None or kini - st["t"] > self.umur_maks:
                st = self._st[k] = {"tahap": 0, "t": kini}

            st["t"] = kini

            while st["tahap"] > 0 and float(j) > self.tangga[st["tahap"] - 1][0] + self.histeresis:
                st["tahap"] -= 1

            tahap = self.tahap(float(j))

            asli = str(d.get("level", "AMAN")).lower()

            e = dict(d)

            e["tahap"], e["tahap_baru"], e["level_asli"] = tahap, tahap > st["tahap"], asli.upper()

            if tahap >= 1:
                minimal = self.tangga[tahap - 1][1]

                if URUTAN_LEVEL[minimal] > URUTAN_LEVEL.get(asli, 0):
                    e["level"] = minimal.upper()

            keluar.append(e)

        for k in [k for k, st in self._st.items() if k not in terlihat and kini - st["t"] > self.umur_maks]:
            del self._st[k]

        return keluar

    @staticmethod
    def boleh_bicara(d: dict) -> bool:
        if "tahap" not in d:
            return True

        return bool(d["tahap_baru"]) or d.get("level_asli") == "BAHAYA"

    def tandai(self, d: dict) -> None:
        if "tahap" in d:
            st = self._st.get((d.get("kelas"), d.get("arah")))

            if st is not None:
                st["tahap"] = max(st["tahap"], d["tahap"])


class PemutarPeringatan:
    def __init__(self, folder: str = FOLDER_DEFAULT, seed: Optional[int] = None,
                 sisi_default: str = SISI_DEFAULT, tangga=None) -> None:
        import pygame

        self._pg = pygame

        jalur = Path(folder)

        jalur_manifest = jalur / "manifest.json"

        if not jalur_manifest.exists():
            raise SystemExit(f"Pustaka suara tidak ditemukan di '{folder}' (manifest.json tidak ada). "
                "Pustaka dibuat dengan: python siapkan_pustaka.py")

        manifest = json.loads(jalur_manifest.read_text(encoding="utf-8"))

        self._skema = manifest.get("skema")

        if self._skema not in SKEMA_DIDUKUNG:
            raise SystemExit("Format pustaka tidak dikenal. Buat ulang dengan: python siapkan_pustaka.py --paksa")

        try:
            pygame.mixer.init()

        except pygame.error as galat:
            raise SystemExit(f"Perangkat audio tidak dapat dibuka: {galat}")

        self._rng = random.Random(seed)

        self.sisi_default = sisi_default

        self._tangga = TanggaJarak() if tangga is None else (tangga or None)

        self._meta: dict = manifest.get("meta", {})

        self.kelas_dikenal: list[str] = list(manifest.get("kelas", []))

        self._pesan: dict[str, list[tuple[str, object]]] = {
            k: [(e["teks"], pygame.mixer.Sound(str(jalur / e["berkas"]))) for e in v]
            for k, v in manifest["pesan"].items()
        }

        self.tersedia = set(self._pesan)

        self._raw: dict[int, bytes] = {}

        self._varian_terakhir: dict[str, int] = {}

        self._waktu_putar: dict = {}

        self._saluran = None

        self._prioritas_aktif = 0

        self._kunci_hilang: set = set()

        self._perlu_aman = False

        self._aman_sejak: Optional[float] = None

        self.terakhir_diumumkan: Optional[dict] = None

        # Guard agar tidak ada pemutaran ganda.
        self._kunci_sedang_diputar: Optional[tuple] = None
        self._waktu_putar_terakhir: float = 0.0

    def daftar_kunci(self) -> list[str]:
        return sorted(self._pesan)

    def sedang_berbunyi(self) -> bool:
        sedang = self._saluran is not None and self._saluran.get_busy()

        if not sedang and self._kunci_sedang_diputar is not None:
            self._kunci_sedang_diputar = None

        return sedang

    def _pilih(self, kunci: str):
        pilihan = list(range(len(self._pesan[kunci])))

        terakhir = self._varian_terakhir.get(kunci)

        if terakhir in pilihan and len(pilihan) > 1:
            pilihan.remove(terakhir)

        i = self._rng.choice(pilihan)

        self._varian_terakhir[kunci] = i

        return self._pesan[kunci][i]

    def _lapor_hilang(self, kunci: str) -> None:
        if kunci not in self._kunci_hilang:
            self._kunci_hilang.add(kunci)

            print(f"[pemutar] klip '{kunci}' tidak ada di pustaka; jalankan: python siapkan_pustaka.py --periksa",
                file=sys.stderr)

    def umumkan(self, kunci: str) -> Optional[str]:
        if kunci not in self._pesan:
            self._lapor_hilang(kunci)

            return None

        meta = self._meta.get(kunci, {})

        prioritas = int(meta.get("prioritas", PRIORITAS_DEFAULT))

        cooldown = float(meta.get("cooldown", COOLDOWN_DEFAULT))

        kini = time.monotonic()

        berbunyi = self.sedang_berbunyi()

        if berbunyi and prioritas <= self._prioritas_aktif:
            return None

        if kini - self._waktu_putar.get(kunci, -1e9) < cooldown:
            return None

        teks, suara = self._pilih(kunci)

        if berbunyi:
            self._saluran.stop()

        self._saluran = suara.play()

        self._prioritas_aktif = prioritas

        self._waktu_putar[kunci] = kini

        return teks

    def _bytes(self, suara) -> bytes:
        k = id(suara)

        if k not in self._raw:
            self._raw[k] = suara.get_raw()

        return self._raw[k]

    def _hening(self, ms: int) -> bytes:
        freq, fmt, kanal = self._pg.mixer.get_init()

        return bytes(int(freq * ms / 1000) * kanal * (abs(fmt) // 8))

    def _rakit(self, segmen: list[str]):
        potongan, teks = [self._hening(PAD_AWAL_MS)], []

        jeda = self._hening(JEDA_SEGMEN_MS)

        for i, kunci in enumerate(segmen):
            t, suara = self._pilih(kunci)

            teks.append(t)

            if i:
                potongan.append(jeda)

            potongan.append(self._bytes(suara))

        data = b"".join(potongan)

        freq, fmt, kanal = self._pg.mixer.get_init()

        durasi = len(data) / (freq * kanal * (abs(fmt) // 8))

        return " ".join(teks), self._pg.mixer.Sound(buffer=data), durasi

    def _putar_rencana(self, r: dict) -> Optional[str]:
        lv = r["level"]

        meta = self._meta.get(lv, {})

        prioritas = int(meta.get("prioritas", PRIORITAS_LEVEL.get(lv, PRIORITAS_DEFAULT)))

        cooldown = float(meta.get("cooldown", COOLDOWN_LEVEL.get(lv, COOLDOWN_DEFAULT)))

        kini = time.monotonic()

        berbunyi = self.sedang_berbunyi()

        # Jeda minimum antar pemutaran apa pun mencegah suara ganda yang
        # dipicu berulang kali dalam waktu sangat dekat (mis. setiap frame).
        if berbunyi and kini - self._waktu_putar_terakhir < JEDA_ANTAR_PUTARAN_DETIK:
            return None

        if berbunyi and prioritas <= self._prioritas_aktif:
            return None

        # Jika kunci yang sama masih sedang diputar, jangan putar ulang kecuali
        # prioritas baru lebih tinggi (interupsi berani).
        kunci_baru = r["kunci"]
        if self._kunci_sedang_diputar == kunci_baru and not (
            berbunyi and prioritas > self._prioritas_aktif
        ):
            return None

        if not r.get("tahap_baru") and kini - self._waktu_putar.get(kunci_baru, -1e9) < cooldown:
            return None

        if not any(k.startswith("benda_") for k in r["segmen"]):
            for k in (r.get("diminta") or []):
                self._lapor_hilang(k)

            return None

        teks, suara, durasi = self._rakit(r["segmen"])

        if berbunyi:
            self._saluran.stop()

        self._saluran = suara.play()

        self._prioritas_aktif = prioritas

        self.terakhir_diumumkan = r.get("benda")

        self._waktu_putar[kunci_baru] = kini + durasi
        self._kunci_sedang_diputar = kunci_baru
        self._waktu_putar_terakhir = kini

        return teks

    def susun_peringatan(self, daftar: list[dict], penutur: Optional[list[dict]] = None) -> Optional[dict]:
        berbahaya = [d for d in daftar if str(d.get("level", "")).upper() != "AMAN"]

        calon = berbahaya if penutur is None else [d for d in penutur if str(d.get("level", "")).upper() != "AMAN"]

        if not calon:
            return None

        teratas = max(calon, key=lambda d: (URUTAN_LEVEL.get(str(d.get("level", "")).lower(), 0),
            d.get("urgensi", 0.0)))

        r = rencana_peringatan(teratas, berbahaya, self.kelas_dikenal or None, self.tersedia, self.sisi_default)

        if r is not None:
            r["benda"] = teratas

            return r

    def umumkan_analisis(self, daftar: list[dict]) -> Optional[str]:
        self.terakhir_diumumkan = None

        if self._skema == 2:
            return self._analisis_skema2(daftar)

        kini = time.monotonic()

        if self._tangga is not None:
            daftar = self._tangga.terapkan(daftar)

        berbahaya = [d for d in daftar if str(d.get("level", "")).upper() != "AMAN"]

        if not berbahaya:
            return self._jalur_aman(kini)

        self._aman_sejak = None

        penutur = [d for d in berbahaya if TanggaJarak.boleh_bicara(d)]

        r = self.susun_peringatan(daftar, penutur) if penutur else None

        teks = self._putar_rencana(r) if r else None

        if teks is not None:
            self._perlu_aman = True

        if r is not None and self._tangga is not None:
            self._tangga.tandai(r["benda"])

        return teks

    def _jalur_aman(self, kini: float) -> Optional[str]:
        if not self._perlu_aman:
            return None

        if self._aman_sejak is None:
            self._aman_sejak = kini

        if kini - self._aman_sejak >= JEDA_AMAN_S:
            teks = self.umumkan(KUNCI_AMAN)

            if teks is not None or KUNCI_AMAN not in self._pesan:
                self._perlu_aman = False

            return teks

        return None

    def _analisis_skema2(self, daftar: list[dict]) -> Optional[str]:
        kini = time.monotonic()

        berbahaya = [d for d in daftar if str(d.get("level", "")).upper() != "AMAN"]

        if not berbahaya:
            return self._jalur_aman(kini)

        self._aman_sejak = None

        teratas = max(berbahaya, key=lambda d: d.get("urgensi", 0.0))

        kunci = kunci_dari_analisis(teratas, self.kelas_dikenal or None)

        teks = self.umumkan(kunci) if kunci else None

        if teks is not None:
            self._perlu_aman = True

            self.terakhir_diumumkan = teratas

        return teks

    def berhenti(self) -> None:
        if self._saluran is not None:
            self._saluran.stop()

    def tunggu_selesai(self) -> None:
        while self.sedang_berbunyi():
            time.sleep(0.05)


def _d(kelas, level, arah, urgensi, jarak, gerak=None) -> dict:
    return {"kelas": kelas, "level": level, "arah": arah, "urgensi": urgensi, "jarak_m": jarak, "gerak": gerak}


def jalankan_simulasi(folder: str) -> None:
    pemutar = PemutarPeringatan(folder)

    if pemutar._skema == 2:
        raise SystemExit("Simulasi ini untuk pustaka skema 3. Buat ulang: python siapkan_pustaka.py --paksa")

    kasus = [
        ("Mobil melaju di kiri, dekat", [_d("mobil", "BAHAYA", "kiri", 90, 1.2, "bergerak")]),
        ("Mobil parkir di kiri, agak jauh", [_d("mobil", "INFO", "kiri", 30, 3.0, "diam")]),
        ("Orang berjalan di kiri, cukup dekat", [_d("orang", "WASPADA", "kiri", 60, 2.0, "bergerak")]),
        ("Lubang tepat di depan", [_d("lubang", "BAHAYA", "depan", 95, 1.0)]),
        ("Pohon di depan, mobil di kanan", [_d("pohon", "WASPADA", "depan", 60, 2.0),
            _d("mobil", "INFO", "kanan", 30, 3.5, "diam")]),
    ]

    for judul, daftar in kasus:
        r = pemutar.susun_peringatan(daftar)

        print(f"{judul}\n   klip : {' + '.join(r['segmen'])}")

        teks = pemutar.umumkan_analisis(daftar)

        print(f"   suara: {teks}")

        pemutar.tunggu_selesai()

        time.sleep(0.3)

    print("Jalur aman setelah semua benda hilang")

    t0 = time.monotonic()

    while time.monotonic() - t0 < JEDA_AMAN_S + 1.0:
        hasil = pemutar.umumkan_analisis([])

        if hasil:
            print("   suara:", hasil)

            break

        time.sleep(0.1)

    pemutar.tunggu_selesai()


def main() -> None:
    ap = argparse.ArgumentParser(description="Pemutar peringatan suara (pengujian).")

    sub = ap.add_subparsers(dest="perintah", required=True)

    for nama, bantuan in (("daftar", "Tampilkan klip dan teksnya."), ("putar", "Putar satu klip."),
                          ("simulasi", "Simulasi keluaran fuzzy.")):
        p = sub.add_parser(nama, help=bantuan)

        p.add_argument("--folder", default=FOLDER_DEFAULT)

        if nama == "putar":
            p.add_argument("kunci")

    a = ap.parse_args()

    if a.perintah == "daftar":
        m = json.loads((Path(a.folder) / "manifest.json").read_text(encoding="utf-8"))

        for kunci, daftar in m["pesan"].items():
            print(kunci)

            for e in daftar:
                print(f"    - {e['teks']}")

    elif a.perintah == "putar":
        pemutar = PemutarPeringatan(a.folder)

        hasil = pemutar.umumkan(a.kunci)

        if hasil is None:
            raise SystemExit(f"Klip '{a.kunci}' tidak ada. Contoh: {', '.join(pemutar.daftar_kunci()[:6])} ...")

        print(hasil)

        pemutar.tunggu_selesai()

    else:
        jalankan_simulasi(a.folder)


if __name__ == "__main__":
    main()
