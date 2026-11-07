



from __future__ import annotations







import json



import os



import re



import time



import urllib.error



import urllib.request



from typing import Optional







PENYEDIA_VALID = ("gemini", "ollama", "anthropic")



PENYEDIA_DEFAULT = "gemini"







MODEL_OLLAMA = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")



MODEL_ANTHROPIC = os.getenv("SUARA_LLM_MODEL", "claude-sonnet-5-5")











ALIAS_GEMINI = ("gemini-flash-latest", "gemini-flash-lite-latest")







BUKAN_TEKS = ("image", "tts", "audio", "live", "embedding", "native",



"transcribe", "omni", "robotics", "computer")







_model_gemini_aktif: Optional[str] = None











class GalatLLM(RuntimeError):











def __init__(self, pesan: str, kode: Optional[int] = None) -> None:



super().__init__(pesan)



self.kode = kode











def tentukan_penyedia(penyedia: Optional[str] = None) -> str:



nama = (penyedia or os.getenv("SUARA_LLM") or PENYEDIA_DEFAULT).strip().lower()



if nama not in PENYEDIA_VALID:



raise SystemExit(f"Penyedia LLM '{nama}' tidak dikenal. Pilihan: {', '.join(PENYEDIA_VALID)}")



return nama











def deskripsi_llm(penyedia: Optional[str] = None) -> str:



nama = tentukan_penyedia(penyedia)



if nama == "gemini":



model = os.getenv("GEMINI_MODEL") or f"{ALIAS_GEMINI[0]} (otomatis, dengan cadangan)"



elif nama == "ollama":



model = MODEL_OLLAMA



else:



model = MODEL_ANTHROPIC



return f"{nama} / {model}"











def _http_json(url: str, muatan: Optional[dict], header: dict, timeout: float) -> dict:







data = json.dumps(muatan).encode("utf-8") if muatan is not None else None



permintaan = urllib.request.Request(



url, data=data, method="POST" if muatan is not None else "GET",



headers={"Content-Type": "application/json", **header},



)



for ke in range(1, 4):



try:



with urllib.request.urlopen(permintaan, timeout=timeout) as respons:



return json.loads(respons.read().decode("utf-8"))



except urllib.error.HTTPError as galat:



isi = galat.read().decode("utf-8", "replace")[:300]



if galat.code in (429, 500, 503) and ke < 3:



time.sleep(6 * ke)



continue



if galat.code == 429:



raise GalatLLM("Batas laju/kuota tingkat gratis tercapai (HTTP 429). "



"Tunggu beberapa menit lalu jalankan lagi. " + isi, kode=429)



raise GalatLLM(f"HTTP {galat.code}: {isi}", kode=galat.code)



except urllib.error.URLError as galat:



raise GalatLLM(f"Tidak dapat terhubung ke {url.split('/')[2]}: {galat.reason}",



kode=599)



except (TimeoutError, OSError) as galat:



raise GalatLLM(f"Waktu tunggu habis atau koneksi terputus: {galat}", kode=599)



raise GalatLLM("Permintaan gagal setelah beberapa percobaan.")











def _versi_model(nama: str) -> float:



cocok = re.search(r"gemini-(\d+(?:\.\d+)?)", nama)



return float(cocok.group(1)) if cocok else 0.0











def _daftar_model_flash(dasar: str, kunci: str) -> list[str]:







try:



data = _http_json(f"{dasar}/models?pageSize=200", None, {"x-goog-api-key": kunci}, 30)



except GalatLLM:



return []



hasil = []



for m in data.get("models", []):



nama = str(m.get("name", "")).replace("models/", "", 1)



if "flash" not in nama or any(k in nama for k in BUKAN_TEKS):



continue



if "generateContent" not in m.get("supportedGenerationMethods", []):



continue



hasil.append(nama)







hasil.sort(key=lambda n: (("preview" in n) or ("exp" in n), "lite" in n, -_versi_model(n)))



return hasil











def _teks_gemini(data: dict) -> str:



try:



bagian = data["candidates"][0]["content"]["parts"]



except (KeyError, IndexError, TypeError):



alasan = (data.get("promptFeedback") or {}).get("blockReason", "tidak diketahui")



raise GalatLLM(f"Respons Gemini kosong atau diblokir (alasan: {alasan}).")



return "".join(b.get("text", "") for b in bagian if not b.get("thought"))











def _gemini(sistem: str, pengguna: str, maks_token: int) -> str:



global _model_gemini_aktif



kunci = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")



if not kunci:



raise SystemExit(



"GEMINI_API_KEY belum diatur. Buat kunci gratis di aistudio.google.com/app/apikey, "



"atau gunakan LLM lokal dengan: --llm ollama"



)



dasar = os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta")



muatan = {



"systemInstruction": {"parts": [{"text": sistem}]},



"contents": [{"role": "user", "parts": [{"text": pengguna}]}],



"generationConfig": {



"temperature": 0.8,











"maxOutputTokens": max(maks_token, 8192),



"responseMimeType": "application/json",



},



}







antrean = [m for m in (_model_gemini_aktif, os.getenv("GEMINI_MODEL"), *ALIAS_GEMINI) if m]



dicoba: list[str] = []



sudah_mendaftar = False



galat_terakhir: Optional[GalatLLM] = None







while antrean and len(dicoba) < 8:



model = antrean.pop(0)



if model in dicoba:



continue



dicoba.append(model)



try:



data = _http_json(f"{dasar}/models/{model}:generateContent", muatan,



{"x-goog-api-key": kunci}, timeout=120)



except GalatLLM as galat:



galat_terakhir = galat











if galat.kode in (404, 403, 429, 500, 503, 599):



alasan = {503: "sedang penuh", 500: "galat server", 599: "timeout"}.get(



galat.kode, f"HTTP {galat.kode}")



print(f"  Model Gemini '{model}' tidak dapat dipakai ({alasan}); mencoba model lain...")



if not antrean and not sudah_mendaftar:



sudah_mendaftar = True



antrean = _daftar_model_flash(dasar, kunci)[:4]



continue



raise



if _model_gemini_aktif != model:



print(f"  Model Gemini yang dipakai: {model}")



_model_gemini_aktif = model



return _teks_gemini(data)







raise GalatLLM(



"Tidak ada model Gemini yang dapat dipakai (dicoba: " + ", ".join(dicoba) + "). "



"Periksa model yang tersedia di ai.google.dev lalu atur GEMINI_MODEL, "



"atau gunakan --llm ollama. Galat terakhir: " + (str(galat_terakhir) if galat_terakhir else "-")



)











def _ollama(sistem: str, pengguna: str, maks_token: int) -> str:



host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")



if not host.startswith("http"):



host = "http://" + host



muatan = {



"model": MODEL_OLLAMA,



"messages": [{"role": "system", "content": sistem},



{"role": "user", "content": pengguna}],



"stream": False,



"options": {"temperature": 0.8, "num_predict": maks_token},



}



try:



data = _http_json(f"{host}/api/chat", muatan, {}, timeout=600)



except GalatLLM as galat:



raise GalatLLM(f"{galat} | Pastikan Ollama berjalan dan model sudah diunduh: "



f"ollama pull {MODEL_OLLAMA}", kode=galat.kode)



try:



return data["message"]["content"]



except (KeyError, TypeError):



raise GalatLLM(f"Respons Ollama tidak sesuai: {str(data)[:200]}")











def _anthropic(sistem: str, pengguna: str, maks_token: int) -> str:



try:



import anthropic



except ImportError:



raise SystemExit("Paket 'anthropic' belum terpasang. Jalankan: pip install anthropic")



if not os.getenv("ANTHROPIC_API_KEY"):



raise SystemExit("ANTHROPIC_API_KEY belum diatur (opsi berbayar). "



"Untuk opsi gratis gunakan --llm gemini atau --llm ollama.")



klien = anthropic.Anthropic()



respons = klien.messages.create(



model=MODEL_ANTHROPIC, max_tokens=maks_token, system=sistem,



messages=[{"role": "user", "content": pengguna}],



)



return "".join(b.text for b in respons.content if getattr(b, "type", "") == "text")











def minta_teks(sistem: str, pengguna: str, penyedia: Optional[str] = None,



maks_token: int = 2000) -> str:







nama = tentukan_penyedia(penyedia)



if nama == "gemini":



return _gemini(sistem, pengguna, maks_token)



if nama == "ollama":



return _ollama(sistem, pengguna, maks_token)



return _anthropic(sistem, pengguna, maks_token)
