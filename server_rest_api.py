"""SERVER REST API VESTCARE - deteksi objek (YOLO-seg) + fuzzy urgensi + output suara.

Alur:
  Klien / ESP32-CAM (gambar + jarak ultrasonik opsional)
      -> POST /deteksi atau /deteksi/suara
      -> YOLO-seg mendeteksi objek dari bobot hasil training (models/best.pt)
      -> Fuzzy Sugeno menghitung tingkat urgensi per objek (AMAN/INFO/WASPADA/BAHAYA)
      -> Objek paling mendesak diucapkan melalui speaker rompi (output suara)
      -> JSON dikembalikan ke klien (deteksi, urgensi, level, aksi suara)

ENDPOINT
  GET  /app                           halaman kamera browser untuk ponsel
  GET  /                              info singkat + status model & suara
  GET  /docs                          dokumentasi interaktif FastAPI/Swagger
  POST /deteksi                       unggah gambar (multipart) + jarak_m opsional -> JSON deteksi + fuzzy
  POST /deteksi/suara                 sama dengan /deteksi tapi memutar suara peringatan di server
  POST /peringatan                    fuzzy saja: JSON {skor_risiko, jarak_m} -> tingkat peringatan
  GET  /riwayat?limit=20              N deteksi terakhir yang tersimpan
  GET  /status                        status server, model, dan pemutar suara

AUTENTIKASI
  Endpoint operasi selain /, /app, /docs, dan /status butuh header:
  X-API-Key: <VEST_API_KEY>. Kunci acak minimal 32 karakter wajib dikonfigurasi.

CARA JALANKAN
  pip install -r requirements.txt
  Salin .env.example menjadi .env dan isi VEST_API_KEY
  python start_server.py
  # aplikasi: http://127.0.0.1:8000/app ; dokumentasi: http://127.0.0.1:8000/docs

UJI CEPAT (curl)
  curl -X POST http://localhost:8000/deteksi \
       -H "X-API-Key: kunci-rahasiamu" \
       -F "gambar=@tes.jpg" -F "jarak_m=0.45"

  curl -X POST http://localhost:8000/deteksi/suara \
       -H "X-API-Key: kunci-rahasiamu" \
       -F "gambar=@tes.jpg" -F "jarak_m=0.45"

KONFIGURASI (env var)
  VEST_API_KEY      kunci API
  VEST_MODEL_PATH   path bobot .pt          (default: models/best.pt)
  VEST_SUARA_FOLDER folder pustaka klip suara (default: cache_suara)
  VEST_IMGSZ        ukuran gambar inferensi  (default: 416 - SAMAKAN dengan training!)
  VEST_CONF         ambang confidence        (default: 0.35)
  VEST_RIWAYAT_PATH file riwayat .jsonl     (default: data/riwayat.jsonl)
  VEST_TANPA_SUARA  1 = suara browser ponsel, bukan speaker server (default)
"""
from __future__ import annotations

import json
import hmac
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
import sys
from typing import Optional

import numpy as np
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field
from PIL import Image
import io

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config_env import api_key_is_configured, load_project_env  # noqa: E402

load_project_env()

# ---- Pipeline inferensi terpadu (YOLO + fuzzy + suara) ----
from inferensi_vest import (  # noqa: E402
    InferensiVest,
    HasilInferensi,
    DEFAULT_MODEL,
    DEFAULT_SUARA_FOLDER,
    DEFAULT_CONF,
    DEFAULT_IMGSZ,
)

# ---------- konfigurasi ----------
API_KEY = os.environ.get("VEST_API_KEY", "").strip()
API_KEY_CONFIGURED = api_key_is_configured(API_KEY)


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
TANPA_SUARA = os.environ.get("VEST_TANPA_SUARA", "1").lower() in ("1", "true", "yes", "on")
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
HOST = os.environ.get("VEST_HOST", "127.0.0.1")
PORT = int(os.environ.get("VEST_PORT", "8000"))

RIWAYAT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------- muat engine inferensi ----------
ENGINE: Optional[InferensiVest] = None
ENGINE_ERROR: Optional[str] = None
try:
    ENGINE = InferensiVest(
        model_path=MODEL_PATH,
        suara_folder=SUARA_FOLDER,
        conf=CONF,
        imgsz=IMGSZ,
        paksa_tts_fallback=False,
        suara_aktif=not TANPA_SUARA,
    )
    print(f"[API] Engine inferensi siap. Model: {MODEL_PATH} | Suara: {'matikan' if TANPA_SUARA else SUARA_FOLDER}")
except Exception as e:  # server tetap bisa start & /docs bisa dibuka buat debug
    ENGINE_ERROR = str(e)
    print(f"[PERINGATAN] Engine belum siap: {ENGINE_ERROR}")
    print("  /deteksi akan menolak request sampai engine berhasil dimuat.")

# ---------- app ----------
app = FastAPI(
    title="VestCare API",
    description=(
        "Deteksi objek jalan (YOLO-seg) + fuzzy urgensi (Sugeno) + output suara "
        "untuk rompi tunanetra. Diterbitkan via Cloudflare Tunnel."
    ),
    version="2.0.0",
)
# ---------- autentikasi ----------
def _cek_api_key(x_api_key: Optional[str]):
    if not API_KEY_CONFIGURED:
        raise HTTPException(
            status_code=503,
            detail="API belum dikonfigurasi. Isi VEST_API_KEY dengan kunci acak minimal 32 karakter.",
        )
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode("utf-8"),
        API_KEY.encode("utf-8"),
    ):
        raise HTTPException(status_code=401, detail="X-API-Key salah atau tidak disertakan.")


def _pastikan_engine_siap():
    if ENGINE is None:
        raise HTTPException(status_code=503, detail=f"Engine belum siap: {ENGINE_ERROR}")


# ---------- riwayat ----------
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


# ---------- deteksi inti ----------
def _jalankan_deteksi(gambar_pil: Image.Image, jarak_m: Optional[float], putar_suara: bool):
    """PIL.Image RGB -> HasilInferensi (deteksi + fuzzy + suara opsional)."""
    _pastikan_engine_siap()
    assert ENGINE is not None
    hasil = ENGINE.deteksi_gambar(
        np.array(gambar_pil.convert("RGB")),
        jarak_us=jarak_m,
        conf_min=CONF,
    )
    if putar_suara:
        teks = ENGINE.putar_suara(hasil)
        hasil.aksi_suara = teks
        hasil.suara_diputar = teks is not None
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


# ---------- endpoint ----------
@app.get("/")
def root():
    return {
        "nama": "VestCare API",
        "versi": "2.0.0",
        "aplikasi_browser": "/app",
        "engine_siap": ENGINE is not None,
        "model_exists": MODEL_PATH.exists(),
        "imgsz": IMGSZ,
        "conf": CONF,
        "suara_browser": "Web Speech API (ponsel)",
        "suara_server": "nonaktif" if TANPA_SUARA else "aktif",
        "autentikasi": "aktif" if API_KEY_CONFIGURED else "belum dikonfigurasi",
        "dokumentasi": "/docs",
        "status": "/status",
    }


@app.get("/app", include_in_schema=False)
def aplikasi_browser():
    return FileResponse(ROOT / "web" / "index.html")


@app.get("/status")
def status():
    """Status ringkas tanpa autentikasi (untuk pemantauan tunnel/uptime)."""
    return {
        "server": "VestCare API",
        "versi": "2.0.0",
        "engine_siap": ENGINE is not None,
        "api_terproteksi": API_KEY_CONFIGURED,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/deteksi")
async def deteksi(
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, ge=0.03, le=3.0, description="jarak ultrasonik depan dalam METER"),
    x_api_key: Optional[str] = Header(None),
):
    _cek_api_key(x_api_key)
    img = await _baca_gambar(gambar)

    hasil = _jalankan_deteksi(img, jarak_m, putar_suara=False)
    entri = _simpan_riwayat(ENGINE.ke_dict(hasil), sumber="deteksi")
    return JSONResponse(entri)


@app.post("/deteksi/suara")
async def deteksi_suara(
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, ge=0.03, le=3.0, description="jarak ultrasonik depan dalam METER"),
    x_api_key: Optional[str] = Header(None),
):
    """Deteksi + putar suara peringatan di server (speaker rompi)."""
    _cek_api_key(x_api_key)
    img = await _baca_gambar(gambar)

    hasil = _jalankan_deteksi(img, jarak_m, putar_suara=True)
    entri = _simpan_riwayat(ENGINE.ke_dict(hasil), sumber="deteksi_suara")
    return JSONResponse(entri)


class MasukanFuzzy(BaseModel):
    skor_risiko: float = Field(..., ge=0, le=1, description="skor risiko 0-1")
    jarak_m: Optional[float] = Field(None, ge=0, description="jarak ultrasonik dalam METER")


@app.post("/peringatan")
def peringatan(m: MasukanFuzzy, x_api_key: Optional[str] = Header(None)):
    """Fuzzy Sugeno berdiri sendiri: tidak butuh model/gambar."""
    _cek_api_key(x_api_key)
    from fuzzysugeno import hitung_peringatan
    return {"skor_risiko": m.skor_risiko, "jarak_m": m.jarak_m,
            "peringatan": hitung_peringatan(m.skor_risiko, m.jarak_m)}


@app.get("/riwayat")
def riwayat(
    limit: int = Query(20, ge=1, le=500, description="jumlah entri terakhir yang diambil"),
    x_api_key: Optional[str] = Header(None),
):
    _cek_api_key(x_api_key)
    return _baca_riwayat(limit)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server_rest_api:app", host=HOST, port=PORT, reload=False)
