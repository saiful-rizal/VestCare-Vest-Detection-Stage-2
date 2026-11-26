from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import math
import os
import random
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time
import urllib.parse
import uuid
from collections import deque
from collections.abc import (
    Awaitable,
    AsyncGenerator,
    AsyncIterator,
    Callable,
    Iterable,
    Mapping,
)
from contextlib import asynccontextmanager, suppress
from dataclasses import dataclass
from datetime import datetime
from http import HTTPStatus
from pathlib import Path
from typing import Any, Optional, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

import numpy as np
from fastapi import (
    BackgroundTasks,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from ultralytics.engine.results import Results

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("vestcare")

ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "web" / "react" / "dist"
DASHBOARD_INDEX = DASHBOARD_DIR / "index.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

JsonRecord = dict[str, Any]

def load_project_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        konten = env_path.read_text(encoding="utf-8-sig")
    except OSError as error:
        print(f"[ENV] .env tidak dapat dibaca: {error}")
        return
    for line_number, raw_line in enumerate(konten.splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            print(f"[ENV] Baris {line_number} dilewati karena format tidak valid.")
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)

load_project_env()


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_DEVICE_ID_ENV = os.environ.get("VEST_SUPABASE_DEVICE_ID", "").strip()
SUPABASE_DEVICE_FALLBACK = str(uuid.uuid5(uuid.NAMESPACE_URL, "vestcare-server-device"))
supabase_device_id = SUPABASE_DEVICE_ID_ENV or SUPABASE_DEVICE_FALLBACK
SUPABASE_SYNC_LOCK = threading.Lock()
supabase_last_signature = ""
supabase_last_saved_at = 0.0
supabase_connected = False
supabase_connection_error: Optional[str] = None
supabase_next_retry_at = 0.0

RIWAYAT_LOCK = threading.Lock()

LATEST_TELEMETRI_LOCK = threading.Lock()
LATEST_TELEMETRI: dict[str, Any] = {
    "jarak": None,
    "valid_jarak": False,
    "lat": None,
    "lng": None,
    "alt": None,
    "spd": None,
    "sat": 0,
    "hdop": None,
    "fix": False,
    "terbaca": False,
    "waktu": None,
    "battery": None,
    "updated_at": 0.0,
    "last_seen_at": 0.0,
}
latest_gps_log_at = 0.0
last_device_update_at = 0.0

LATEST_DETEKSI_LOCK = threading.Lock()
LATEST_DETEKSI: dict[str, Any] = {
    "updated_at": 0.0,
    "data": None,
}

ESP32_FRAME_CONDITION = threading.Condition()
esp32_frame_bytes: Optional[bytes] = None
esp32_frame_sequence = 0
esp32_frame_updated_at = 0.0

TELEMETRI_JALUR_LOCK = threading.Lock()
TELEMETRI_JALUR: deque[dict[str, Any]] = deque(maxlen=300)


def api_key_is_configured(value: Optional[str]) -> bool:
    if value is None or len(value.strip()) < 32:
        return False
    normalized = value.strip().lower()
    return not any(marker in normalized for marker in ("contoh", "ganti", "rahasia-anda"))


DEFAULT_MODEL = ROOT / "models" / "best.pt"
DEFAULT_SUARA_FOLDER = ROOT / "data" / "runtime" / "audio" / "cache_ardi"
DEFAULT_CONF = 0.35
DEFAULT_CONF_RAGU = 0.50
DEFAULT_IMGSZ = 512
ALERT_FRONT_DISTANCE_M = 0.5

from fuzzysugeno import (
    KELAS_ID_KE_NAMA,
    KELAS_INTERNAL_MODEL,
    PelacakGerak,
    analisis_hasil,
    validasi_nama_kelas,
)
from ultralytics import YOLO


@dataclass
class HasilInferensi:
    waktu: str
    deteksi: list[JsonRecord]
    aksi_suara: Optional[str] = None
    suara_diputar: bool = False

    @property
    def jumlah_objek(self) -> int:
        return len(self.deteksi)

    @property
    def deteksi_yakin(self) -> list[JsonRecord]:
        return [item for item in self.deteksi if not item.get("ragu")]

    @property
    def jumlah_ragu(self) -> int:
        return len(self.deteksi) - len(self.deteksi_yakin)

    @property
    def level_tertinggi(self) -> str:
        yakin = self.deteksi_yakin
        return yakin[0]["level"] if yakin else "AMAN"

    @property
    def urgensi_tertinggi(self) -> float:
        yakin = self.deteksi_yakin
        return float(yakin[0]["urgensi"]) if yakin else 0.0


class InferensiVest:
    def __init__(self, model_path: Path, conf: float, imgsz: int,
                 conf_ragu: float = DEFAULT_CONF_RAGU) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"Bobot model tidak ditemukan: {model_path}")
        self.conf = conf
        self.conf_ragu = conf_ragu
        self.imgsz = imgsz
        self.pelacak = PelacakGerak()
        self.model = YOLO(str(model_path))
        nama_kelas = cast(
            Mapping[int, str] | list[str] | tuple[str, ...],
            self.model.names,
        )
        nama_kelas_valid = validasi_nama_kelas(nama_kelas)
        self.kelas_prediksi = sorted(
            class_id
            for class_id in nama_kelas_valid
            if class_id in KELAS_ID_KE_NAMA or class_id in KELAS_INTERNAL_MODEL
        )

    def deteksi_gambar(self, gambar: np.ndarray, jarak_us: Optional[float] = None,
                       conf_min: Optional[float] = None) -> HasilInferensi:
        conf = self.conf if conf_min is None else conf_min
        predict = cast(
            Callable[..., Iterable[Results]],
            getattr(self.model, "predict"),
        )
        prediksi = predict(
            source=gambar,
            imgsz=self.imgsz,
            conf=conf,
            classes=self.kelas_prediksi,
            verbose=False,
        )
        hasil_model = next(iter(prediksi), None)
        if not isinstance(hasil_model, Results):
            raise RuntimeError("Model tidak menghasilkan objek hasil deteksi.")
        deteksi: list[JsonRecord] = analisis_hasil(
            hasil_model,
            conf_min=conf,
            jarak_us=jarak_us,
            conf_ragu=self.conf_ragu,
        )
        self.pelacak.perbarui(deteksi)
        deteksi.sort(key=lambda item: -item["urgensi"])
        return HasilInferensi(
            waktu=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            deteksi=deteksi,
        )

    @staticmethod
    def ke_dict(hasil: HasilInferensi) -> JsonRecord:
        close_front_object = any(
            item.get("arah") == "depan"
            and isinstance(item.get("jarak_m"), (int, float))
            and 0 <= item["jarak_m"] < ALERT_FRONT_DISTANCE_M
            for item in hasil.deteksi_yakin
        )
        alert = {"BAHAYA": 2, "WASPADA": 1}.get(hasil.level_tertinggi, 0)
        if close_front_object:
            alert = 2

        return {
            "waktu": hasil.waktu,
            "jumlah_objek": hasil.jumlah_objek,
            "jumlah_objek_yakin": len(hasil.deteksi_yakin),
            "jumlah_ragu": hasil.jumlah_ragu,
            "level_tertinggi": hasil.level_tertinggi,
            "urgensi_tertinggi": round(hasil.urgensi_tertinggi, 1),
            "alert": alert,
            "aksi_suara": hasil.aksi_suara,
            "suara_diputar": hasil.suara_diputar,
            "deteksi": hasil.deteksi,
        }

class PerencanaSuara:
    URUTAN_LEVEL = {"AMAN": 0, "INFO": 1, "WASPADA": 2, "BAHAYA": 3}

    def __init__(self, folder: Path) -> None:
        manifest_path = folder / "manifest.json"
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest_data, dict):
            raise ValueError(f"Format manifest suara tidak valid: {manifest_path}")
        manifest: JsonRecord = cast(JsonRecord, manifest_data)
        if manifest.get("skema") not in (2, 3):
            raise ValueError(f"Skema pustaka suara {manifest.get('skema')!r} tidak didukung.")
        self.folder = folder
        self.penutur = str(manifest.get("suara", ""))
        kelas = manifest.get("kelas", [])
        if not isinstance(kelas, list) or not all(
            isinstance(item, str) for item in cast(list[Any], kelas)
        ):
            raise ValueError(f"Format kelas manifest suara tidak valid: {manifest_path}")
        self.kelas_dikenal: set[str] = set(cast(list[str], kelas))
        self._pesan_siap: dict[str, list[JsonRecord]] = {}
        self._berkas: set[str] = set()
        self._varian_terakhir: dict[str, int] = {}
        self._rng = random.Random()
        pesan_data = manifest.get("pesan", {})
        if not isinstance(pesan_data, dict):
            raise ValueError(f"Format pesan manifest suara tidak valid: {manifest_path}")
        pesan = cast(JsonRecord, pesan_data)
        for key, entries in pesan.items():
            if not isinstance(entries, list):
                raise ValueError(f"Format entri manifest suara tidak valid: {manifest_path}")
            entries = cast(list[Any], entries)
            valid: list[JsonRecord] = []
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                entry = cast(JsonRecord, entry)
                berkas = entry.get("berkas")
                if (
                    isinstance(berkas, str)
                    and berkas
                    and str(entry.get("teks", "")).strip()
                    and (folder / berkas).is_file()
                ):
                    valid.append(entry)
            if valid:
                self._pesan_siap[key] = valid
                self._berkas.update(str(entry["berkas"]) for entry in valid)
        self.tersedia: set[str] = set(self._pesan_siap)
        wajib = {"jalur_aman", "awal_waspada", "awal_bahaya"}
        wajib.update(
            f"benda_{kelas}_{arah}_netral"
            for kelas in (*KELAS_ID_KE_NAMA.values(), "umum")
            for arah in ("kiri", "depan", "kanan")
        )
        wajib.update(f"jarak_{jarak:02d}" for jarak in range(5, 51, 5))
        wajib.update(
            f"solusi_{aksi}"
            for aksi in (
                "lurus",
                "pelan",
                "pelan_kiri",
                "pelan_kanan",
                "berhenti",
                "berhenti_kiri",
                "berhenti_kanan",
            )
        )
        hilang = sorted(wajib - self.tersedia)
        if hilang:
            raise ValueError(f"Klip suara atau teks wajib belum tersedia: {', '.join(hilang)}")

    def berkas_diizinkan(self, nama_berkas: str) -> bool:
        return nama_berkas in self._berkas

    def _segmen(self, key: str) -> Optional[JsonRecord]:
        entries = self._pesan_siap.get(key)
        if not entries:
            return None
        choices = [index for index in range(len(entries))
                   if len(entries) == 1 or index != self._varian_terakhir.get(key)]
        index = self._rng.choice(choices)
        self._varian_terakhir[key] = index
        entry = entries[index]
        name = entry["berkas"]
        return {
            "kunci": key,
            "teks": str(entry.get("teks", "")),
            "berkas": name,
            "url": f"/suara/{name}",
        }

    @staticmethod
    def _aksi(top: Mapping[str, Any], detections: Iterable[Mapping[str, Any]]) -> str:
        level_name = str(top.get("level", "")).upper()
        direction = top.get("arah", "depan")
        occupied = {
            item.get("arah") for item in detections
            if str(item.get("level", "")).upper() != "AMAN"
        } | {direction}
        if direction in ("kiri", "kanan"):
            opposite = "kanan" if direction == "kiri" else "kiri"
            if level_name == "INFO":
                return "lurus"
            if opposite in occupied:
                return "berhenti" if level_name == "BAHAYA" else "pelan"
            return ("berhenti_" if level_name == "BAHAYA" else "pelan_") + opposite
        free_sides = [side for side in ("kiri", "kanan") if side not in occupied]
        if level_name == "INFO":
            return "pelan"
        if level_name == "BAHAYA":
            return f"berhenti_{free_sides[0]}" if len(free_sides) == 1 else "berhenti"
        if len(free_sides) == 1:
            return f"pelan_{free_sides[0]}"
        if len(free_sides) == 2:
            return "pelan_kiri"
        return "pelan"

    def susun(self, detections: list[JsonRecord]) -> Optional[JsonRecord]:
        if not detections:
            safe = self._segmen("jalur_aman")
            return {
                "level": "AMAN",
                "teks": safe["teks"],
                "aksi": "lurus",
                "segmen": [safe],
            } if safe else None

        yakin = [item for item in detections if not item.get("ragu")]
        if not yakin:
            return None

        active = [item for item in yakin if str(item.get("level", "")).upper() != "AMAN"]
        if not active:
            active = yakin
        top = max(
            active,
            key=lambda item: (
                self.URUTAN_LEVEL.get(str(item.get("level", "")).upper(), 0),
                float(item.get("urgensi", 0.0)),
            ),
        )
        class_name = str(top.get("kelas", "umum"))
        if class_name not in self.kelas_dikenal:
            class_name = "umum"
        direction = top.get("arah", "depan")
        level_name = str(top.get("level", "")).lower()
        gerak = str(top.get("gerak") or "netral")
        if gerak not in ("bergerak", "diam"):
            gerak = "netral"
        keys: list[str] = []
        if level_name in ("waspada", "bahaya"):
            keys.append(f"awal_{level_name}")
        benda_key = f"benda_{class_name}_{direction}_{gerak}"
        if benda_key not in self._pesan_siap:
            benda_key = f"benda_{class_name}_{direction}_netral"
        keys.append(benda_key)
        if top.get("jarak_m") is not None:
            distance_bucket = min(50, max(5, int(float(top["jarak_m"]) * 2 + 0.5) * 5))
            if float(top["jarak_m"]) < 0.75:
                distance_bucket = 5
            keys.append(f"jarak_{distance_bucket:02d}")
        action = self._aksi(top, active)
        keys.append(f"solusi_{action}")
        segments: list[JsonRecord] = [
            part for key in keys if (part := self._segmen(key)) is not None
        ]
        if not any(part["kunci"].startswith("benda_") for part in segments):
            return None
        return {
            "level": level_name.upper(),
            "teks": " ".join(part["teks"] for part in segments if part["teks"]),
            "aksi": action,
            "gerak": gerak,
            "segmen": segments,
        }

    def contoh(self) -> Optional[JsonRecord]:
        return self.susun([{
            "kelas": "umum",
            "level": "WASPADA",
            "arah": "depan",
            "urgensi": 60.0,
            "jarak_m": 1.0,
        }])

API_KEY = os.environ.get("VEST_API_KEY", "").strip()
API_KEY_CONFIGURED = api_key_is_configured(API_KEY)


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


model_path = _project_path(os.environ.get("VEST_MODEL_PATH", DEFAULT_MODEL))
if not model_path.is_file():
    trained_model = (
        ROOT / "data" / "results" / "runs" / "segment" / "runs"
        / "semua_kelas_yolo26n" / "weights" / "best.pt"
    )
    if trained_model.is_file():
        model_path = trained_model
SUARA_FOLDER = _project_path(os.environ.get("VEST_SUARA_FOLDER", DEFAULT_SUARA_FOLDER))


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except (TypeError, ValueError):
        print(f"[KONFIG] {name} tidak valid; memakai nilai default {default}.")
        return default


def _env_float(name: str, default: float) -> float:
    try:
        value = float(os.environ.get(name, str(default)))
        if not math.isfinite(value):
            raise ValueError("nilai harus finite")
        return value
    except (TypeError, ValueError):
        print(f"[KONFIG] {name} tidak valid; memakai nilai default {default}.")
        return default


IMGSZ = _env_int("VEST_IMGSZ", DEFAULT_IMGSZ)
CONF = _env_float("VEST_CONF", DEFAULT_CONF)
CONF_RAGU = _env_float("VEST_CONF_RAGU", DEFAULT_CONF_RAGU)
riwayat_path = _project_path(
    os.environ.get("VEST_RIWAYAT_PATH", ROOT / "data" / "runtime" / "riwayat.jsonl")
)
# Riwayat lokal tidak boleh tumbuh tanpa batas: file besar membuat polling
# /riwayat dan dashboard makin lambat serta menghabiskan disk container.
RIWAYAT_MAX_BYTES = max(256 * 1024, _env_int("VEST_RIWAYAT_MAX_BYTES", 5 * 1024 * 1024))
RIWAYAT_KEEP_ENTRIES = max(100, _env_int("VEST_RIWAYAT_KEEP_ENTRIES", 4000))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
PORT = _env_int("PORT", _env_int("VEST_PORT", 8080))
ENABLE_LAN_DISCOVERY = os.environ.get("VEST_ENABLE_LAN_DISCOVERY", "1").strip().lower() in {
    "1",
    "true",
    "yes",
}
ESP32_DISCOVERY_PORT = 4211
GOOGLE_MAPS_API_KEY = (
    os.environ.get("GOOGLE_MAPS_API_KEY", "")
    or os.environ.get("VITE_GOOGLE_MAPS_API_KEY", "")
).strip()
MAP_DEFAULT_LAT = _env_float("VEST_MAP_DEFAULT_LAT", -8.1689)
MAP_DEFAULT_LNG = _env_float("VEST_MAP_DEFAULT_LNG", 113.7020)
MAP_DEFAULT_ZOOM = _env_int("VEST_MAP_ZOOM", 17)

try:
    riwayat_path.parent.mkdir(parents=True, exist_ok=True)
except OSError as error:
    fallback = Path(tempfile.gettempdir()) / "vestcare" / "riwayat.jsonl"
    print(
        f"[RIWAYAT] Folder {riwayat_path.parent} tidak dapat dibuat "
        f"({error}); memakai {fallback}."
    )
    riwayat_path = fallback
    riwayat_path.parent.mkdir(parents=True, exist_ok=True)

COOKIE_SESI = "vestcare_sesi"
UMUR_SESI_DETIK = 12 * 60 * 60

try:
    perencana_suara: Optional[PerencanaSuara] = (
        PerencanaSuara(SUARA_FOLDER) if (SUARA_FOLDER / "manifest.json").is_file() else None
    )
    if perencana_suara is None:
        raise FileNotFoundError(f"manifest.json tidak ditemukan di {SUARA_FOLDER}")
    print(
        f"[SUARA] Pustaka browser siap: {SUARA_FOLDER} "
        f"({len(perencana_suara.tersedia)} kunci, penutur {perencana_suara.penutur or '-'})"
    )
except Exception as e:
    perencana_suara = None
    print(f"[SUARA] Pustaka browser nonaktif: {e}")

engine: Optional[InferensiVest] = None
engine_error: Optional[str] = None
INFERENSI_LOCK = threading.Lock()
try:
    engine = InferensiVest(
        model_path=model_path,
        conf=CONF,
        imgsz=IMGSZ,
        conf_ragu=CONF_RAGU,
    )
    print(f"[API] Engine inferensi siap. Model: {model_path}")
except Exception as e:
    engine_error = str(e)
    logger.error("[API] Engine tidak dapat dimuat: %s", engine_error)
    logger.error("  /deteksi akan menolak request sampai engine berhasil dimuat.")

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None, None]:
    discovery_stop = threading.Event()
    discovery_thread: Optional[threading.Thread] = None
    if ENABLE_LAN_DISCOVERY:
        discovery_thread = threading.Thread(
            target=_layani_penemuan_esp32,
            args=(discovery_stop,),
            name="esp32-discovery",
            daemon=True,
        )
        discovery_thread.start()

    # Sinkronisasi Supabase berjalan di latar belakang. Server dan kamera harus
    # tetap siap walaupun Supabase lambat, sedang offline, atau belum diisi.
    supabase_task = asyncio.create_task(_sinkron_supabase_latar())
    try:
        yield
    finally:
        discovery_stop.set()
        if discovery_thread is not None:
            discovery_thread.join(timeout=2)
        supabase_task.cancel()
        with suppress(asyncio.CancelledError):
            await supabase_task


async def _sinkron_supabase_latar() -> None:
    try:
        await hubungkan_supabase_saat_server_mulai()
    except asyncio.CancelledError:
        raise
    except Exception as error:  # noqa: BLE001 - jangan pernah menggagalkan startup
        _tandai_supabase_gagal(error)
        logger.info("[SUPABASE] Sinkronisasi latar belakang tertunda: %s", error)


def _layani_penemuan_esp32(stop_event: threading.Event) -> None:
    """UDP discovery responder — compatible with the ESP32-S3 firmware.

    The ESP32 sends "VESTCARE_DISCOVER_V1 <nonce>" as a broadcast on port 4211.
    The server replies with a signed response so the ESP32 can trust the URL:

        VESTCARE_URL_V1\n<nonce>\n<public_url>\n<hmac_signature>\n

    The public_url is read from data/runtime/public_url.txt (written by
    server.py when a Cloudflare / ngrok / Railway tunnel is active).  If the
    file is missing or empty we fall back to `http://<local-ip>:<PORT>` for
    pure LAN setups, but the ESP32 firmware only accepts https:// URLs for
    signature validation, so a tunnel is typically required.
    """
    import re
    public_url_path = ROOT / "data" / "runtime" / "public_url.txt"

    def _dapatkan_url_publik() -> Optional[str]:
        def normalisasi(url: str) -> Optional[str]:
            kandidat = url.strip().rstrip("/")
            if not kandidat:
                return None
            if "://" not in kandidat:
                kandidat = f"https://{kandidat}"
            parsed = urllib.parse.urlsplit(kandidat)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                return None
            return kandidat

        # 1) Try the file written by server.py / cloudflared monitor
        if public_url_path.is_file():
            try:
                url = normalisasi(public_url_path.read_text(encoding="utf-8"))
            except OSError as error:
                logger.info("[DISCOVERY] URL publik tidak dapat dibaca: %s", error)
                url = None
            if url:
                return url
        # 2) Explicit override, followed by Railway's generated public domain.
        env_url = os.environ.get("VEST_PUBLIC_URL", "").strip().rstrip("/")
        if env_url:
            url = normalisasi(env_url)
            if url:
                return url
        railway_domain = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain:
            url = normalisasi(railway_domain)
            if url:
                return url
        # 3) No HTTPS URL available — LAN-only mode
        return None

    def _tanda_tangan(nonce: str, url: str) -> str:
        pesan = f"{nonce}\n{url}".encode("utf-8")
        return hmac.new(API_KEY.encode("utf-8"), pesan, hashlib.sha256).hexdigest()

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as discovery_socket:
            discovery_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            discovery_socket.bind(("0.0.0.0", ESP32_DISCOVERY_PORT))
            discovery_socket.settimeout(0.5)
            logger.info("[DISCOVERY] Menunggu ESP32 pada UDP port %d.", ESP32_DISCOVERY_PORT)
            while not stop_event.is_set():
                try:
                    data, address = discovery_socket.recvfrom(128)
                except socket.timeout:
                    continue
                except OSError:
                    if not stop_event.is_set():
                        logger.info("[DISCOVERY] Socket error; discovery berhenti.")
                    return

                try:
                    parts = data.decode("ascii").strip().split()
                except UnicodeDecodeError:
                    continue

                if (
                    len(parts) != 2
                    or parts[0] != "VESTCARE_DISCOVER_V1"
                    or not re.fullmatch(r"[0-9a-f]{32}", parts[1])
                ):
                    continue

                public_url = _dapatkan_url_publik()
                if public_url is None:
                    continue

                nonce = parts[1]
                signature = _tanda_tangan(nonce, public_url)
                response = f"VESTCARE_URL_V1\n{nonce}\n{public_url}\n{signature}\n"
                try:
                    discovery_socket.sendto(response.encode("ascii"), address)
                    logger.info("[DISCOVERY] Menjawab ESP32 dari %s dengan URL %s", address[0], public_url)
                except OSError as error:
                    logger.info("[DISCOVERY] Balasan discovery tertunda: %s", error)
    except OSError as error:
        if not stop_event.is_set():
            logger.info("[DISCOVERY] Layanan penemuan ESP32 nonaktif: %s", error)


app = FastAPI(
    title="VestCare API",
    description=(
        "Deteksi objek jalan (YOLO-seg) + fuzzy urgensi (Sugeno) + output suara "
        "untuk rompi tunanetra. Dapat diterbitkan melalui Railway, Cloudflare, "
        "atau jaringan lokal."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — dashboard utama memakai same-origin. Origin tambahan dapat diatur
# lewat VEST_CORS_ORIGINS (dipisah koma) untuk frontend yang di-host terpisah.
# Wildcard + credentials adalah kombinasi tidak valid di browser, jadi
# credentials hanya diaktifkan saat origin dibatasi secara eksplisit.
# ---------------------------------------------------------------------------
CORS_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("VEST_CORS_ORIGINS", "*").split(",")
    if origin.strip()
] or ["*"]
CORS_ALLOW_ALL = "*" in CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=not CORS_ALLOW_ALL,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["ETag", "X-Request-Id"],
)


@app.middleware("http")
async def log_request_http(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    if request.method not in {"GET", "POST"}:
        return await call_next(request)

    mulai = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        durasi_ms = (time.perf_counter() - mulai) * 1000
        logger.error(
            "[HTTP] %s %s gagal (%.1f ms)",
            request.method,
            request.url.path,
            durasi_ms,
        )
        raise

    durasi_ms = (time.perf_counter() - mulai) * 1000
    logger.info(
        "[HTTP] %s %s -> %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        durasi_ms,
    )
    return response


# ---------------------------------------------------------------------------
# Global exception handler — tangkap semua error tak terduga ke JSON
# ---------------------------------------------------------------------------
@app.exception_handler(Exception)
async def global_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "Terjadi kesalahan internal pada server VestCare.",
            "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
    )


def _kode_error_http(exc: HTTPException) -> str:
    detail: Any = exc.detail
    if isinstance(detail, str) and detail.strip():
        return detail
    if isinstance(detail, Mapping):
        status: object = cast(Mapping[str, object], detail).get("status")
        if isinstance(status, str) and status.strip():
            return status
    try:
        return HTTPStatus(exc.status_code).name.lower()
    except ValueError:
        return f"http_{exc.status_code}"


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": _kode_error_http(exc),
            "detail": exc.detail,
            "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        headers={"Cache-Control": "no-store"},
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
    detail = [
        {key: value for key, value in item.items() if key != "input"}
        for item in error.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": detail})


def _buat_token_sesi() -> str:
    kedaluwarsa = int(time.time()) + UMUR_SESI_DETIK
    nonce = secrets.token_urlsafe(12)
    pesan = f"vestcare:{kedaluwarsa}:{nonce}".encode("utf-8")
    tanda = hmac.new(API_KEY.encode("utf-8"), pesan, hashlib.sha256).hexdigest()
    return f"{kedaluwarsa}.{nonce}.{tanda}"


def _token_sesi_valid(token: Optional[str]) -> bool:
    if not token:
        return False
    bagian = token.split(".")
    if len(bagian) != 3:
        return False
    kedaluwarsa_teks, nonce, tanda = bagian
    try:
        kedaluwarsa = int(kedaluwarsa_teks)
    except ValueError:
        return False
    if kedaluwarsa < int(time.time()):
        return False
    pesan = f"vestcare:{kedaluwarsa}:{nonce}".encode("utf-8")
    harapan = hmac.new(API_KEY.encode("utf-8"), pesan, hashlib.sha256).hexdigest()
    return hmac.compare_digest(tanda, harapan)


def _pasang_cookie_sesi(response: Response, request: Request) -> None:
    protokol = request.headers.get("x-forwarded-proto", request.url.scheme)
    https = protokol.split(",")[0].strip().lower() == "https"
    response.set_cookie(
        key=COOKIE_SESI,
        value=_buat_token_sesi(),
        max_age=UMUR_SESI_DETIK,
        httponly=True,
        secure=https,
        samesite="lax",
        path="/",
    )


def _cek_api_key(request: Request, x_api_key: Optional[str]) -> None:
    if not API_KEY_CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail="API belum dikonfigurasi. Isi VEST_API_KEY dengan kunci acak minimal 32 karakter.",
        )
    if x_api_key and hmac.compare_digest(
        x_api_key.encode("utf-8"),
        API_KEY.encode("utf-8"),
    ):
        return
    if _token_sesi_valid(request.cookies.get(COOKIE_SESI)):
        return
    raise HTTPException(
        status_code=401,
        detail="X-API-Key atau sesi web salah atau tidak disertakan.",
    )


def _rencana_suara(data: JsonRecord) -> Optional[JsonRecord]:
    if perencana_suara is None:
        return None
    return perencana_suara.susun(data.get("deteksi", []))


def _pastikan_engine_siap() -> InferensiVest:
    if engine is None:
        raise HTTPException(status_code=503, detail=f"Engine belum siap: {engine_error}")
    return engine


def _tandai_supabase_gagal(error: Exception) -> None:
    global supabase_connected, supabase_connection_error, supabase_next_retry_at
    supabase_connected = False
    supabase_connection_error = str(error)
    supabase_next_retry_at = time.time() + 60.0


def _putar_riwayat_jika_perlu() -> None:
    """Batasi ukuran riwayat lokal dengan menyisakan entri terbaru saja.

    File lama disalin ke ``<nama>.1`` agar data sebelumnya masih bisa
    diperiksa, lalu file aktif diganti secara atomik.
    """
    try:
        if not riwayat_path.exists() or riwayat_path.stat().st_size <= RIWAYAT_MAX_BYTES:
            return
        terbaru: deque[str] = deque(maxlen=RIWAYAT_KEEP_ENTRIES)
        with open(riwayat_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    terbaru.append(line if line.endswith("\n") else f"{line}\n")
        arsip = riwayat_path.with_name(f"{riwayat_path.name}.1")
        shutil.copy2(riwayat_path, arsip)
        sementara = riwayat_path.with_name(f"{riwayat_path.name}.tmp")
        with open(sementara, "w", encoding="utf-8") as f:
            f.writelines(terbaru)
        os.replace(sementara, riwayat_path)
        logger.info(
            "[RIWAYAT] File diputar; %d entri terbaru dipertahankan, arsip: %s.",
            len(terbaru),
            arsip,
        )
    except OSError as error:
        logger.error("[RIWAYAT] Gagal memutar file riwayat: %s", error)


def _simpan_riwayat(hasil_dict: JsonRecord, sumber: str) -> JsonRecord:
    with LATEST_TELEMETRI_LOCK:
        tele = dict(LATEST_TELEMETRI)
    if "posisi" not in hasil_dict and tele.get("fix") and tele.get("lat") is not None and tele.get("lng") is not None:
        hasil_dict["posisi"] = {
            "lat": tele["lat"],
            "lng": tele["lng"],
        }
    entri: JsonRecord = {
        "id": uuid.uuid4().hex[:12],
        "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sumber": sumber,
        **hasil_dict,
    }
    try:
        with RIWAYAT_LOCK:
            riwayat_path.parent.mkdir(parents=True, exist_ok=True)
            with open(riwayat_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entri, ensure_ascii=False) + "\n")
            _putar_riwayat_jika_perlu()
    except OSError as error:
        # Riwayat lokal tidak boleh menggagalkan hasil inferensi.
        logger.error("Gagal menulis riwayat deteksi: %s", error)
        entri["riwayat_error"] = str(error)
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            sinkronisasi: JsonRecord = _simpan_deteksi_supabase(entri)
        except Exception as error:  # noqa: BLE001 - Supabase bersifat opsional
            _tandai_supabase_gagal(error)
            sinkronisasi = {
                "supabase_tersimpan": False,
                "supabase_error": str(error),
            }
    else:
        sinkronisasi = {"supabase_tersimpan": False}
    entri.update(sinkronisasi)
    return entri


def _ambil_perangkat_supabase(device_id: Optional[str] = None) -> Optional[JsonRecord]:
    query = {"select": "id,name", "limit": "1"}
    if device_id:
        query["id"] = f"eq.{device_id}"
    else:
        query["order"] = "created_at.asc"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    request = UrlRequest(
        f"{SUPABASE_URL}/rest/v1/devices?{urllib.parse.urlencode(query)}",
        headers=headers,
    )
    rows: Any = None
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=10) as response:
                rows = json.loads(response.read().decode("utf-8"))
            break
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Supabase devices mengembalikan HTTP {error.code}: {detail or error.reason}"
            ) from error
        except (URLError, json.JSONDecodeError, TimeoutError, OSError) as error:
            last_error = error
            if attempt < 2:
                time.sleep(1.5)
    else:
        raise RuntimeError(f"Gagal membaca Supabase devices: {last_error}") from last_error
    if not isinstance(rows, list) or not all(
        isinstance(row, dict) for row in cast(list[Any], rows)
    ):
        raise RuntimeError("Supabase mengembalikan format devices yang tidak valid.")
    return cast(list[JsonRecord], rows)[0] if rows else None


def _hubungkan_perangkat_supabase() -> str:
    global supabase_device_id

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Atur SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY di .env server."
        )

    if SUPABASE_DEVICE_ID_ENV:
        try:
            device_id = str(uuid.UUID(SUPABASE_DEVICE_ID_ENV))
        except ValueError as error:
            raise ValueError("VEST_SUPABASE_DEVICE_ID harus berupa UUID yang valid.") from error
        existing = _ambil_perangkat_supabase(device_id)
    else:
        existing = _ambil_perangkat_supabase()
        device_id = str(existing["id"]) if existing and existing.get("id") else SUPABASE_DEVICE_FALLBACK

    created_at = datetime.now().astimezone().isoformat()
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

    if existing:
        path = f"devices?id=eq.{urllib.parse.quote(device_id, safe='')}"
        body = json.dumps({"online": True, "last_seen": created_at}).encode("utf-8")
        method = "PATCH"
        prefer = "return=minimal"
    else:
        path = "devices?on_conflict=id"
        body = json.dumps([{
            "id": device_id,
            "name": "VestCare Server",
            "student_name": "Perangkat sementara",
            "school": "Server VestCare",
            "online": True,
            "last_seen": created_at,
        }]).encode("utf-8")
        method = "POST"
        prefer = "resolution=merge-duplicates,return=minimal"

    request = UrlRequest(
        f"{SUPABASE_URL}/rest/v1/{path}",
        data=body,
        headers={**headers, "Prefer": prefer},
        method=method,
    )
    try:
        with urlopen(request, timeout=8) as response:
            if response.status not in (200, 201, 204):
                raise RuntimeError(f"Supabase devices mengembalikan HTTP {response.status}.")
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Supabase devices mengembalikan HTTP {error.code}: {detail or error.reason}"
        ) from error
    except URLError as error:
        reason = getattr(error, "reason", error)
        raise RuntimeError(f"Gagal menghubungi Supabase devices: {reason}") from error

    supabase_device_id = device_id
    return device_id


def _deduplikasi_deteksi_supabase(device_id: str) -> int:
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    query = urllib.parse.urlencode({
        "device_id": f"eq.{device_id}",
        "select": "id,object,created_at",
        "order": "created_at.desc,id.desc",
        "limit": "1000",
    })
    try:
        with urlopen(UrlRequest(f"{SUPABASE_URL}/rest/v1/detections?{query}", headers=headers), timeout=8) as response:
            detections: Any = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Gagal membaca duplikat detections dari Supabase (HTTP {error.code}): {detail or error.reason}"
        ) from error
    except (URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Gagal membaca detections Supabase untuk deduplikasi: {error}") from error
    if not isinstance(detections, list) or not all(
        isinstance(row, dict) for row in cast(list[Any], detections)
    ):
        raise RuntimeError("Supabase mengembalikan format detections yang tidak valid.")
    detections = cast(list[JsonRecord], detections)

    latest_by_object: set[str] = set()
    duplicate_ids: list[str] = []
    for row in detections:
        object_name = str(row.get("object", "")).strip().lower()
        if not object_name:
            continue
        if object_name in latest_by_object:
            duplicate_ids.append(str(row["id"]))
        else:
            latest_by_object.add(object_name)

    for start in range(0, len(duplicate_ids), 100):
        batch = duplicate_ids[start:start + 100]
        id_filter = ",".join(batch)
        path = f"detections?device_id=eq.{device_id}&id=in.({id_filter})"
        request = UrlRequest(
            f"{SUPABASE_URL}/rest/v1/{path}",
            headers={
                **headers,
                "Prefer": "return=minimal",
            },
            method="DELETE",
        )
        try:
            with urlopen(request, timeout=8) as response:
                if response.status not in (200, 204):
                    raise RuntimeError(f"Supabase deduplikasi mengembalikan HTTP {response.status}.")
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"Gagal menghapus duplikat detections (HTTP {error.code}): {detail or error.reason}"
            ) from error
        except URLError as error:
            reason = getattr(error, "reason", error)
            raise RuntimeError(f"Gagal menghapus duplikat detections: {reason}") from error
    return len(duplicate_ids)


def _simpan_deteksi_supabase(entri: JsonRecord) -> JsonRecord:
    global supabase_last_signature, supabase_last_saved_at
    global supabase_connected, supabase_connection_error, supabase_next_retry_at

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Atur SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY di .env server untuk menyimpan riwayat."
        )
    if (
        not supabase_connected
        and supabase_connection_error
        and time.time() < supabase_next_retry_at
    ):
        # Jangan menahan respons deteksi dengan percobaan jaringan berulang
        # ketika Supabase baru saja terbukti tidak tersedia.
        raise RuntimeError(
            f"Supabase sedang tidak tersedia: {supabase_connection_error}"
        )
    try:
        device_id = str(uuid.UUID(supabase_device_id))
    except ValueError as error:
        raise ValueError("VEST_SUPABASE_DEVICE_ID harus berupa UUID yang valid.") from error

    latest_by_object: dict[str, JsonRecord] = {}
    detections = cast(list[JsonRecord], entri.get("deteksi", []))
    for item in detections:
        if item.get("ragu"):
            continue
        object_name = str(item.get("kelas", item.get("object", ""))).strip().lower()
        if not object_name or object_name not in KELAS_ID_KE_NAMA.values():
            continue
        current = latest_by_object.get(object_name)
        if current is None or float(item.get("urgensi", 0) or 0) > float(current.get("urgensi", 0) or 0):
            latest_by_object[object_name] = item
    deteksi: list[JsonRecord] = list(latest_by_object.values())
    if not deteksi:
        return {"supabase_tersimpan": True, "supabase_jumlah": 0}

    signature = "|".join(sorted(
        f"{item.get('kelas', item.get('object', ''))}:{item.get('level', '')}:{item.get('arah', '')}"
        for item in deteksi
    ))
    now = time.monotonic()
    with SUPABASE_SYNC_LOCK:
        if signature == supabase_last_signature and now - supabase_last_saved_at < 10:
            return {"supabase_tersimpan": True, "supabase_jumlah": 0}

        created_at = datetime.now().astimezone().isoformat()
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

        def request_supabase(path: str, method: str,
                             payload: Optional[JsonRecord | list[JsonRecord]] = None,
                             prefer: str = "return=minimal") -> Any:
            request = UrlRequest(
                f"{SUPABASE_URL}/rest/v1/{path}",
                data=json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None,
                headers={**headers, "Prefer": prefer},
                method=method,
            )
            try:
                with urlopen(request, timeout=8) as response:
                    if response.status not in (200, 201, 204):
                        raise RuntimeError(f"Supabase {path} mengembalikan HTTP {response.status}.")
                    body = response.read().decode("utf-8")
                    return json.loads(body) if body else None
            except HTTPError as error:
                detail = error.read().decode("utf-8", errors="replace").strip()
                raise RuntimeError(
                    f"Supabase {path} mengembalikan HTTP {error.code}: {detail or error.reason}"
                ) from error
            except URLError as error:
                reason = getattr(error, "reason", error)
                raise RuntimeError(f"Gagal menghubungi Supabase {path}: {reason}") from error

        if not supabase_connected:
            _hubungkan_perangkat_supabase()

        posisi = cast(JsonRecord, entri.get("posisi") or {})
        tingkat_ke_urgensi = {
            "BAHAYA": "Tinggi",
            "WASPADA": "Sedang",
            "INFO": "Rendah",
            "AMAN": "Rendah",
        }
        rows: list[JsonRecord] = [{
            "device_id": device_id,
            "object": str(item.get("kelas", item.get("object", "Tidak dikenal"))),
            "distance_m": float(item.get("jarak_m", item.get("distance_m", 0)) or 0),
            "confidence": float(item.get("conf", item.get("confidence", 0)) or 0),
            "urgency": tingkat_ke_urgensi.get(
                str(item.get("level", item.get("urgency", "INFO"))).upper(),
                "Sedang",
            ),
            "lat": posisi.get("lat"),
            "lng": posisi.get("lng"),
            "urgency_score": float(item.get("urgensi", item.get("urgency_score", 0)) or 0),
            "created_at": created_at,
        } for item in deteksi]
        existing_query = urllib.parse.urlencode({
            "device_id": f"eq.{device_id}",
            "select": "id,object",
            "order": "created_at.desc,id.desc",
            "limit": "1000",
        })
        existing_data: Any = request_supabase(f"detections?{existing_query}", "GET") or []
        if not isinstance(existing_data, list) or not all(
            isinstance(existing, dict) for existing in cast(list[Any], existing_data)
        ):
            raise RuntimeError("Supabase mengembalikan format detections yang tidak valid.")
        existing_rows = cast(list[JsonRecord], existing_data)
        latest_id_by_object: dict[str, str] = {}
        duplicate_ids: list[str] = []
        for existing in existing_rows:
            object_name = str(existing.get("object", "")).strip().lower()
            if not object_name:
                continue
            if object_name in latest_id_by_object:
                duplicate_ids.append(str(existing["id"]))
            else:
                latest_id_by_object[object_name] = str(existing["id"])

        inserts: list[JsonRecord] = []
        for row in rows:
            existing_id = latest_id_by_object.get(row["object"].lower())
            if existing_id is None:
                inserts.append(row)
            else:
                request_supabase(
                    f"detections?id=eq.{urllib.parse.quote(existing_id, safe='')}&device_id=eq.{device_id}",
                    "PATCH",
                    row,
                )
                latest_id_by_object.pop(row["object"].lower())

        if inserts:
            request_supabase("detections", "POST", inserts)
        for start in range(0, len(duplicate_ids), 100):
            id_filter = ",".join(duplicate_ids[start:start + 100])
            request_supabase(
                f"detections?device_id=eq.{device_id}&id=in.({id_filter})",
                "DELETE",
            )

        supabase_last_signature = signature
        supabase_last_saved_at = now
        supabase_connected = True
        supabase_connection_error = None
        supabase_next_retry_at = 0.0
        return {"supabase_tersimpan": True, "supabase_jumlah": len(rows)}


def _sinkronisasi_telemetri_supabase(data: JsonRecord) -> None:
    global latest_gps_log_at, last_device_update_at
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return

    now = time.time()
    try:
        device_id = str(uuid.UUID(supabase_device_id))
    except (ValueError, TypeError):
        return

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

    if now - last_device_update_at >= 15.0:
        last_device_update_at = now
        payload_device: dict[str, Any] = {
            "online": True,
            "last_seen": datetime.now().astimezone().isoformat(),
        }
        if data.get("battery") is not None:
            payload_device["battery"] = data["battery"]
        req_dev = UrlRequest(
            f"{SUPABASE_URL}/rest/v1/devices?id=eq.{urllib.parse.quote(device_id, safe='')}",
            data=json.dumps(payload_device).encode("utf-8"),
            headers={**headers, "Prefer": "return=minimal"},
            method="PATCH",
        )
        try:
            with urlopen(req_dev, timeout=5):
                pass
        except Exception:
            pass

    if data.get("fix") and data.get("lat") is not None and data.get("lng") is not None:
        if now - latest_gps_log_at >= 5.0:
            latest_gps_log_at = now
            payload_gps: list[JsonRecord] = [{
                "device_id": device_id,
                "lat": float(data["lat"]),
                "lng": float(data["lng"]),
                "accuracy": float(data.get("hdop") or 1.0),
                "created_at": datetime.now().astimezone().isoformat(),
            }]
            req_gps = UrlRequest(
                f"{SUPABASE_URL}/rest/v1/gps_log",
                data=json.dumps(payload_gps).encode("utf-8"),
                headers={**headers, "Prefer": "return=minimal"},
                method="POST",
            )
            try:
                with urlopen(req_gps, timeout=5):
                    pass
            except Exception:
                pass


def _baca_riwayat(limit: int) -> JsonRecord:
    with RIWAYAT_LOCK:
        # Pastikan file lama yang sudah membesar ikut dipangkas walaupun
        # pengguna belum mengirim deteksi baru.
        _putar_riwayat_jika_perlu()
    if not riwayat_path.exists():
        return {"total": 0, "data": []}
    terbaru: deque[JsonRecord] = deque(maxlen=limit)
    total = 0
    try:
        with open(riwayat_path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                total += 1
                try:
                    entri = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(entri, dict):
                    terbaru.append(cast(JsonRecord, entri))
    except OSError as error:
        logger.error("Gagal membaca riwayat deteksi: %s", error)
        return {"total": 0, "data": [], "error": str(error)}
    data = list(reversed(terbaru))
    return {"total": total, "ditampilkan": len(data), "data": data}


def _catat_jalur(data: JsonRecord) -> None:
    """Simpan titik GPS baru agar peta bisa menggambar jejak perjalanan."""
    if not data.get("fix") or data.get("lat") is None or data.get("lng") is None:
        return
    try:
        lat = float(data["lat"])
        lng = float(data["lng"])
    except (TypeError, ValueError):
        return
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return
    with TELEMETRI_JALUR_LOCK:
        if TELEMETRI_JALUR:
            terakhir = TELEMETRI_JALUR[-1]
            if abs(float(terakhir["lat"]) - lat) < 1e-6 and abs(float(terakhir["lng"]) - lng) < 1e-6:
                return
        TELEMETRI_JALUR.append({
            "lat": lat,
            "lng": lng,
            "spd": data.get("spd"),
            "alt": data.get("alt"),
            "waktu": data.get("waktu"),
            "updated_at": data.get("updated_at"),
        })


def _salin_jalur() -> list[dict[str, Any]]:
    with TELEMETRI_JALUR_LOCK:
        return [dict(titik) for titik in TELEMETRI_JALUR]


def _ringkasan_telemetri(data: JsonRecord) -> JsonRecord:
    now = time.time()
    updated_at = float(data.get("updated_at") or 0)
    last_seen_at = max(updated_at, float(data.get("last_seen_at") or 0))
    umur = max(0.0, now - last_seen_at) if last_seen_at else None
    return {
        "telemetri": data,
        "jalur": _salin_jalur(),
        "online": umur is not None and umur < 15.0,
        "umur_detik": round(umur, 1) if umur is not None else None,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _jalankan_deteksi(gambar_pil: Image.Image, jarak_m: Optional[float]) -> HasilInferensi:
    engine = _pastikan_engine_siap()
    with INFERENSI_LOCK:
        hasil = engine.deteksi_gambar(
            np.array(gambar_pil.convert("RGB")),
            jarak_us=jarak_m,
            conf_min=CONF,
        )
    return hasil


async def _baca_gambar(gambar: UploadFile) -> Image.Image:
    isi = await gambar.read(MAX_UPLOAD_BYTES + 1)
    if len(isi) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Ukuran gambar melebihi batas 10 MB.")
    try:
        with Image.open(io.BytesIO(isi)) as source:
            if source.width * source.height > 40_000_000:
                raise HTTPException(status_code=413, detail="Resolusi gambar melebihi batas 40 megapiksel.")
            source.verify()
        with Image.open(io.BytesIO(isi)) as source:
            source.load()
            return source.convert("RGB")
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(
            status_code=400,
            detail="File gambar tidak valid / tidak bisa dibaca.",
        ) from error


def _validasi_frame_jpeg(frame: bytes) -> None:
    if not frame.startswith(b"\xff\xd8"):
        raise HTTPException(status_code=400, detail="Frame ESP32 harus berupa JPEG.")
    try:
        with Image.open(io.BytesIO(frame)) as image:
            if image.format != "JPEG":
                raise HTTPException(status_code=400, detail="Frame ESP32 harus berupa JPEG.")
            if image.width * image.height > 40_000_000:
                raise HTTPException(
                    status_code=413,
                    detail="Resolusi frame melebihi batas 40 megapiksel.",
                )
            image.verify()
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise HTTPException(
            status_code=400,
            detail="Frame ESP32 bukan JPEG yang valid atau tidak dapat dibaca.",
        ) from error


@app.get("/info")
def info() -> JsonRecord:
    with ESP32_FRAME_CONDITION:
        frame_tersedia = esp32_frame_bytes is not None
        frame_umur = (
            round(max(0.0, time.time() - esp32_frame_updated_at), 1)
            if esp32_frame_updated_at
            else None
        )
    return {
        "nama": "VestCare API",
        "versi": "2.0.0",
        "aplikasi_browser": "/app",
        "engine_siap": engine is not None,
        "model_exists": model_path.exists(),
        "imgsz": IMGSZ,
        "conf": CONF,
        "conf_ragu": CONF_RAGU,
        "suara_browser": "klip Ardi (suara-natural-ai)",
        "pustaka_suara_siap": perencana_suara is not None,
        "autentikasi": "aktif" if API_KEY_CONFIGURED else "belum dikonfigurasi",
        "kamera_esp32_tersedia": frame_tersedia and frame_umur is not None and frame_umur <= 5.0,
        "kamera_esp32_umur_detik": frame_umur,
        "dokumentasi": "/docs",
        "status": "/status",
        "sesi": "/sesi",
    }


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
def aplikasi_browser(request: Request) -> Response:
    if not DASHBOARD_INDEX.is_file():
        raise HTTPException(
            status_code=503,
            detail="Dashboard React belum dibangun. Jalankan `npm run build` di folder web/react.",
        )
    response = FileResponse(
        DASHBOARD_INDEX,
        headers={"Cache-Control": "no-store"},
    )
    if API_KEY_CONFIGURED:
        _pasang_cookie_sesi(response, request)
    return response


@app.get("/suara/pratinjau")
def pratinjau_suara(
    request: Request,
    x_api_key: Optional[str] = Header(None),
) -> JsonRecord:
    _cek_api_key(request, x_api_key)
    if perencana_suara is None:
        raise HTTPException(status_code=503, detail="Pustaka suara Ardi belum tersedia.")
    rencana = perencana_suara.contoh()
    if rencana is None:
        raise HTTPException(status_code=404, detail="Klip contoh tidak tersedia.")
    return {"suara": rencana}


@app.get("/suara/{nama_berkas}", include_in_schema=False)
def berkas_suara(
    nama_berkas: str,
    request: Request,
    x_api_key: Optional[str] = Header(None),
) -> Response:
    _cek_api_key(request, x_api_key)
    if perencana_suara is None or not perencana_suara.berkas_diizinkan(nama_berkas):
        raise HTTPException(status_code=404, detail="Berkas suara tidak ditemukan.")
    return FileResponse(
        SUARA_FOLDER / nama_berkas,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.get("/status")
def status() -> JsonRecord:
    with ESP32_FRAME_CONDITION:
        frame_umur = (
            round(max(0.0, time.time() - esp32_frame_updated_at), 1)
            if esp32_frame_updated_at
            else None
        )
    with LATEST_DETEKSI_LOCK:
        deteksi_umur = (
            round(max(0.0, time.time() - float(LATEST_DETEKSI.get("updated_at") or 0.0)), 1)
            if LATEST_DETEKSI.get("updated_at")
            else None
        )
    return {
        "server": "VestCare API",
        "versi": "2.0.0",
        "engine_siap": engine is not None,
        "api_terproteksi": API_KEY_CONFIGURED,
        "pustaka_suara_siap": perencana_suara is not None,
        "supabase_sinkronisasi_aktif": bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        "supabase_terhubung": supabase_connected,
        "supabase_error": supabase_connection_error,
        "supabase_device_id": supabase_device_id if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else None,
        "kamera_esp32_umur_detik": frame_umur,
        "kamera_esp32_tersedia": frame_umur is not None and frame_umur <= 5.0,
        "deteksi_umur_detik": deteksi_umur,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/sesi")
def sesi_baru(request: Request) -> Response:
    """Perbarui cookie sesi browser tanpa memuat ulang dashboard.

    Browser memakai endpoint ini ketika cookie 12 jam kedaluwarsa. Respons
    tetap dapat diakses halaman same-origin; API lain tetap memerlukan cookie
    atau X-API-Key.
    """
    response = JSONResponse({
        "status": "ok",
        "pesan": "Sesi browser diperbarui.",
        "umur_detik": UMUR_SESI_DETIK,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    response.headers["Cache-Control"] = "no-store"
    if API_KEY_CONFIGURED:
        _pasang_cookie_sesi(response, request)
    return response


@app.get("/healthz", include_in_schema=False)
def healthz() -> JsonRecord:
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
def readyz() -> JsonRecord:
    belum_siap: list[str] = []
    if engine is None:
        belum_siap.append("engine")
    if not API_KEY_CONFIGURED:
        belum_siap.append("api_key")
    if not DASHBOARD_INDEX.is_file():
        belum_siap.append("dashboard")
    if belum_siap:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "komponen": belum_siap},
        )
    return {
        "status": "ready",
        "engine_siap": True,
        "api_terproteksi": True,
        "dashboard_siap": True,
    }


async def hubungkan_supabase_saat_server_mulai() -> None:
    global supabase_connected, supabase_connection_error, supabase_next_retry_at
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        # Supabase opsional. Jangan laporkan sebagai error agar /status tetap
        # bersih pada instalasi lokal/Railway yang hanya memakai riwayat lokal.
        print("[SUPABASE] Sinkronisasi nonaktif: konfigurasi belum lengkap.")
        return
    device_id: str = supabase_device_id
    removed = 0
    try:
        device_id = await run_in_threadpool(_hubungkan_perangkat_supabase)
        removed = await run_in_threadpool(_deduplikasi_deteksi_supabase, device_id)
    except ValueError as error:
        _tandai_supabase_gagal(error)
        print(f"[SUPABASE] Konfigurasi tidak valid: {supabase_connection_error}")
        return
    except RuntimeError:
        for attempt in range(3):
            try:
                await run_in_threadpool(time.sleep, 2)
                device_id = await run_in_threadpool(_hubungkan_perangkat_supabase)
                removed = await run_in_threadpool(_deduplikasi_deteksi_supabase, device_id)
                break
            except RuntimeError as error:
                if attempt == 2:
                    _tandai_supabase_gagal(error)
                    print(f"[SUPABASE] Koneksi saat startup gagal: {supabase_connection_error}")
                    return

    supabase_connected = True
    supabase_connection_error = None
    supabase_next_retry_at = 0.0
    print(
        f"[SUPABASE] Terhubung. Perangkat server: {device_id}; "
        f"duplikat kelas dihapus: {removed}"
    )


class MasukanTelemetri(BaseModel):
    jarak: Optional[float] = Field(None, allow_inf_nan=False, description="jarak ultrasonik dalam meter")
    valid_jarak: Optional[bool] = Field(None, description="apakah pembacaan ultrasonik valid")
    lat: Optional[float] = Field(None, ge=-90, le=90, allow_inf_nan=False, description="latitude dari GPS dalam derajat")
    lng: Optional[float] = Field(None, ge=-180, le=180, allow_inf_nan=False, description="longitude dari GPS dalam derajat")
    alt: Optional[float] = Field(None, allow_inf_nan=False, description="ketinggian (meter)")
    spd: Optional[float] = Field(None, allow_inf_nan=False, description="kecepatan (km/jam)")
    sat: Optional[int] = Field(None, description="jumlah satelit terkunci")
    hdop: Optional[float] = Field(None, allow_inf_nan=False, description="horizontal dilution of precision")
    fix: Optional[bool] = Field(None, description="apakah GPS fix lock valid")
    terbaca: Optional[bool] = Field(None, description="apakah modul GPS merespon")
    waktu: Optional[str] = Field(None, description="waktu GPS")
    battery: Optional[float] = Field(None, allow_inf_nan=False, description="persentase baterai")


@app.post("/telemetri")
@app.post("/api/telemetri")
async def telemetri_masuk(
    m: MasukanTelemetri,
    background_tasks: BackgroundTasks,
) -> JsonRecord:
    """Public telemetry endpoint for Wemos devices configured with Wi-Fi only."""
    global LATEST_TELEMETRI
    now = time.time()
    gps_fix = bool(m.fix and m.lat is not None and m.lng is not None)
    lat = m.lat
    lng = m.lng
    update_data: JsonRecord = {
        "jarak": float(m.jarak) if m.jarak is not None and m.valid_jarak else None,
        "valid_jarak": bool(m.valid_jarak),
        "lat": float(lat) if gps_fix and lat is not None else None,
        "lng": float(lng) if gps_fix and lng is not None else None,
        "alt": float(m.alt) if m.alt is not None else None,
        "spd": float(m.spd) if m.spd is not None else None,
        "sat": int(m.sat or 0),
        "hdop": float(m.hdop or 0.0),
        "fix": gps_fix,
        "terbaca": bool(m.terbaca),
        "waktu": m.waktu or datetime.now().strftime("%H:%M:%S"),
        "battery": m.battery,
        "updated_at": now,
        "last_seen_at": now,
    }
    with LATEST_TELEMETRI_LOCK:
        LATEST_TELEMETRI.update(update_data)
    _catat_jalur(update_data)

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        background_tasks.add_task(_sinkronisasi_telemetri_supabase, update_data)

    return {
        "status": "ok",
        "pesan": "Telemetri diterima",
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "gps_fix": gps_fix,
        "jarak_sensor": m.jarak if m.valid_jarak else None,
    }


@app.get("/telemetri")
@app.get("/api/telemetri")
def telemetri_status() -> JsonRecord:
    with LATEST_TELEMETRI_LOCK:
        data = dict(LATEST_TELEMETRI)
    return _ringkasan_telemetri(data)


@app.get("/telemetri/stream", include_in_schema=False)
@app.get("/api/telemetri/stream", include_in_schema=False)
async def telemetri_stream(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, description="API key untuk klien non-browser"),
) -> StreamingResponse:
    """Server-Sent Events: dorong telemetri Wemos ke dashboard seketika."""
    if API_KEY_CONFIGURED:
        _cek_api_key(request, x_api_key or api_key)

    async def peristiwa() -> AsyncIterator[str]:
        signature_terakhir: Optional[tuple[Any, ...]] = None
        kirim_terakhir = 0.0
        detak_terakhir = 0.0
        while True:
            if await request.is_disconnected():
                break
            with LATEST_TELEMETRI_LOCK:
                data = dict(LATEST_TELEMETRI)
            sekarang = time.time()
            jalur = _salin_jalur()
            signature = (
                data.get("updated_at"),
                data.get("battery"),
                data.get("fix"),
                data.get("lat"),
                data.get("lng"),
                len(jalur),
            )
            if signature != signature_terakhir or sekarang - kirim_terakhir >= 5.0:
                payload = _ringkasan_telemetri(data)
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
                signature_terakhir = signature
                kirim_terakhir = sekarang
            elif sekarang - detak_terakhir >= 15.0:
                yield ": keep-alive\n\n"
                detak_terakhir = sekarang
            await asyncio.sleep(1.0)

    return StreamingResponse(
        peristiwa(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/deteksi/stream", include_in_schema=False)
async def deteksi_stream(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, description="API key untuk klien non-browser"),
) -> StreamingResponse:
    if API_KEY_CONFIGURED:
        _cek_api_key(request, x_api_key or api_key)

    async def peristiwa() -> AsyncIterator[str]:
        updated_at_terakhir = 0.0
        kirim_terakhir = 0.0
        while not await request.is_disconnected():
            with LATEST_DETEKSI_LOCK:
                data = dict(LATEST_DETEKSI)

            updated_at = float(data.get("updated_at") or 0.0)
            sekarang = time.time()
            if updated_at > updated_at_terakhir:
                yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                updated_at_terakhir = updated_at
                kirim_terakhir = sekarang
            elif sekarang - kirim_terakhir >= 15.0:
                yield ": keep-alive\n\n"
                kirim_terakhir = sekarang

            await asyncio.sleep(0.05)

    return StreamingResponse(
        peristiwa(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/deteksi/latest", include_in_schema=False)
def deteksi_terbaru(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    if_none_match: Optional[str] = Header(None),
) -> Response:
    _cek_api_key(request, x_api_key)
    with LATEST_DETEKSI_LOCK:
        data = dict(LATEST_DETEKSI)

    updated_at = float(data.get("updated_at") or 0.0)
    umur = max(0.0, time.time() - updated_at) if updated_at else None
    etag = f'"{int(updated_at * 1000)}"'
    headers = {"Cache-Control": "no-store", "ETag": etag}
    if if_none_match == etag:
        return Response(status_code=304, headers=headers)
    return JSONResponse(
        {
            "data": data.get("data"),
            "updated_at": updated_at,
            "umur_detik": round(umur, 1) if umur is not None else None,
            "online": umur is not None and umur < 30.0,
        },
        headers=headers,
    )


@app.get("/config")
def konfigurasi_publik() -> JsonRecord:
    """Konfigurasi publik dashboard (kunci Google Maps memang kunci browser)."""
    return {
        "versi": "2.0.0",
        "google_maps_api_key": GOOGLE_MAPS_API_KEY,
        "map_default_center": {"lat": MAP_DEFAULT_LAT, "lng": MAP_DEFAULT_LNG},
        "map_zoom": MAP_DEFAULT_ZOOM,
        "telemetri_stream": "/api/telemetri/stream",
        "telemetri_poll_ms": 1000,
        "dashboard_poll_ms": 10000,
        "esp32_stream": "/esp32/stream",
        "esp32_status": "/api/esp32/status",
        "esp32_frame": "/api/esp32/frame/latest",
        "deteksi_latest": "/api/deteksi/latest",
        "sesi": "/sesi",
    }


@app.get("/esp32/stream", include_in_schema=False)
@app.get("/api/esp32/stream", include_in_schema=False)
async def esp32_stream(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, description="API key untuk klien non-browser"),
) -> StreamingResponse:
    if API_KEY_CONFIGURED:
        _cek_api_key(request, x_api_key or api_key)

    async def stream() -> AsyncGenerator[bytes, None]:
        sequence = 0
        while not await request.is_disconnected():
            frame, sequence = await run_in_threadpool(_tunggu_frame_esp32, sequence)
            if frame is None:
                continue
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(frame)}\r\n\r\n".encode("ascii")
                + frame
                + b"\r\n"
            )

    return StreamingResponse(
        stream(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/api/esp32/status", include_in_schema=False)
def status_kamera_esp32(
    request: Request,
    x_api_key: Optional[str] = Header(None),
) -> JsonRecord:
    """Cek cepat apakah kamera ESP32 sedang mengirim frame.

    Dipakai dashboard untuk memilih sumber kamera: ESP32 jika aktif, atau
    kamera perangkat (browser) jika tidak ada frame baru.
    """
    _cek_api_key(request, x_api_key)
    with ESP32_FRAME_CONDITION:
        tersedia = esp32_frame_bytes is not None
        sequence = esp32_frame_sequence
        updated_at = esp32_frame_updated_at
    umur = max(0.0, time.time() - updated_at) if updated_at else None
    return {
        "tersedia": bool(tersedia and umur is not None and umur <= 5.0),
        "umur_detik": round(umur, 1) if umur is not None else None,
        "urutan": sequence,
        "diperbarui_pada": updated_at or None,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.get("/api/esp32/frame/latest", include_in_schema=False)
def frame_esp32_terbaru(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    if_none_match: Optional[str] = Header(None),
) -> Response:
    _cek_api_key(request, x_api_key)
    with ESP32_FRAME_CONDITION:
        frame = esp32_frame_bytes
        sequence = esp32_frame_sequence
        updated_at = esp32_frame_updated_at

    cache_headers = {"Cache-Control": "no-store, no-cache, must-revalidate"}
    if frame is None or time.time() - updated_at > 5.0:
        return Response(status_code=204, headers=cache_headers)

    etag = f'"{sequence}-{int(updated_at * 1000)}"'
    cache_headers["ETag"] = etag
    if if_none_match == etag:
        return Response(status_code=304, headers=cache_headers)
    return Response(content=frame, media_type="image/jpeg", headers=cache_headers)


@app.post("/api/esp32/frame", include_in_schema=False)
async def terima_frame_esp32(
    request: Request,
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    _cek_api_key(request, x_api_key)
    isi = bytearray()
    async for potongan in request.stream():
        if len(isi) + len(potongan) > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Ukuran frame melebihi batas 10 MB.")
        isi.extend(potongan)

    frame = bytes(isi)
    _validasi_frame_jpeg(frame)
    _simpan_frame_esp32(frame)
    return JSONResponse({"diterima": True}, status_code=202)


ESP32_STREAM_IP_LOCK = threading.Lock()
esp32_stream_ip: Optional[str] = None
esp32_stream_registered_at: float = 0.0


@app.post("/api/esp32/stream", include_in_schema=False)
async def registrasi_stream_esp32(
    request: Request,
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    """ESP32 registers its local IP so the dashboard can show its MJPEG stream."""
    _cek_api_key(request, x_api_key)
    global esp32_stream_ip, esp32_stream_registered_at
    try:
        body_data: object = await request.json()
    except Exception:
        body_data = {}

    client_ip = request.client.host if request.client else None
    ip: Optional[str] = client_ip
    if isinstance(body_data, dict):
        body = cast(dict[str, object], body_data)
        candidate_ip = body.get("ip", client_ip)
        if isinstance(candidate_ip, str) and candidate_ip.strip():
            ip = candidate_ip.strip()
    with ESP32_STREAM_IP_LOCK:
        esp32_stream_ip = ip
        esp32_stream_registered_at = time.time()
    logger.info("[STREAM-REG] ESP32 stream registered: %s", ip)
    return JSONResponse({"status": "ok", "ip": ip})


def _simpan_frame_esp32(frame: bytes) -> None:
    global esp32_frame_bytes, esp32_frame_sequence, esp32_frame_updated_at
    with ESP32_FRAME_CONDITION:
        esp32_frame_bytes = frame
        esp32_frame_sequence += 1
        esp32_frame_updated_at = time.time()
        ESP32_FRAME_CONDITION.notify_all()
    with LATEST_TELEMETRI_LOCK:
        LATEST_TELEMETRI["last_seen_at"] = esp32_frame_updated_at


def _tunggu_frame_esp32(sequence: int) -> tuple[Optional[bytes], int]:
    with ESP32_FRAME_CONDITION:
        berubah = ESP32_FRAME_CONDITION.wait_for(
            lambda: esp32_frame_sequence > sequence,
            timeout=1.0,
        )
        if not berubah:
            return None, sequence
        return esp32_frame_bytes, esp32_frame_sequence


@app.get("/dashboard/data")
def dashboard_data(request: Request, x_api_key: Optional[str] = Header(None)) -> JSONResponse:
    _cek_api_key(request, x_api_key)
    with LATEST_TELEMETRI_LOCK:
        live_telemetri = dict(LATEST_TELEMETRI)
    with LATEST_DETEKSI_LOCK:
        live_detection = dict(LATEST_DETEKSI)
    last_seen_live = max(
        float(live_telemetri.get("updated_at") or 0.0),
        float(live_telemetri.get("last_seen_at") or 0.0),
    )
    is_live_online = bool(last_seen_live and (time.time() - last_seen_live) < 15.0)

    try:
        device_id = str(uuid.UUID(supabase_device_id))
    except (ValueError, TypeError):
        device_id = SUPABASE_DEVICE_FALLBACK

    device_rows: list[JsonRecord] = []
    detections: list[JsonRecord] = []
    gps_rows: list[JsonRecord] = []

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }

        def baca_tabel(path: str) -> list[JsonRecord]:
            url = f"{SUPABASE_URL}/rest/v1/{path}"
            try:
                with urlopen(UrlRequest(url, headers=headers), timeout=5) as response:
                    data: Any = json.loads(response.read().decode("utf-8"))
            except Exception as error:  # noqa: BLE001 - dashboard tetap harus tampil
                logger.info("[SUPABASE] Baca %s ditunda: %s", path, error)
                return []
            if not isinstance(data, list) or not all(
                isinstance(row, dict) for row in cast(list[Any], data)
            ):
                return []
            return cast(list[JsonRecord], data)

        device_rows = baca_tabel(
            f"devices?id=eq.{device_id}&select=id,name,student_name,school,battery,online,last_seen&limit=1"
        )
        detections = baca_tabel(
            f"detections?device_id=eq.{device_id}"
            "&select=id,device_id,object,distance_m,confidence,urgency,lat,lng,urgency_score,created_at"
            "&order=created_at.desc,urgency_score.desc&limit=100"
        )
        gps_rows = baca_tabel(
            f"gps_log?device_id=eq.{device_id}"
            "&select=id,device_id,lat,lng,accuracy,created_at&order=created_at.desc&limit=1"
        )

    device_result: JsonRecord = device_rows[0] if device_rows else {
        "id": device_id,
        "name": "VestCare Rompi",
        "student_name": "Siswa VestCare",
        "school": "VestCare",
        "battery": live_telemetri.get("battery"),
        "online": is_live_online,
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if last_seen_live:
        # Data live (telemetri atau frame kamera) adalah sumber kebenaran
        # status online; jangan biarkan baris Supabase lama terus "online".
        device_result["online"] = is_live_online
        device_result["last_seen"] = datetime.now().astimezone().isoformat()
        if live_telemetri.get("battery") is not None:
            device_result["battery"] = live_telemetri["battery"]

    live_detection_updated = float(live_detection.get("updated_at") or 0)
    live_detection_data = live_detection.get("data")
    live_detection_fresh = bool(
        live_detection_updated and (time.time() - live_detection_updated) < 30
    )
    if live_detection_fresh:
        if isinstance(live_detection_data, dict):
            raw_detections = cast(JsonRecord, live_detection_data).get("deteksi")
            if isinstance(raw_detections, list):
                detection_records: list[JsonRecord] = []
                for item in cast(list[Any], raw_detections):
                    if isinstance(item, dict):
                        detection_records.append(cast(JsonRecord, item))
                detections = detection_records

    gps_result: Optional[JsonRecord] = gps_rows[0] if gps_rows and not is_live_online else None
    if live_telemetri.get("fix") and live_telemetri.get("lat") is not None and live_telemetri.get("lng") is not None:
        gps_result = {
            "id": "live-wemos",
            "device_id": device_id,
            "lat": live_telemetri["lat"],
            "lng": live_telemetri["lng"],
            "accuracy": live_telemetri.get("hdop", 1.0),
            "created_at": datetime.now().astimezone().isoformat(),
        }

    return JSONResponse(
        {
            "device": device_result,
            "detections": detections,
            "deteksi_live": live_detection_fresh,
            "deteksi_umur_detik": (
                round(max(0.0, time.time() - live_detection_updated), 1)
                if live_detection_updated
                else None
            ),
            "gps": gps_result,
            "telemetri": live_telemetri,
            "jalur": _salin_jalur(),
            "telemetri_online": is_live_online,
            "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        headers={"Cache-Control": "no-store"},
    )


@app.post("/deteksi")
async def deteksi(
    request: Request,
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(
        None,
        ge=0.03,
        le=3.0,
        allow_inf_nan=False,
        description="jarak ultrasonik depan dalam METER",
    ),
    mode_realtime: bool = Form(False, description="lewati penyimpanan riwayat untuk frame kamera realtime"),
    sesi: Optional[str] = Form(None),
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    _cek_api_key(request, x_api_key)
    with LATEST_TELEMETRI_LOCK:
        tele = dict(LATEST_TELEMETRI)
    if jarak_m is None and tele.get("valid_jarak") and tele.get("jarak") is not None:
        if (time.time() - tele.get("updated_at", 0)) < 5.0:
            jarak_m = float(tele["jarak"])

    frame_stream: Optional[bytes] = None
    if sesi == "esp32s3-camera":
        frame_stream = await gambar.read(MAX_UPLOAD_BYTES + 1)
        await gambar.seek(0)

    img = await _baca_gambar(gambar)
    if frame_stream is not None and frame_stream.startswith(b"\xff\xd8"):
        _simpan_frame_esp32(frame_stream)

    hasil = await run_in_threadpool(_jalankan_deteksi, img, jarak_m)
    data = InferensiVest.ke_dict(hasil)
    data["suara"] = _rencana_suara(data)
    if tele.get("fix") and tele.get("lat") is not None and tele.get("lng") is not None:
        data["posisi"] = {
            "lat": tele["lat"],
            "lng": tele["lng"],
        }
    with LATEST_DETEKSI_LOCK:
        LATEST_DETEKSI["updated_at"] = time.time()
        LATEST_DETEKSI["data"] = data
    if mode_realtime:
        return JSONResponse(data, headers={"Cache-Control": "no-store"})
    entri = await run_in_threadpool(_simpan_riwayat, data, "deteksi")
    return JSONResponse(entri, headers={"Cache-Control": "no-store"})


@app.post("/deteksi/suara")
async def deteksi_suara(
    request: Request,
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(
        None,
        ge=0.03,
        le=3.0,
        allow_inf_nan=False,
        description="jarak ultrasonik depan dalam METER",
    ),
    x_api_key: Optional[str] = Header(None),
) -> JSONResponse:
    _cek_api_key(request, x_api_key)
    with LATEST_TELEMETRI_LOCK:
        tele = dict(LATEST_TELEMETRI)
    if jarak_m is None and tele.get("valid_jarak") and tele.get("jarak") is not None:
        if (time.time() - tele.get("updated_at", 0)) < 5.0:
            jarak_m = float(tele["jarak"])

    img = await _baca_gambar(gambar)

    hasil = await run_in_threadpool(_jalankan_deteksi, img, jarak_m)
    data = InferensiVest.ke_dict(hasil)
    data["suara"] = _rencana_suara(data)
    if tele.get("fix") and tele.get("lat") is not None and tele.get("lng") is not None:
        data["posisi"] = {
            "lat": tele["lat"],
            "lng": tele["lng"],
        }
    entri = await run_in_threadpool(_simpan_riwayat, data, "deteksi_suara")
    return JSONResponse(entri, headers={"Cache-Control": "no-store"})


class MasukanFuzzy(BaseModel):
    skor_risiko: float = Field(..., ge=0, le=1, allow_inf_nan=False)
    jarak_m: Optional[float] = Field(None, ge=0, allow_inf_nan=False)


@app.post("/peringatan")
def peringatan(
    m: MasukanFuzzy,
    request: Request,
    x_api_key: Optional[str] = Header(None),
) -> JsonRecord:
    _cek_api_key(request, x_api_key)
    from fuzzysugeno import hitung_peringatan
    return {"skor_risiko": m.skor_risiko, "jarak_m": m.jarak_m,
            "peringatan": hitung_peringatan(m.skor_risiko, m.jarak_m)}


@app.get("/riwayat")
def riwayat(
    request: Request,
    limit: int = Query(20, ge=1, le=500, description="jumlah entri terakhir yang diambil"),
    x_api_key: Optional[str] = Header(None),
) -> JsonRecord:
    _cek_api_key(request, x_api_key)
    return _baca_riwayat(limit)


if DASHBOARD_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")


if __name__ == "__main__":
    raise SystemExit("Jalankan server VestCare dengan `python server.py`.")
