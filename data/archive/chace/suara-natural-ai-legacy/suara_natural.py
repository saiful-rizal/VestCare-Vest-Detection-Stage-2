



from __future__ import annotations







import argparse



import asyncio



import io



import json



import os



import random



import re



import sys



import time



from dataclasses import dataclass



from pathlib import Path







import edge_tts



from pydub import AudioSegment



from pydub.effects import normalize







from llm import PENYEDIA_VALID, deskripsi_llm, minta_teks











SUARA_DEFAULT = "id-ID-GadisNeural"











@dataclass(frozen=True)



class Preset:







rate: int



pitch: int



volume: int











PRESET_EMOSI: dict[str, Preset] = {



"netral":   Preset(rate=0,   pitch=0,  volume=0),



"ramah":    Preset(rate=3,   pitch=2,  volume=0),



"antusias": Preset(rate=8,   pitch=6,  volume=5),



"tenang":   Preset(rate=-8,  pitch=-2, volume=-3),



"serius":   Preset(rate=-4,  pitch=-4, volume=0),



"empati":   Preset(rate=-10, pitch=-2, volume=-5),



}







PROMPT_NARASI = """Anda adalah penulis naskah suara (voice script) berbahasa Indonesia.
Tugas Anda: mengubah teks pengguna menjadi naskah lisan yang terdengar seperti
manusia sungguhan sedang berbicara, bukan membaca teks.

Aturan penulisan:
- Pertahankan seluruh makna dan fakta; jangan menambah informasi baru.
- Gunakan kalimat pendek hingga sedang. Pecah kalimat panjang menjadi beberapa bagian.
- Gunakan kata sambung dan penanda lisan secara wajar dan hemat
  (misalnya "nah", "jadi", "oke", "begini"), tidak berlebihan.
- Eja angka, singkatan, simbol, dan tanda baca teknis menjadi bentuk yang diucapkan
  (contoh: "17%" menjadi "tujuh belas persen", "IoT" menjadi "ai-o-ti").
- Hapus format markdown, tautan, dan emoji.
- Gunakan koma, titik, dan tanda tanya agar jeda dan intonasi terbentuk alami.

Keluaran HARUS berupa JSON array murni tanpa teks lain dan tanpa pagar kode.
Setiap elemen berbentuk:
{"teks": "kalimat yang diucapkan", "emosi": "netral|ramah|antusias|tenang|serius|empati", "jeda_ms": 150-900}
Gunakan jeda pendek (150-300) di antara kalimat yang bersambung, dan jeda lebih
panjang (500-900) pada pergantian gagasan atau akhir paragraf."""





























































PROMPT_JAWAB = PROMPT_NARASI.replace(



"Tugas Anda: mengubah teks pengguna menjadi naskah lisan yang terdengar seperti\n"



"manusia sungguhan sedang berbicara, bukan membaca teks.",



"Tugas Anda: menjawab pertanyaan atau permintaan pengguna secara ringkas, akurat,\n"



"dan dalam gaya lisan yang terdengar seperti manusia sungguhan sedang berbicara.\n"



"Panjang jawaban maksimal sekitar 150 kata.",



).replace("- Pertahankan seluruh makna dan fakta; jangan menambah informasi baru.\n", "")











def _ekstrak_json(teks: str) -> list[dict]:







bersih = re.sub(r"```(?:json)?", "", teks).strip()



awal, akhir = bersih.find("["), bersih.rfind("]")



if awal == -1 or akhir == -1:



raise ValueError("Keluaran LLM tidak memuat JSON array.")



return json.loads(bersih[awal:akhir + 1])











def _validasi_segmen(data: list[dict]) -> list[dict]:



hasil: list[dict] = []



for item in data:



teks = str(item.get("teks", "")).strip()



if not teks:



continue



emosi = str(item.get("emosi", "netral")).lower()



if emosi not in PRESET_EMOSI:



emosi = "netral"



try:



jeda = int(item.get("jeda_ms", 300))



except (TypeError, ValueError):



jeda = 300



hasil.append({"teks": teks, "emosi": emosi, "jeda_ms": max(150, min(900, jeda))})



if not hasil:



raise ValueError("Tidak ada segmen valid dari LLM.")



return hasil











def susun_dengan_llm(teks: str, mode: str, percobaan: int = 3,



penyedia: str | None = None) -> list[dict]:







sistem = PROMPT_JAWAB if mode == "jawab" else PROMPT_NARASI



galat_terakhir: Exception | None = None



for ke in range(1, percobaan + 1):



try:



mentah = minta_teks(sistem, teks, penyedia)



return _validasi_segmen(_ekstrak_json(mentah))



except (ValueError, json.JSONDecodeError) as galat:







galat_terakhir = galat



print(f"  Keluaran LLM belum valid (percobaan {ke}/{percobaan}): {galat}")



except Exception as galat:







galat_terakhir = galat



print(f"  Panggilan LLM gagal (percobaan {ke}/{percobaan}): {galat}")



time.sleep(1.5 * ke)



raise SystemExit(f"LLM gagal menyusun naskah setelah {percobaan} percobaan: {galat_terakhir}")











def _parameter_prosodi(emosi: str, rng: random.Random) -> dict[str, str]:







p = PRESET_EMOSI[emosi]



rate = p.rate + rng.randint(-2, 2)



pitch = p.pitch + rng.randint(-1, 1)



volume = p.volume



return {



"rate": f"{rate:+d}%",



"pitch": f"{pitch:+d}Hz",



"volume": f"{volume:+d}%",



}











async def sintesis_segmen(teks: str, suara: str, prosodi: dict[str, str],



percobaan: int = 3) -> AudioSegment:







galat_terakhir: Exception | None = None



for ke in range(1, percobaan + 1):



try:



komunikator = edge_tts.Communicate(teks, suara, **prosodi)



buffer = bytearray()



async for potongan in komunikator.stream():



if potongan["type"] == "audio":



buffer.extend(potongan["data"])



if not buffer:



raise RuntimeError("Audio kosong dari layanan TTS.")



return AudioSegment.from_file(io.BytesIO(bytes(buffer)), format="mp3")



except Exception as galat:



galat_terakhir = galat



await asyncio.sleep(1.5 * ke)



raise RuntimeError(f"Sintesis gagal setelah {percobaan} percobaan: {galat_terakhir}")











async def rakit_audio(segmen: list[dict], suara: str, seed: int | None) -> AudioSegment:



rng = random.Random(seed)



hasil = AudioSegment.silent(duration=250)



for i, s in enumerate(segmen, 1):



prosodi = _parameter_prosodi(s["emosi"], rng)



print(f"  [{i}/{len(segmen)}] ({s['emosi']}) {s['teks'][:70]}")



audio = await sintesis_segmen(s["teks"], suara, prosodi)



audio = audio.fade_in(15).fade_out(40)



jeda = s["jeda_ms"] + rng.randint(-40, 60)



hasil += audio + AudioSegment.silent(duration=max(100, jeda))



return normalize(hasil, headroom=1.0)











async def daftar_suara_indonesia() -> None:



semua = await edge_tts.list_voices()



for v in semua:



if v["Locale"].startswith("id-"):



print(f"{v['ShortName']:<22} {v['Gender']}")











def baca_masukan(args: argparse.Namespace) -> str:



if args.berkas:



return Path(args.berkas).read_text(encoding="utf-8").strip()



if args.teks:



return args.teks.strip()



if not sys.stdin.isatty():



return sys.stdin.read().strip()



raise SystemExit("Berikan teks melalui --teks, --berkas, atau stdin.")











def main() -> None:



ap = argparse.ArgumentParser(description="Pembuat suara AI Indonesia yang natural.")



ap.add_argument("--teks", help="Teks yang akan diucapkan.")



ap.add_argument("--berkas", help="Jalur berkas .txt berisi naskah.")



ap.add_argument("--llm", choices=PENYEDIA_VALID, default=None,



help="Penyedia LLM (bawaan: gemini, gratis). Lihat llm.py.")



ap.add_argument("--mode", choices=["narasi", "jawab"], default="narasi",



help="narasi: LLM menulis ulang teks lalu diucapkan; jawab: LLM menjawab teks lalu diucapkan.")



ap.add_argument("--suara", default=SUARA_DEFAULT, help="Nama suara Edge TTS.")



ap.add_argument("-o", "--keluaran", default="keluaran.mp3", help="Berkas MP3 keluaran.")



ap.add_argument("--seed", type=int, default=None,



help="Seed variasi acak agar hasil dapat diulang.")



ap.add_argument("--daftar-suara", action="store_true",



help="Tampilkan daftar suara bahasa Indonesia lalu keluar.")



args = ap.parse_args()







if args.daftar_suara:



asyncio.run(daftar_suara_indonesia())



return







masukan = baca_masukan(args)



if not masukan:



raise SystemExit("Teks masukan kosong.")











print(f"Menyusun naskah lisan dengan LLM ({deskripsi_llm(args.llm)})...")



segmen = susun_dengan_llm(masukan, args.mode, penyedia=args.llm)











print(f"Mensintesis {len(segmen)} segmen dengan suara {args.suara}...")



audio = asyncio.run(rakit_audio(segmen, args.suara, args.seed))







keluaran = Path(args.keluaran)



keluaran.parent.mkdir(parents=True, exist_ok=True)



audio.export(keluaran, format="mp3", bitrate="192k")



print(f"Selesai: {keluaran} ({len(audio) / 1000:.1f} detik)")











if __name__ == "__main__":



main()
