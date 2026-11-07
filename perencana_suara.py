"""Perencana peringatan suara dari pustaka klip ``suara-natural-ai``.

Modul ini hanya membaca ``manifest.json`` dan memilih berkas MP3. Tidak ada
ketergantungan pada pygame atau perangkat audio server, sehingga aman dipakai
oleh FastAPI yang meminta browser memutar suara Ardi sesuai level fuzzy.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path
from typing import Iterable, Optional

ROOT = Path(__file__).resolve().parent
SUARA_DIR = ROOT / "suara-natural-ai"
if str(SUARA_DIR) not in sys.path:
    sys.path.insert(0, str(SUARA_DIR))

from pemutar_peringatan import rencana_peringatan  # noqa: E402

SKEMA_DIDUKUNG = (2, 3)
URUTAN_LEVEL = {"AMAN": 0, "INFO": 1, "WASPADA": 2, "BAHAYA": 3}


class PerencanaSuara:
    """Mengubah hasil deteksi + fuzzy menjadi daftar segmen klip Ardi."""

    def __init__(self, folder: str | Path, seed: Optional[int] = None) -> None:
        self.folder = Path(folder)
        manifest_path = self.folder / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError(f"manifest.json tidak ditemukan di {self.folder}")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        skema = manifest.get("skema")
        if skema not in SKEMA_DIDUKUNG:
            raise ValueError(f"Skema pustaka suara {skema!r} tidak didukung.")

        self.skema = skema
        self.penutur = str(manifest.get("suara", ""))
        self.kelas_dikenal = list(manifest.get("kelas", []))
        self.meta = manifest.get("meta", {})
        self.pesan = manifest.get("pesan", {})

        self._berkas: set[str] = set()
        self._pesan_siap: dict[str, list[dict]] = {}
        for kunci, daftar in self.pesan.items():
            valid = [
                entri
                for entri in daftar
                if str(entri.get("berkas", ""))
                and (self.folder / str(entri["berkas"])).is_file()
            ]
            if valid:
                self._pesan_siap[kunci] = valid
                self._berkas.update(str(entri["berkas"]) for entri in valid)

        self.tersedia = set(self._pesan_siap)
        self._rng = random.Random(seed)
        self._varian_terakhir: dict[str, int] = {}

    @property
    def siap(self) -> bool:
        return bool(self._berkas) and bool(self.tersedia)

    def berkas_diizinkan(self, nama_berkas: str) -> bool:
        return nama_berkas in self._berkas

    def _pilih_varian(self, kunci: str) -> Optional[dict]:
        daftar = self._pesan_siap.get(kunci)
        if not daftar:
            return None
        pilihan = list(range(len(daftar)))
        terakhir = self._varian_terakhir.get(kunci)
        if terakhir in pilihan and len(pilihan) > 1:
            pilihan.remove(terakhir)
        indeks = self._rng.choice(pilihan)
        self._varian_terakhir[kunci] = indeks
        return daftar[indeks]

    def _segmen(self, kunci: str) -> Optional[dict]:
        entri = self._pilih_varian(kunci)
        if entri is None:
            return None
        nama_berkas = str(entri["berkas"])
        return {
            "kunci": kunci,
            "teks": str(entri.get("teks", "")),
            "berkas": nama_berkas,
            "url": f"/suara/{nama_berkas}",
        }

    def _susun_segmen(self, kunci_list: Iterable[str]) -> list[dict]:
        segmen = []
        for kunci in kunci_list:
            bagian = self._segmen(kunci)
            if bagian is not None:
                segmen.append(bagian)
        return segmen

    def susun(self, deteksi: Iterable[dict]) -> Optional[dict]:
        """Kembalikan rencana suara untuk daftar deteksi berurutan urgensi."""
        daftar = [
            d
            for d in deteksi
            if str(d.get("level", "")).upper() != "AMAN"
        ]

        if not daftar:
            bagian = self._segmen("jalur_aman")
            if bagian is None:
                return None
            return {
                "level": "AMAN",
                "teks": bagian["teks"],
                "aksi": "lurus",
                "segmen": [bagian],
            }

        teratas = max(
            daftar,
            key=lambda d: (
                URUTAN_LEVEL.get(str(d.get("level", "")).upper(), 0),
                float(d.get("urgensi", 0.0)),
            ),
        )
        rencana = rencana_peringatan(
            teratas,
            daftar,
            self.kelas_dikenal or None,
            self.tersedia,
        )
        if rencana is None:
            return None

        segmen = self._susun_segmen(rencana["segmen"])
        if not any(bagian["kunci"].startswith("benda_") for bagian in segmen):
            return None

        return {
            "level": str(teratas.get("level", "")).upper(),
            "teks": " ".join(
                bagian["teks"] for bagian in segmen if bagian["teks"]
            ),
            "aksi": rencana.get("aksi"),
            "segmen": segmen,
        }

    def contoh(self) -> Optional[dict]:
        """Rencana contoh untuk tombol tes suara di halaman /app."""
        return self.susun(
            [
                {
                    "kelas": "umum",
                    "level": "WASPADA",
                    "arah": "depan",
                    "urgensi": 60.0,
                    "jarak_m": 1.0,
                }
            ]
        )
