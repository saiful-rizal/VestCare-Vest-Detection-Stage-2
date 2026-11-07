"""Pipeline inferensi VestCare Rompi Cerdas.

Alur:
  gambar/video/webcam
      -> YOLO-seg (model hasil training: models/best.pt)
      -> Fuzzy Sugeno (jarak, bahaya kelas, jalur) -> tingkat urgensi
      -> output suara (PemutarPeringatan dari suara-natural-ai)
      -> (opsional) dikirim ke FastAPI sebagai JSON

File ini bisa dijalankan langsung (CLI) atau diimpor oleh server_rest_api.py.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ---- Fuzzy logic (root) ----
from fuzzysugeno import (  # noqa: E402
    analisis_hasil,
    BAHAYA_KELAS,
    level,
    sugeno,
)

# ---- Model YOLO ----
try:  # ultralytics boleh tidak terpasang di pelanggan API
    from ultralytics import YOLO  # noqa: E402
except Exception:  # pragma: no cover
    YOLO = None  # type: ignore

# ---- Suara (suara-natural-ai) ----
SUARA_DIR = ROOT / "suara-natural-ai"
if str(SUARA_DIR) not in sys.path:
    sys.path.insert(0, str(SUARA_DIR))

try:  # pemutar butuh pygame + pustaka klip manifest.json
    from pemutar_peringatan import PemutarPeringatan  # noqa: E402
except Exception:  # pragma: no cover
    PemutarPeringatan = None  # type: ignore

try:  # fallback TTS jika pustaka klip belum ada
    import edge_tts  # noqa: E402
    from pydub import AudioSegment  # noqa: E402
    import io  # noqa: E402
    import asyncio  # noqa: E402
    _TTS_TERSEDIA = True
except Exception:  # pragma: no cover
    edge_tts = None  # type: ignore
    AudioSegment = None  # type: ignore
    io = None  # type: ignore
    asyncio = None  # type: ignore
    _TTS_TERSEDIA = False

DEFAULT_MODEL = ROOT / "models" / "best.pt"
DEFAULT_SUARA_FOLDER = ROOT / "cache_suara"
DEFAULT_CONF = 0.35
DEFAULT_IMGSZ = 416

URUSAN_PRIORITAS = {"AMAN": 0, "INFO": 1, "WASPADA": 2, "BAHAYA": 3}

# Pesan teks default per level (dibacakan TTS jika klip tidak tersedia)
PESAN_TTS_DEFAULT = {
    "AMAN": "Jalur aman, silakan lanjut berjalan.",
    "INFO": "Hati-hati, ada rintangan di dekat, berjalanlah pelan-pelan.",
    "WASPADA": "Waspada, ada rintangan cukup dekat, kurangi kecepatan dan berhati-hati.",
    "BAHAYA": "Awas, bahaya di depan, segera berhenti dan cari jalur yang aman.",
}


@dataclass
class HasilDeteksi:
    kelas: str
    arah: str
    jarak_m: float
    urgensi: float
    level: str
    conf: float
    sumber: str
    pesan: str
    getar: dict = field(default_factory=dict)


@dataclass
class HasilInferensi:
    waktu: str
    jumlah_objek: int
    deteksi: list[HasilDeteksi]
    teratas: Optional[HasilDeteksi]
    level_tertinggi: str
    urgensi_tertinggi: float
    aksi_suara: Optional[str] = None
    suara_diputar: bool = False


class TTSFallback:
    """Pemutar suara sederhana dengan edge-tts (Teks -> Suara alami Indonesia).

    Digunakan sebagai cadangan jika pustaka klip suara-natural-ai belum tersedia.
    Butuh edge-tts, pydub, dan FFmpeg terpasang.
    """

    def __init__(self, suara: str = "id-ID-GadisNeural"):
        self.suara = suara
        self.terbaru: Optional[str] = None

    async def _sintesis(self, teks: str):
        komunikator = edge_tts.Communicate(teks, self.suara)
        buffer = bytearray()
        async for potongan in komunikator.stream():
            if potongan["type"] == "audio":
                buffer.extend(potongan["data"])
        return AudioSegment.from_file(io.BytesIO(bytes(buffer)), format="mp3")

    def ucapkan(self, teks: str) -> bool:
        if not _TTS_TERSEDIA:
            print(f"[TTS] (tidak bisa diputar, pustaka TTS tidak lengkap): {teks}")
            return False
        try:
            audio = asyncio.run(self._sintesis(teks))
            # Putar melalui pygame jika tersedia, else simpan ke file sementara.
            import pygame
            pygame.mixer.init()
            pygame.mixer.music.load(io.BytesIO(audio.export(format="mp3").read()))
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy():
                time.sleep(0.05)
            self.terbaru = teks
            return True
        except Exception as e:  # pragma: no cover - pemutaran audio sangat bergantung hardware
            print(f"[TTS] gagal memutar: {e}")
            return False


class InferensiVest:
    """Deteksi objek + fuzzy urgensi + output suara untuk rompi tunanetra."""

    def __init__(
        self,
        model_path: str | Path = DEFAULT_MODEL,
        suara_folder: str | Path = DEFAULT_SUARA_FOLDER,
        conf: float = DEFAULT_CONF,
        imgsz: int = DEFAULT_IMGSZ,
        device: Optional[str] = None,
        paksa_tts_fallback: bool = False,
    ) -> None:
        from datetime import datetime

        self.model_path = Path(model_path)
        self.suara_folder = Path(suara_folder)
        self.conf = conf
        self.imgsz = imgsz
        self.device = device
        self.waktu_mulai = datetime.now()

        if YOLO is None:
            raise RuntimeError("ultralytics belum terpasang; jalankan: pip install -r requirements.txt")
        if not self.model_path.exists():
            raise FileNotFoundError(f"Bobot model tidak ditemukan: {self.model_path}")

        print(f"[INFERENSI] Memuat model {self.model_path} ...")
        self.model = YOLO(str(self.model_path))
        print(f"[INFERENSI] Model siap. Kelas: {self.model.names}")

        # Inisialisasi pemutar suara
        self.pemutar: Optional[PemutarPeringatan] = None
        self.tts_fallback: Optional[TTSFallback] = None
        self._inisialisasi_suara(paksa_tts_fallback)

    def _inisialisasi_suara(self, paksa_fallback: bool) -> None:
        # Coba pemutar klip suara-natural-ai dulu.
        if not paksa_fallback and PemutarPeringatan is not None and self.suara_folder.is_dir():
            manifest = self.suara_folder / "manifest.json"
            if manifest.exists():
                try:
                    self.pemutar = PemutarPeringatan(str(self.suara_folder))
                    print(f"[SUARA] Pemutar klip siap: {self.suara_folder}")
                    return
                except Exception as e:
                    print(f"[SUARA] Gagal buka klip ({e}); coba TTS fallback.")
            else:
                print(f"[SUARA] manifest.json tidak ada di {self.suara_folder}.")
        else:
            print("[SUARA] Pemutar klip tidak tersedia / dipaksa fallback TTS.")

        # Fallback TTS langsung (edge-tts).
        if _TTS_TERSEDIA:
            self.tts_fallback = TTSFallback()
            print("[SUARA] TTS fallback (edge-tts) siap.")
        else:
            print("[SUARA] Peringatan: tidak ada pemutar suara tersedia (butuh pygame atau edge-tts + FFmpeg).")

    # ------------------------------------------------------------------ deteksi

    def deteksi_gambar(
        self,
        gambar: np.ndarray,
        jarak_us: Optional[float] = None,
        conf_min: Optional[float] = None,
    ) -> HasilInferensi:
        """Jalankan deteksi pada satu frame gambar (numpy BGR/RGB)."""
        from datetime import datetime

        conf = self.conf if conf_min is None else conf_min
        hasil = self.model.predict(
            source=gambar,
            imgsz=self.imgsz,
            conf=conf,
            verbose=False,
        )[0]

        daftar_mentah = analisis_hasil(
            hasil,
            conf_min=conf,
            jarak_us=jarak_us,
        )

        deteksi = [
            HasilDeteksi(
                kelas=d["kelas"],
                arah=d["arah"],
                jarak_m=d["jarak_m"],
                urgensi=d["urgensi"],
                level=d["level"],
                conf=d["conf"],
                sumber=d["sumber"],
                pesan=d["pesan"],
                getar=d.get("getar", {}),
            )
            for d in daftar_mentah
        ]

        # Urutkan menurun menurut urgensi.
        deteksi.sort(key=lambda d: -d.urgensi)

        teratas = deteksi[0] if deteksi else None
        level_tertinggi = teratas.level if teratas else "AMAN"
        urgensi_tertinggi = teratas.urgensi if teratas else 0.0

        return HasilInferensi(
            waktu=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            jumlah_objek=len(deteksi),
            deteksi=deteksi,
            teratas=teratas,
            level_tertinggi=level_tertinggi,
            urgensi_tertinggi=urgensi_tertinggi,
        )

    # ------------------------------------------------------------------ suara

    def putar_suara(self, hasil: HasilInferensi) -> Optional[str]:
        """Putar peringatan suara berdasarkan hasil inferensi. Return teks yang diucapkan."""
        if hasil.jumlah_objek == 0 or hasil.teratas is None:
            # Tidak ada ancaman -> ucapkan jalur aman (opsional, hanya sekali).
            return None

        # Bangun daftar dict kompatibel dengan pemutar_peringatan.
        daftar = [
            {
                "kelas": d.kelas,
                "level": d.level,
                "arah": d.arah,
                "urgensi": d.urgensi,
                "jarak_m": d.jarak_m,
                "conf": d.conf,
                "sumber": d.sumber,
                "gerak": None,
            }
            for d in hasil.deteksi
            if d.level.upper() != "AMAN"
        ]

        if self.pemutar is not None:
            teks = self.pemutar.umumkan_analisis(daftar)
            if teks is not None:
                return teks
            # Jika pemutar klip tidak mengucapkan apa-apa (cooldown), tetap beri fallback TTS.

        if self.tts_fallback is not None:
            teratas = hasil.teratas
            teks = PESAN_TTS_DEFAULT.get(teratas.level.upper(), PESAN_TTS_DEFAULT["AMAN"])
            detail = f"{teratas.kelas} di {teratas.arah}, sekitar {teratas.jarak_m:.1f} meter."
            penuh = f"{teks} {detail}"
            self.tts_fallback.ucapkan(penuh)
            return penuh

        return None

    # ------------------------------------------------------------------ serialisasi

    def ke_dict(self, hasil: HasilInferensi) -> dict:
        return {
            "waktu": hasil.waktu,
            "jumlah_objek": hasil.jumlah_objek,
            "level_tertinggi": hasil.level_tertinggi,
            "urgensi_tertinggi": round(hasil.urgensi_tertinggi, 1),
            "aksi_suara": hasil.aksi_suara,
            "suara_diputar": hasil.suara_diputar,
            "deteksi": [
                {
                    "kelas": d.kelas,
                    "arah": d.arah,
                    "jarak_m": d.jarak_m,
                    "urgensi": round(d.urgensi, 1),
                    "level": d.level,
                    "conf": round(d.conf, 2),
                    "sumber": d.sumber,
                    "pesan": d.pesan,
                    "getar": d.getar,
                }
                for d in hasil.deteksi
            ],
        }


def jalankan_cli(
    sumber: str = "0",
    model_path: str | Path = DEFAULT_MODEL,
    suara_folder: str | Path = DEFAULT_SUARA_FOLDER,
    jarak: Optional[float] = None,
    conf: float = DEFAULT_CONF,
    imgsz: int = DEFAULT_IMGSZ,
    device: Optional[str] = None,
    tanpa_suara: bool = False,
) -> None:
    """Jalankan deteksi real-time dari webcam/video/gambar dengan output suara."""
    import cv2

    engine = InferensiVest(
        model_path=model_path,
        suara_folder=None if tanpa_suara else suara_folder,
        conf=conf,
        imgsz=imgsz,
        device=device,
    )

    print(f"[CLI] Sumber: {sumber} | Tekan 'q' untuk keluar.")
    cap = cv2.VideoCapture(int(sumber) if sumber.isdigit() else sumber)
    if not cap.isOpened():
        raise SystemExit(f"Tidak bisa membuka sumber video: {sumber}")

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            jarak_us = jarak  # override jarak tetap jika diinginkan
            hasil = engine.deteksi_gambar(frame, jarak_us=jarak_us)

            if not tanpa_suara:
                teks = engine.putar_suara(hasil)
                if teks:
                    hasil.aksi_suara = teks
                    hasil.suara_diputar = True
                    print(f"[SUARA] {teks}")

            # Gambar overlay di frame.
            for i, d in enumerate(hasil.deteksi):
                warna = (0, 0, 255) if d.urgensi >= 75 else (0, 200, 255)
                teks_overlay = f"{d.kelas} {d.level} {d.urgensi:.0f} | {d.jarak_m:.1f}m"
                cv2.putText(
                    frame,
                    teks_overlay,
                    (10, 30 + i * 28),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    warna,
                    2,
                    cv2.LINE_AA,
                )
            if hasil.jumlah_objek == 0:
                cv2.putText(
                    frame,
                    "Tidak ada deteksi",
                    (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.7,
                    (180, 180, 180),
                    2,
                    cv2.LINE_AA,
                )
            cv2.putText(
                frame,
                f"Level: {hasil.level_tertinggi} | Urgensi: {hasil.urgensi_tertinggi:.0f}",
                (10, frame.shape[0] - 20),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 255, 0),
                2,
                cv2.LINE_AA,
            )

            cv2.imshow("VestCare - Deteksi + Fuzzy + Suara", frame)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        print("[CLI] Selesai.")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="VestCare: deteksi + fuzzy urgensi + suara.")
    ap.add_argument("--source", default="0", help="0 untuk webcam, atau path gambar/video.")
    ap.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Path bobot .pt hasil training.")
    ap.add_argument("--suara", type=Path, default=DEFAULT_SUARA_FOLDER, help="Folder pustaka klip suara.")
    ap.add_argument("--jarak", type=float, default=None, help="Override jarak ultrasonik (meter).")
    ap.add_argument("--conf", type=float, default=DEFAULT_CONF, help="Confidence minimum YOLO.")
    ap.add_argument("--imgsz", type=int, default=DEFAULT_IMGSZ, help="Ukuran inferensi YOLO.")
    ap.add_argument("--device", default=None, help="Device (mis. 0 untuk GPU).")
    ap.add_argument("--tanpa-suara", action="store_true", help="Matikan output suara.")
    args = ap.parse_args()

    jalankan_cli(
        sumber=args.source,
        model_path=args.model,
        suara_folder=args.suara,
        jarak=args.jarak,
        conf=args.conf,
        imgsz=args.imgsz,
        device=args.device,
        tanpa_suara=args.tanpa_suara,
    )
