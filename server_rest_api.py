"""SERVER REST API VESTCARE - deteksi objek (YOLO-seg) + fuzzy urgensi + output suara.

Alur:
  Klien / ESP32-CAM (gambar + jarak ultrasonik opsional)
      -> POST /deteksi atau /deteksi/suara
      -> YOLO-seg mendeteksi objek dari bobot hasil training (models/best.pt)
      -> Fuzzy Sugeno menghitung tingkat urgensi per objek (AMAN/INFO/WASPADA/BAHAYA)
      -> Objek paling mendesak diucapkan melalui speaker rompi (output suara)
      -> JSON dikembalikan ke klien (deteksi, urgensi, level, aksi suara)

ENDPOINT
  GET  /                              info singkat + status model & suara
  GET  /docs                          dokumentasi interaktif FastAPI/Swagger
  POST /deteksi                       unggah gambar (multipart) + jarak_m opsional -> JSON deteksi + fuzzy
  POST /deteksi/suara                 sama dengan /deteksi tapi memutar suara peringatan di server
  POST /peringatan                    fuzzy saja: JSON {skor_risiko, jarak_m} -> tingkat peringatan
  GET  /riwayat?limit=20              N deteksi terakhir yang tersimpan
  GET  /status                        status server, model, dan pemutar suara

AUTENTIKASI
  Semua endpoint selain /, /docs, dan /status butuh header:  X-API-Key: <VEST_API_KEY>
  Set env var VEST_API_KEY. Kalau tidak diset, autentikasi dimatikan (dev only).

CARA JALANKAN
  pip install -r requirements.txt
  set VEST_API_KEY=kunci-rahasiamu        (Windows PowerShell: $env:VEST_API_KEY="...")
  python server_rest_api.py
  # server jalan di http://0.0.0.0:8000 , dokumentasi di http://0.0.0.0:8000/docs

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
  VEST_TANPA_SUARA  1 = matikan output suara (untuk server tanpa speaker)
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from PIL import Image
import io

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

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
API_KEY = os.environ.get("VEST_API_KEY")  # None = autentikasi dimatikan (dev only)
MODEL_PATH = Path(os.environ.get("VEST_MODEL_PATH", DEFAULT_MODEL))
SUARA_FOLDER = Path(os.environ.get("VEST_SUARA_FOLDER", DEFAULT_SUARA_FOLDER))
IMGSZ = int(os.environ.get("VEST_IMGSZ", DEFAULT_IMGSZ))
CONF = float(os.environ.get("VEST_CONF", DEFAULT_CONF))
RIWAYAT_PATH = Path(os.environ.get("VEST_RIWAYAT_PATH", ROOT / "data" / "riwayat.jsonl"))
TANPA_SUARA = os.environ.get("VEST_TANPA_SUARA", "0").lower() in ("1", "true", "yes", "on")

RIWAYAT_PATH.parent.mkdir(parents=True, exist_ok=True)

# ---------- muat engine inferensi ----------
ENGINE: Optional[InferensiVest] = None
ENGINE_ERROR: Optional[str] = None
try:
    ENGINE = InferensiVest(
        model_path=MODEL_PATH,
        suara_folder=None if TANPA_SUARA else SUARA_FOLDER,
        conf=CONF,
        imgsz=IMGSZ,
        paksa_tts_fallback=TANPA_SUARA,
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # longgarkan buat development; batasi ke domain saat deploy
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- autentikasi ----------
def _cek_api_key(x_api_key: Optional[str]):
    if API_KEY is None:
        return  # autentikasi dimatikan (VEST_API_KEY tidak diset)
    if x_api_key != API_KEY:
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


# ---------- endpoint ----------
@app.get("/")
def root():
    return {
        "nama": "VestCare API",
        "versi": "2.0.0",
        "engine_siap": ENGINE is not None,
        "engine_error": ENGINE_ERROR,
        "model_path": str(MODEL_PATH),
        "model_exists": MODEL_PATH.exists(),
        "imgsz": IMGSZ,
        "conf": CONF,
        "suara": "matikan" if TANPA_SUARA else ("aktif" if ENGINE and ENGINE.pemutar or ENGINE and ENGINE.tts_fallback else "tidak tersedia"),
        "suara_folder": str(SUARA_FOLDER),
        "suara_folder_exists": SUARA_FOLDER.exists(),
        "autentikasi": "aktif" if API_KEY else "NONAKTIF (set VEST_API_KEY untuk mengaktifkan)",
        "dokumentasi": "/docs",
        "status": "/status",
    }


@app.get("/status")
def status():
    """Status ringkas tanpa autentikasi (untuk pemantauan tunnel/uptime)."""
    return {
        "server": "VestCare API",
        "versi": "2.0.0",
        "engine_siap": ENGINE is not None,
        "engine_error": ENGINE_ERROR,
        "suara_aktif": bool(ENGINE and (ENGINE.pemutar or ENGINE.tts_fallback)),
        "tanpa_suara": TANPA_SUARA,
        "waktu_server": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


@app.post("/deteksi")
async def deteksi(
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, description="jarak ultrasonik depan dalam METER"),
    x_api_key: Optional[str] = Header(None),
):
    _cek_api_key(x_api_key)
    try:
        isi = await gambar.read()
        img = Image.open(io.BytesIO(isi)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="File gambar tidak valid / tidak bisa dibaca.")

    hasil = _jalankan_deteksi(img, jarak_m, putar_suara=False)
    entri = _simpan_riwayat(ENGINE.ke_dict(hasil), sumber="deteksi")
    return JSONResponse(entri)


@app.post("/deteksi/suara")
async def deteksi_suara(
    gambar: UploadFile = File(..., description="file gambar (jpg/png) dari rompi/klien"),
    jarak_m: Optional[float] = Form(None, description="jarak ultrasonik depan dalam METER"),
    x_api_key: Optional[str] = Header(None),
):
    """Deteksi + putar suara peringatan di server (speaker rompi)."""
    _cek_api_key(x_api_key)
    try:
        isi = await gambar.read()
        img = Image.open(io.BytesIO(isi)).convert("RGB")
    except Exception:
        raise HTTPException(status_code=400, detail="File gambar tidak valid / tidak bisa dibaca.")

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
    uvicorn.run("server_rest_api:app", host="0.0.0.0", port=8000, reload=False)
