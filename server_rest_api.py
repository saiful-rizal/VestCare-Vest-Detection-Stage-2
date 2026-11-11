from __future__ import annotations

import asyncio
import hashlib
import json
import hmac
import os
import random
import secrets
import shutil
import subprocess
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Optional
from urllib.error import HTTPError, URLError
import urllib.parse
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
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from PIL import Image
from starlette.concurrency import run_in_threadpool
import io

ROOT = Path(__file__).resolve().parent
DASHBOARD_DIR = ROOT / "vest-care-react" / "dist"
DASHBOARD_INDEX = DASHBOARD_DIR / "index.html"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

def load_project_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    for line_number, raw_line in enumerate(env_path.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        key = key.strip()
        if not separator or not key or not key.replace("_", "").isalnum():
            raise ValueError(f"Format .env tidak valid pada baris {line_number}.")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)

load_project_env()


SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
SUPABASE_DEVICE_ID_ENV = os.environ.get("VEST_SUPABASE_DEVICE_ID", "").strip()
SUPABASE_DEVICE_FALLBACK = str(uuid.uuid5(uuid.NAMESPACE_URL, "vestcare-server-device"))
SUPABASE_DEVICE_ID = SUPABASE_DEVICE_ID_ENV or SUPABASE_DEVICE_FALLBACK
SUPABASE_SYNC_LOCK = threading.Lock()
SUPABASE_LAST_SIGNATURE = ""
SUPABASE_LAST_SAVED_AT = 0.0
SUPABASE_CONNECTED = False
SUPABASE_CONNECTION_ERROR: Optional[str] = None

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
}
LATEST_GPS_LOG_AT = 0.0
LAST_DEVICE_UPDATE_AT = 0.0

# Jejak posisi Wemos selama server hidup. Dipakai peta Google Maps untuk
# menggambar garis perjalanan tanpa harus menunggu data Supabase.
TELEMETRI_JALUR_LOCK = threading.Lock()
TELEMETRI_JALUR: deque[dict[str, Any]] = deque(maxlen=300)


def api_key_is_configured(value: Optional[str]) -> bool:
    if value is None or len(value.strip()) < 32:
        return False
    normalized = value.strip().lower()
    return not any(marker in normalized for marker in ("contoh", "ganti", "rahasia-anda"))


DEFAULT_MODEL = ROOT / "models" / "best.pt"
DEFAULT_SUARA_FOLDER = ROOT / "suara-natural-ai" / "cache_ardi"
DEFAULT_CONF = 0.35
DEFAULT_CONF_RAGU = 0.50
DEFAULT_IMGSZ = 512

from fuzzysugeno import KELAS_ID_KE_NAMA, PelacakGerak, analisis_hasil, validasi_nama_kelas
from ultralytics import YOLO


@dataclass
class HasilInferensi:
    waktu: str
    deteksi: list[dict[str, Any]]
    aksi_suara: Optional[str] = None
    suara_diputar: bool = False

    @property
    def jumlah_objek(self) -> int:
        return len(self.deteksi)

    @property
    def deteksi_yakin(self) -> list[dict[str, Any]]:
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
        validasi_nama_kelas(self.model.names)

    def deteksi_gambar(self, gambar: np.ndarray, jarak_us: Optional[float] = None,
                       conf_min: Optional[float] = None) -> HasilInferensi:
        conf = self.conf if conf_min is None else conf_min
        hasil_model = self.model.predict(
            source=gambar,
            imgsz=self.imgsz,
            conf=conf,
            classes=sorted(KELAS_ID_KE_NAMA),
            verbose=False,
        )[0]
        deteksi = analisis_hasil(
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
    def ke_dict(hasil: HasilInferensi) -> dict[str, Any]:
        return {
            "waktu": hasil.waktu,
            "jumlah_objek": hasil.jumlah_objek,
            "jumlah_objek_yakin": len(hasil.deteksi_yakin),
            "jumlah_ragu": hasil.jumlah_ragu,
            "level_tertinggi": hasil.level_tertinggi,
            "urgensi_tertinggi": round(hasil.urgensi_tertinggi, 1),
            "aksi_suara": hasil.aksi_suara,
            "suara_diputar": hasil.suara_diputar,
            "deteksi": hasil.deteksi,
        }

class PerencanaSuara:
    URUTAN_LEVEL = {"AMAN": 0, "INFO": 1, "WASPADA": 2, "BAHAYA": 3}

    def __init__(self, folder: Path) -> None:
        manifest_path = folder / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("skema") not in (2, 3):
            raise ValueError(f"Skema pustaka suara {manifest.get('skema')!r} tidak didukung.")
        self.folder = folder
        self.penutur = str(manifest.get("suara", ""))
        self.kelas_dikenal = set(manifest.get("kelas", []))
        self._pesan_siap = {}
        self._berkas = set()
        self._varian_terakhir = {}
        self._rng = random.Random()
        for key, entries in manifest.get("pesan", {}).items():
            valid = [
                entry for entry in entries
                if entry.get("berkas")
                and str(entry.get("teks", "")).strip()
                and (folder / entry["berkas"]).is_file()
            ]
            if valid:
                self._pesan_siap[key] = valid
                self._berkas.update(entry["berkas"] for entry in valid)
        self.tersedia = set(self._pesan_siap)
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

    def _segmen(self, key: str) -> Optional[dict]:
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
    def _aksi(top: dict, detections: list[dict]) -> str:
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

    def susun(self, detections: list[dict]) -> Optional[dict]:
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
        keys = []
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
        segments = [part for key in keys if (part := self._segmen(key)) is not None]
        if not any(part["kunci"].startswith("benda_") for part in segments):
            return None
        return {
            "level": level_name.upper(),
            "teks": " ".join(part["teks"] for part in segments if part["teks"]),
            "aksi": action,
            "gerak": gerak,
            "segmen": segments,
        }

    def contoh(self) -> Optional[dict]:
        return self.susun([{
            "kelas": "umum",
            "level": "WASPADA",
            "arah": "depan",
            "urgensi": 60.0,
            "jarak_m": 1.0,
        }])

API_KEY = os.environ.get("VEST_API_KEY", "").strip()
API_KEY_CONFIGURED = api_key_is_configured(API_KEY)

if __name__ == "__main__" and not API_KEY_CONFIGURED:
    raise SystemExit(
        "VEST_API_KEY belum aman/valid. Isi .env dengan kunci acak minimal 32 karakter."
    )


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


MODEL_PATH = _project_path(os.environ.get("VEST_MODEL_PATH", DEFAULT_MODEL))
if not MODEL_PATH.is_file():
    trained_model = ROOT / "runs" / "segment" / "runs" / "semua_kelas_yolo26n" / "weights" / "best.pt"
    if trained_model.is_file():
        MODEL_PATH = trained_model
SUARA_FOLDER = _project_path(os.environ.get("VEST_SUARA_FOLDER", DEFAULT_SUARA_FOLDER))
IMGSZ = int(os.environ.get("VEST_IMGSZ", DEFAULT_IMGSZ))
CONF = float(os.environ.get("VEST_CONF", DEFAULT_CONF))
CONF_RAGU = float(os.environ.get("VEST_CONF_RAGU", DEFAULT_CONF_RAGU))
RIWAYAT_PATH = _project_path(os.environ.get("VEST_RIWAYAT_PATH", ROOT / "data" / "riwayat.jsonl"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HOST = os.environ.get("VEST_HOST", "127.0.0.1")
PORT = int(os.environ.get("VEST_PORT", "8080"))
GOOGLE_MAPS_API_KEY = (
    os.environ.get("GOOGLE_MAPS_API_KEY", "")
    or os.environ.get("VITE_GOOGLE_MAPS_API_KEY", "")
).strip()
MAP_DEFAULT_LAT = float(os.environ.get("VEST_MAP_DEFAULT_LAT", "-8.1689"))
MAP_DEFAULT_LNG = float(os.environ.get("VEST_MAP_DEFAULT_LNG", "113.7020"))
MAP_DEFAULT_ZOOM = int(os.environ.get("VEST_MAP_ZOOM", "17"))

RIWAYAT_PATH.parent.mkdir(parents=True, exist_ok=True)

COOKIE_SESI = "vestcare_sesi"
UMUR_SESI_DETIK = 12 * 60 * 60

try:
    PERENCANA_SUARA: Optional[PerencanaSuara] = (
        PerencanaSuara(SUARA_FOLDER) if (SUARA_FOLDER / "manifest.json").is_file() else None
    )
    if PERENCANA_SUARA is None:
        raise FileNotFoundError(f"manifest.json tidak ditemukan di {SUARA_FOLDER}")
    print(
        f"[SUARA] Pustaka browser siap: {SUARA_FOLDER} "
        f"({len(PERENCANA_SUARA.tersedia)} kunci, penutur {PERENCANA_SUARA.penutur or '-'})"
    )
except Exception as e:
    PERENCANA_SUARA = None
    print(f"[PERINGATAN] Pustaka suara browser belum siap: {e}")

ENGINE: Optional[InferensiVest] = None
ENGINE_ERROR: Optional[str] = None
INFERENSI_LOCK = threading.Lock()
try:
    ENGINE = InferensiVest(
        model_path=MODEL_PATH,
        conf=CONF,
        imgsz=IMGSZ,
        conf_ragu=CONF_RAGU,
    )
    print(f"[API] Engine inferensi siap. Model: {MODEL_PATH}")
except Exception as e:
    ENGINE_ERROR = str(e)
    print(f"[PERINGATAN] Engine belum siap: {ENGINE_ERROR}")
    print("  /deteksi akan menolak request sampai engine berhasil dimuat.")

app = FastAPI(
    title="VestCare API",
    description=(
        "Deteksi objek jalan (YOLO-seg) + fuzzy urgensi (Sugeno) + output suara "
        "untuk rompi tunanetra. Dapat diterbitkan melalui ngrok."
    ),
    version="2.0.0",
)


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, error: RequestValidationError):
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


def _pasang_cookie_sesi(response, request: Request) -> None:
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


def _cek_api_key(request: Request, x_api_key: Optional[str]):
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


def _rencana_suara(data: dict) -> Optional[dict]:
    if PERENCANA_SUARA is None:
        return None
    return PERENCANA_SUARA.susun(data.get("deteksi", []))


def _pastikan_engine_siap() -> InferensiVest:
    if ENGINE is None:
        raise HTTPException(status_code=503, detail=f"Engine belum siap: {ENGINE_ERROR}")
    return ENGINE


def _simpan_riwayat(hasil_dict: dict, sumber: str):
    with LATEST_TELEMETRI_LOCK:
        tele = dict(LATEST_TELEMETRI)
    if "posisi" not in hasil_dict and tele.get("fix") and tele.get("lat") is not None and tele.get("lng") is not None:
        hasil_dict["posisi"] = {
            "lat": tele["lat"],
            "lng": tele["lng"],
        }
    entri = {
        "id": uuid.uuid4().hex[:12],
        "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sumber": sumber,
        **hasil_dict,
    }
    with open(RIWAYAT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entri, ensure_ascii=False) + "\n")
    try:
        sinkronisasi = _simpan_deteksi_supabase(entri)
    except (OSError, ValueError, RuntimeError) as error:
        sinkronisasi = {
            "supabase_tersimpan": False,
            "supabase_error": str(error),
        }
    entri.update(sinkronisasi)
    return entri


def _ambil_perangkat_supabase(device_id: Optional[str] = None) -> Optional[dict[str, Any]]:
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
    rows = None
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
    if not isinstance(rows, list):
        raise RuntimeError("Supabase mengembalikan format devices yang tidak valid.")
    return rows[0] if rows else None


def _hubungkan_perangkat_supabase() -> str:
    global SUPABASE_DEVICE_ID

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

    SUPABASE_DEVICE_ID = device_id
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
            detections = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"Gagal membaca duplikat detections dari Supabase (HTTP {error.code}): {detail or error.reason}"
        ) from error
    except (URLError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Gagal membaca detections Supabase untuk deduplikasi: {error}") from error
    if not isinstance(detections, list):
        raise RuntimeError("Supabase mengembalikan format detections yang tidak valid.")

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


def _simpan_deteksi_supabase(entri: dict) -> dict[str, Any]:
    global SUPABASE_LAST_SIGNATURE, SUPABASE_LAST_SAVED_AT
    global SUPABASE_CONNECTED, SUPABASE_CONNECTION_ERROR

    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "Atur SUPABASE_URL dan SUPABASE_SERVICE_ROLE_KEY di .env server untuk menyimpan riwayat."
        )
    try:
        device_id = str(uuid.UUID(SUPABASE_DEVICE_ID))
    except ValueError as error:
        raise ValueError("VEST_SUPABASE_DEVICE_ID harus berupa UUID yang valid.") from error

    latest_by_object = {}
    for item in entri.get("deteksi", []):
        if item.get("ragu"):
            continue
        object_name = str(item.get("kelas", item.get("object", ""))).strip().lower()
        if not object_name or object_name not in KELAS_ID_KE_NAMA.values():
            continue
        current = latest_by_object.get(object_name)
        if current is None or float(item.get("urgensi", 0) or 0) > float(current.get("urgensi", 0) or 0):
            latest_by_object[object_name] = item
    deteksi = list(latest_by_object.values())
    if not deteksi:
        return {"supabase_tersimpan": True, "supabase_jumlah": 0}

    signature = "|".join(sorted(
        f"{item.get('kelas', item.get('object', ''))}:{item.get('level', '')}:{item.get('arah', '')}"
        for item in deteksi
    ))
    now = time.monotonic()
    with SUPABASE_SYNC_LOCK:
        if signature == SUPABASE_LAST_SIGNATURE and now - SUPABASE_LAST_SAVED_AT < 10:
            return {"supabase_tersimpan": True, "supabase_jumlah": 0}

        created_at = datetime.now().astimezone().isoformat()
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
            "Content-Type": "application/json",
        }

        def request_supabase(path: str, method: str, payload: Optional[list[dict]] = None,
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

        if not SUPABASE_CONNECTED:
            _hubungkan_perangkat_supabase()
        SUPABASE_CONNECTED = True
        SUPABASE_CONNECTION_ERROR = None

        posisi = entri.get("posisi") or {}
        tingkat_ke_urgensi = {
            "BAHAYA": "Tinggi",
            "WASPADA": "Sedang",
            "INFO": "Rendah",
            "AMAN": "Rendah",
        }
        rows = [{
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
        existing_rows = request_supabase(f"detections?{existing_query}", "GET") or []
        latest_id_by_object = {}
        duplicate_ids = []
        for existing in existing_rows:
            object_name = str(existing.get("object", "")).strip().lower()
            if not object_name:
                continue
            if object_name in latest_id_by_object:
                duplicate_ids.append(str(existing["id"]))
            else:
                latest_id_by_object[object_name] = str(existing["id"])

        inserts = []
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

        SUPABASE_LAST_SIGNATURE = signature
        SUPABASE_LAST_SAVED_AT = now
        return {"supabase_tersimpan": True, "supabase_jumlah": len(rows)}


def _sinkronisasi_telemetri_supabase(data: dict) -> None:
    global LATEST_GPS_LOG_AT, LAST_DEVICE_UPDATE_AT
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return

    now = time.time()
    try:
        device_id = str(uuid.UUID(SUPABASE_DEVICE_ID))
    except (ValueError, TypeError):
        return

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }

    if now - LAST_DEVICE_UPDATE_AT >= 15.0:
        LAST_DEVICE_UPDATE_AT = now
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
        if now - LATEST_GPS_LOG_AT >= 5.0:
            LATEST_GPS_LOG_AT = now
            payload_gps = [{
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


def _baca_riwayat(limit: int):
    if not RIWAYAT_PATH.exists():
        return {"total": 0, "data": []}
    with open(RIWAYAT_PATH, encoding="utf-8") as f:
        baris = [json.loads(l) for l in f if l.strip()]
    terbaru = list(reversed(baris))[:limit]
    return {"total": len(baris), "ditampilkan": len(terbaru), "data": terbaru}


def _catat_jalur(data: dict) -> None:
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


def _ringkasan_telemetri(data: dict) -> dict[str, Any]:
    now = time.time()
    updated_at = float(data.get("updated_at") or 0)
    umur = max(0.0, now - updated_at) if updated_at else None
    return {
        "telemetri": data,
        "jalur": _salin_jalur(),
        "online": umur is not None and umur < 15.0,
        "umur_detik": round(umur, 1) if umur is not None else None,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _alamat_ngrok_aktif(port: int) -> Optional[str]:
    try:
        with urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as response:
            tunnels = json.load(response).get("tunnels", [])
    except (OSError, URLError, json.JSONDecodeError):
        return None
    return next(
        (
            tunnel["public_url"]
            for tunnel in tunnels
            if tunnel.get("public_url", "").startswith("https://")
            and str(tunnel.get("config", {}).get("addr", "")).rstrip("/").endswith(f":{port}")
        ),
        None,
    )


def _server_lokal_aktif(port: int) -> bool:
    """True bila sudah ada server VestCare yang melayani port tersebut."""
    try:
        with urlopen(f"http://127.0.0.1:{port}/status", timeout=1) as response:
            return response.status == 200
    except (OSError, URLError):
        return False


def _simpan_url_publik(url: str) -> Path:
    path = ROOT / "data" / "public_url.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(url + "\n", encoding="utf-8")
    return path


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


@app.get("/info")
def info():
    return {
        "nama": "VestCare API",
        "versi": "2.0.0",
        "aplikasi_browser": "/app",
        "engine_siap": ENGINE is not None,
        "model_exists": MODEL_PATH.exists(),
        "imgsz": IMGSZ,
        "conf": CONF,
        "conf_ragu": CONF_RAGU,
        "suara_browser": "klip Ardi (suara-natural-ai)",
        "pustaka_suara_siap": PERENCANA_SUARA is not None,
        "autentikasi": "aktif" if API_KEY_CONFIGURED else "belum dikonfigurasi",
        "dokumentasi": "/docs",
        "status": "/status",
    }


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
def aplikasi_browser(request: Request):
    if not DASHBOARD_INDEX.is_file():
        raise HTTPException(
            status_code=503,
            detail="Dashboard React belum dibangun. Jalankan `npm run build` di folder vest-care-react.",
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
):
    _cek_api_key(request, x_api_key)
    if PERENCANA_SUARA is None:
        raise HTTPException(status_code=503, detail="Pustaka suara Ardi belum tersedia.")
    rencana = PERENCANA_SUARA.contoh()
    if rencana is None:
        raise HTTPException(status_code=404, detail="Klip contoh tidak tersedia.")
    return {"suara": rencana}


@app.get("/suara/{nama_berkas}", include_in_schema=False)
def berkas_suara(
    nama_berkas: str,
    request: Request,
    x_api_key: Optional[str] = Header(None),
):
    _cek_api_key(request, x_api_key)
    if PERENCANA_SUARA is None or not PERENCANA_SUARA.berkas_diizinkan(nama_berkas):
        raise HTTPException(status_code=404, detail="Berkas suara tidak ditemukan.")
    return FileResponse(
        SUARA_FOLDER / nama_berkas,
        media_type="audio/mpeg",
        headers={"Cache-Control": "private, max-age=86400"},
    )


@app.get("/status")
def status():
    return {
        "server": "VestCare API",
        "versi": "2.0.0",
        "engine_siap": ENGINE is not None,
        "api_terproteksi": API_KEY_CONFIGURED,
        "pustaka_suara_siap": PERENCANA_SUARA is not None,
        "supabase_sinkronisasi_aktif": bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY),
        "supabase_terhubung": SUPABASE_CONNECTED,
        "supabase_device_id": SUPABASE_DEVICE_ID if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY else None,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.on_event("startup")
async def hubungkan_supabase_saat_server_mulai():
    global SUPABASE_CONNECTED, SUPABASE_CONNECTION_ERROR
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        SUPABASE_CONNECTION_ERROR = "Konfigurasi Supabase belum lengkap."
        print(f"[SUPABASE] {SUPABASE_CONNECTION_ERROR}")
        return
    try:
        device_id = await run_in_threadpool(_hubungkan_perangkat_supabase)
        removed = await run_in_threadpool(_deduplikasi_deteksi_supabase, device_id)
    except ValueError as error:
        SUPABASE_CONNECTED = False
        SUPABASE_CONNECTION_ERROR = str(error)
        print(f"[SUPABASE] Konfigurasi tidak valid: {SUPABASE_CONNECTION_ERROR}")
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
                    SUPABASE_CONNECTED = False
                    SUPABASE_CONNECTION_ERROR = str(error)
                    print(f"[SUPABASE] Koneksi saat startup gagal: {SUPABASE_CONNECTION_ERROR}")
                    return

    SUPABASE_CONNECTED = True
    SUPABASE_CONNECTION_ERROR = None
    print(
        f"[SUPABASE] Terhubung. Perangkat server: {device_id}; "
        f"duplikat kelas dihapus: {removed}"
    )


class MasukanTelemetri(BaseModel):
    jarak: Optional[float] = Field(None, description="jarak ultrasonik dalam meter")
    valid_jarak: Optional[bool] = Field(None, description="apakah pembacaan ultrasonik valid")
    lat: Optional[float] = Field(None, ge=-90, le=90, description="latitude dari GPS dalam derajat")
    lng: Optional[float] = Field(None, ge=-180, le=180, description="longitude dari GPS dalam derajat")
    alt: Optional[float] = Field(None, description="ketinggian (meter)")
    spd: Optional[float] = Field(None, description="kecepatan (km/jam)")
    sat: Optional[int] = Field(None, description="jumlah satelit terkunci")
    hdop: Optional[float] = Field(None, description="horizontal dilution of precision")
    fix: Optional[bool] = Field(None, description="apakah GPS fix lock valid")
    terbaca: Optional[bool] = Field(None, description="apakah modul GPS merespon")
    waktu: Optional[str] = Field(None, description="waktu GPS")
    battery: Optional[float] = Field(None, description="persentase baterai")


@app.post("/telemetri")
@app.post("/api/telemetri")
async def telemetri_masuk(
    m: MasukanTelemetri,
    background_tasks: BackgroundTasks,
):
    """Public telemetry endpoint for Wemos devices configured with Wi-Fi only."""
    global LATEST_TELEMETRI
    now = time.time()
    gps_fix = bool(m.fix and m.lat is not None and m.lng is not None)
    update_data = {
        "jarak": float(m.jarak) if m.jarak is not None and m.valid_jarak else None,
        "valid_jarak": bool(m.valid_jarak),
        "lat": float(m.lat) if gps_fix else None,
        "lng": float(m.lng) if gps_fix else None,
        "alt": float(m.alt) if m.alt is not None else None,
        "spd": float(m.spd) if m.spd is not None else None,
        "sat": int(m.sat or 0),
        "hdop": float(m.hdop or 0.0),
        "fix": gps_fix,
        "terbaca": bool(m.terbaca),
        "waktu": m.waktu or datetime.now().strftime("%H:%M:%S"),
        "battery": m.battery,
        "updated_at": now,
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
def telemetri_status(request: Request, x_api_key: Optional[str] = Header(None)):
    with LATEST_TELEMETRI_LOCK:
        data = dict(LATEST_TELEMETRI)
    return _ringkasan_telemetri(data)


@app.get("/telemetri/stream", include_in_schema=False)
@app.get("/api/telemetri/stream", include_in_schema=False)
async def telemetri_stream(
    request: Request,
    x_api_key: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, description="API key untuk klien non-browser"),
):
    """Server-Sent Events: dorong telemetri Wemos ke dashboard seketika."""
    if API_KEY_CONFIGURED:
        _cek_api_key(request, x_api_key or api_key)

    async def peristiwa():
        signature_terakhir: Optional[tuple] = None
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


@app.get("/config")
def konfigurasi_publik():
    """Konfigurasi publik dashboard (kunci Google Maps memang kunci browser)."""
    return {
        "versi": "2.0.0",
        "google_maps_api_key": GOOGLE_MAPS_API_KEY,
        "map_default_center": {"lat": MAP_DEFAULT_LAT, "lng": MAP_DEFAULT_LNG},
        "map_zoom": MAP_DEFAULT_ZOOM,
        "telemetri_stream": "/api/telemetri/stream",
        "telemetri_poll_ms": 1000,
        "dashboard_poll_ms": 10000,
    }


@app.get("/dashboard/data")
def dashboard_data(request: Request, x_api_key: Optional[str] = Header(None)):
    _cek_api_key(request, x_api_key)
    with LATEST_TELEMETRI_LOCK:
        live_telemetri = dict(LATEST_TELEMETRI)
    is_live_online = (time.time() - live_telemetri.get("updated_at", 0)) < 15.0

    try:
        device_id = str(uuid.UUID(SUPABASE_DEVICE_ID))
    except (ValueError, TypeError):
        device_id = SUPABASE_DEVICE_FALLBACK

    device_rows = []
    detections = []
    gps_rows = []

    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        headers = {
            "apikey": SUPABASE_SERVICE_ROLE_KEY,
            "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        }

        def baca_tabel(path: str) -> list[dict[str, Any]]:
            url = f"{SUPABASE_URL}/rest/v1/{path}"
            try:
                with urlopen(UrlRequest(url, headers=headers), timeout=8) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except Exception:
                return []
            return data if isinstance(data, list) else []

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

    device_result = device_rows[0] if device_rows else {
        "id": device_id,
        "name": "VestCare Rompi",
        "student_name": "Siswa VestCare",
        "school": "VestCare",
        "battery": live_telemetri.get("battery"),
        "online": is_live_online,
        "last_seen": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    if is_live_online:
        device_result["online"] = True
        if live_telemetri.get("battery") is not None:
            device_result["battery"] = live_telemetri["battery"]

    gps_result = gps_rows[0] if gps_rows and not is_live_online else None
    if live_telemetri.get("fix") and live_telemetri.get("lat") is not None and live_telemetri.get("lng") is not None:
        gps_result = {
            "id": "live-wemos",
            "device_id": device_id,
            "lat": live_telemetri["lat"],
            "lng": live_telemetri["lng"],
            "accuracy": live_telemetri.get("hdop", 1.0),
            "created_at": datetime.now().astimezone().isoformat(),
        }

    return {
        "device": device_result,
        "detections": detections,
        "gps": gps_result,
        "telemetri": live_telemetri,
        "jalur": _salin_jalur(),
        "telemetri_online": is_live_online,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/deteksi")
async def deteksi(
    request: Request,
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, ge=0.03, le=3.0, description="jarak ultrasonik depan dalam METER"),
    mode_realtime: bool = Form(False, description="lewati penyimpanan riwayat untuk frame kamera realtime"),
    x_api_key: Optional[str] = Header(None),
):
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
    if mode_realtime:
        return JSONResponse(data)
    entri = await run_in_threadpool(_simpan_riwayat, data, "deteksi")
    return JSONResponse(entri)


@app.post("/deteksi/suara")
async def deteksi_suara(
    request: Request,
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, ge=0.03, le=3.0, description="jarak ultrasonik depan dalam METER"),
    x_api_key: Optional[str] = Header(None),
):
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
    return JSONResponse(entri)


class MasukanFuzzy(BaseModel):
    skor_risiko: float = Field(..., ge=0, le=1, allow_inf_nan=False)
    jarak_m: Optional[float] = Field(None, ge=0, allow_inf_nan=False)


@app.post("/peringatan")
def peringatan(m: MasukanFuzzy, request: Request, x_api_key: Optional[str] = Header(None)):
    _cek_api_key(request, x_api_key)
    from fuzzysugeno import hitung_peringatan
    return {"skor_risiko": m.skor_risiko, "jarak_m": m.jarak_m,
            "peringatan": hitung_peringatan(m.skor_risiko, m.jarak_m)}


@app.get("/riwayat")
def riwayat(
    request: Request,
    limit: int = Query(20, ge=1, le=500, description="jumlah entri terakhir yang diambil"),
    x_api_key: Optional[str] = Header(None),
):
    _cek_api_key(request, x_api_key)
    return _baca_riwayat(limit)


if DASHBOARD_DIR.is_dir():
    app.mount("/", StaticFiles(directory=DASHBOARD_DIR, html=True), name="dashboard")


if __name__ == "__main__":
    import uvicorn

    if not API_KEY_CONFIGURED:
        raise SystemExit(
            "VEST_API_KEY belum aman/valid. Isi .env dengan kunci acak minimal 32 karakter."
        )
    if ENGINE is None:
        raise SystemExit(f"Engine deteksi gagal dimuat: {ENGINE_ERROR}")

    executable = shutil.which(os.environ.get("NGROK_EXECUTABLE", "ngrok"))

    server = None
    server_thread = None
    if _server_lokal_aktif(PORT):
        print(f"[INFO] Server VestCare sudah aktif di http://127.0.0.1:{PORT}; memakai proses yang ada.")
    else:
        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, reload=False))
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not server_thread.is_alive():
                raise SystemExit(f"Server API berhenti sebelum siap (port {PORT} mungkin dipakai proses lain).")
            if _server_lokal_aktif(PORT):
                break
            time.sleep(0.25)
        else:
            raise SystemExit(f"Server API tidak siap dalam 30 detik pada port {PORT}.")

    tunnel = None
    try:
        public_url = _alamat_ngrok_aktif(PORT) if executable else None
        if public_url is None and executable is not None:
            tunnel = subprocess.Popen(
                [executable, "http", f"http://127.0.0.1:{PORT}"],
                cwd=ROOT,
            )
            print("[INFO] Menunggu alamat HTTPS ngrok...")
            url_deadline = time.monotonic() + 60
            while time.monotonic() < url_deadline:
                if tunnel.poll() is not None:
                    print(f"[WARN] ngrok berhenti dengan kode {tunnel.returncode}.")
                    break
                public_url = _alamat_ngrok_aktif(PORT)
                if public_url:
                    break
                time.sleep(0.5)

        if public_url is None:
            if executable is None:
                print("[WARN] ngrok tidak ditemukan; server lokal tetap berjalan tanpa URL publik.")
            else:
                print("[WARN] Alamat HTTPS ngrok tidak tersedia; server lokal tetap berjalan.")
            if tunnel is not None and tunnel.poll() is None:
                tunnel.terminate()
                try:
                    tunnel.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    tunnel.kill()
                    tunnel.wait()
            tunnel = None
        else:
            path_url = _simpan_url_publik(public_url)
            print(f"[INFO] Dashboard publik : {public_url}")
            print(f"[INFO] Dokumentasi API  : {public_url}/docs")
            print(f"[INFO] URL disimpan di  : {path_url}")

        print(f"[INFO] Dashboard lokal  : http://127.0.0.1:{PORT}")

        while True:
            server_alive = server_thread is not None and server_thread.is_alive()
            tunnel_alive = tunnel is not None and tunnel.poll() is None
            if not server_alive and not tunnel_alive:
                break
            if tunnel is not None and not tunnel_alive:
                print("[WARN] Proses tunnel berhenti; server lokal tetap berjalan.")
                tunnel = None
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        if tunnel is not None and tunnel.poll() is None:
            tunnel.terminate()
            try:
                tunnel.wait(timeout=10)
            except subprocess.TimeoutExpired:
                tunnel.kill()
                tunnel.wait()
        if server is not None:
            server.should_exit = True
        if server_thread is not None:
            server_thread.join(timeout=10)
