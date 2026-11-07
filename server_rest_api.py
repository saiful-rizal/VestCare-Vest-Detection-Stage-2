from __future__ import annotations

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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import sys
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import urlopen

import numpy as np
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from PIL import Image
from starlette.concurrency import run_in_threadpool
import io

ROOT = Path(__file__).resolve().parent
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

def api_key_is_configured(value: Optional[str]) -> bool:
    if value is None or len(value.strip()) < 32:
        return False
    normalized = value.strip().lower()
    return not any(marker in normalized for marker in ("contoh", "ganti", "rahasia-anda"))


DEFAULT_MODEL = ROOT / "models" / "best.pt"
DEFAULT_SUARA_FOLDER = ROOT / "suara-natural-ai" / "cache_ardi"
DEFAULT_CONF = 0.35
DEFAULT_IMGSZ = 416

from fuzzysugeno import KELAS_ID_KE_NAMA, analisis_hasil, validasi_nama_kelas  # noqa: E402
from ultralytics import YOLO  # noqa: E402


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
    def level_tertinggi(self) -> str:
        return self.deteksi[0]["level"] if self.deteksi else "AMAN"

    @property
    def urgensi_tertinggi(self) -> float:
        return float(self.deteksi[0]["urgensi"]) if self.deteksi else 0.0


class InferensiVest:
    def __init__(self, model_path: Path, conf: float, imgsz: int) -> None:
        if not model_path.is_file():
            raise FileNotFoundError(f"Bobot model tidak ditemukan: {model_path}")
        self.conf = conf
        self.imgsz = imgsz
        self.model = YOLO(str(model_path))
        validasi_nama_kelas(self.model.names)

    def deteksi_gambar(self, gambar: np.ndarray, jarak_us: Optional[float] = None,
                       conf_min: Optional[float] = None) -> HasilInferensi:
        conf = self.conf if conf_min is None else conf_min
        hasil_model = self.model.predict(
            source=gambar,
            imgsz=self.imgsz,
            conf=conf,
            verbose=False,
        )[0]
        deteksi = analisis_hasil(hasil_model, conf_min=conf, jarak_us=jarak_us)
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
        active = [item for item in detections if str(item.get("level", "")).upper() != "AMAN"]
        if not active:
            if not detections:
                safe = self._segmen("jalur_aman")
                return {
                    "level": "AMAN",
                    "teks": safe["teks"],
                    "aksi": "lurus",
                    "segmen": [safe],
                } if safe else None
            active = detections
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
        keys = []
        if level_name in ("waspada", "bahaya"):
            keys.append(f"awal_{level_name}")
        keys.append(f"benda_{class_name}_{direction}_netral")
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
RIWAYAT_PATH = _project_path(os.environ.get("VEST_RIWAYAT_PATH", ROOT / "data" / "riwayat.jsonl"))
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HOST = os.environ.get("VEST_HOST", "127.0.0.1")
PORT = int(os.environ.get("VEST_PORT", "8080"))

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
    )
    print(f"[API] Engine inferensi siap. Model: {MODEL_PATH}")
except Exception as e:  # server tetap bisa start & /docs bisa dibuka buat debug
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
    entri = {
        "id": uuid.uuid4().hex[:12],
        "waktu": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sumber": sumber,
        **hasil_dict,
    }
    with open(RIWAYAT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entri, ensure_ascii=False) + "\n")
    return entri


def _baca_riwayat(limit: int):
    if not RIWAYAT_PATH.exists():
        return {"total": 0, "data": []}
    with open(RIWAYAT_PATH, encoding="utf-8") as f:
        baris = [json.loads(l) for l in f if l.strip()]
    terbaru = list(reversed(baris))[:limit]
    return {"total": len(baris), "ditampilkan": len(terbaru), "data": terbaru}


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
        "suara_browser": "klip Ardi (suara-natural-ai)",
        "pustaka_suara_siap": PERENCANA_SUARA is not None,
        "autentikasi": "aktif" if API_KEY_CONFIGURED else "belum dikonfigurasi",
        "dokumentasi": "/docs",
        "status": "/status",
    }


@app.get("/", include_in_schema=False)
@app.get("/app", include_in_schema=False)
def aplikasi_browser(request: Request):
    response = FileResponse(
        ROOT / "web" / "index.html",
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
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/deteksi")
async def deteksi(
    request: Request,
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, ge=0.03, le=3.0, description="jarak ultrasonik depan dalam METER"),
    x_api_key: Optional[str] = Header(None),
):
    _cek_api_key(request, x_api_key)
    img = await _baca_gambar(gambar)

    hasil = await run_in_threadpool(_jalankan_deteksi, img, jarak_m)
    data = InferensiVest.ke_dict(hasil)
    data["suara"] = _rencana_suara(data)
    entri = _simpan_riwayat(data, sumber="deteksi")
    return JSONResponse(entri)


@app.post("/deteksi/suara")
async def deteksi_suara(
    request: Request,
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, ge=0.03, le=3.0, description="jarak ultrasonik depan dalam METER"),
    x_api_key: Optional[str] = Header(None),
):
    _cek_api_key(request, x_api_key)
    img = await _baca_gambar(gambar)

    hasil = await run_in_threadpool(_jalankan_deteksi, img, jarak_m)
    data = InferensiVest.ke_dict(hasil)
    data["suara"] = _rencana_suara(data)
    entri = _simpan_riwayat(data, sumber="deteksi_suara")
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


if __name__ == "__main__":
    import uvicorn

    if not API_KEY_CONFIGURED:
        raise SystemExit(
            "VEST_API_KEY belum aman/valid. Isi .env dengan kunci acak minimal 32 karakter."
        )
    if ENGINE is None:
        raise SystemExit(f"Engine deteksi gagal dimuat: {ENGINE_ERROR}")
    executable = shutil.which(os.environ.get("NGROK_EXECUTABLE", "ngrok"))
    if executable is None:
        raise SystemExit("ngrok tidak ditemukan. Install ngrok dan pastikan tersedia di PATH.")

    server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=PORT, reload=False))
    server_thread = threading.Thread(target=server.run, daemon=True)
    tunnel = None
    server_thread.start()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if not server_thread.is_alive():
                raise RuntimeError("Server API berhenti sebelum siap.")
            try:
                with urlopen(f"http://127.0.0.1:{PORT}/status", timeout=1) as response:
                    if response.status == 200:
                        break
            except (OSError, URLError):
                time.sleep(0.25)
        else:
            raise TimeoutError("Server API tidak siap dalam 30 detik.")

        public_url = _alamat_ngrok_aktif(PORT)
        if public_url is None:
            tunnel = subprocess.Popen([executable, "http", f"http://127.0.0.1:{PORT}"])
            print("[INFO] Menunggu alamat HTTPS ngrok...")
            url_deadline = time.monotonic() + 60
            while time.monotonic() < url_deadline:
                if tunnel.poll() is not None:
                    raise RuntimeError(f"ngrok berhenti dengan kode {tunnel.returncode}.")
                public_url = _alamat_ngrok_aktif(PORT)
                if public_url:
                    break
                time.sleep(0.5)
            if public_url is None:
                raise TimeoutError("Alamat HTTPS ngrok tidak tersedia. Periksa authtoken dan koneksi ngrok.")

        print(f"[INFO] Buka halaman kamera: {public_url}")
        while server_thread.is_alive() and (tunnel is None or tunnel.poll() is None):
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
        server.should_exit = True
        server_thread.join(timeout=10)
