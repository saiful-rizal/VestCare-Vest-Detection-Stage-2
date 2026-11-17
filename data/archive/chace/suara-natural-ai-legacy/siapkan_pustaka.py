


from __future__ import annotations







import argparse



import asyncio



import json



import random



import time



from pathlib import Path



from typing import Optional







from definisi_suara import (PENGATURAN_TINGKAT, SKEMA, Skenario, bangun_skenario, bersihkan_akhir,



tekanan_sambung, valid, KUNCI_AMAN)



from llm import PENYEDIA_VALID, deskripsi_llm, minta_teks



from teks_bawaan import hanya_bawaan, teks_bawaan







FOLDER_DEFAULT = "cache_suara"











def _pasang_preset_emosi():



from suara_natural import PRESET_EMOSI, Preset



PRESET_EMOSI.setdefault("waspada", Preset(rate=4, pitch=-2, volume=8))



PRESET_EMOSI.setdefault("darurat", Preset(rate=6, pitch=-3, volume=10))











PROMPT = """Anda perancang pesan suara untuk rompi bantu mobilitas penyandang tunanetra (bahasa Indonesia).
Pesan lengkap dirakit dari klip pendek, dan Anda menulis satu jenis klip saja.

Masukan: objek JSON kunci -> {"deskripsi", "maks_kata", "jumlah"}.
Untuk tiap kunci tulis "jumlah" variasi kalimat lisan yang berbeda susunannya tetapi sama maknanya.

Aturan umum:
- Jumlah kata tiap kalimat tidak boleh melebihi "maks_kata".
- JANGAN menulis angka atau jarak. JANGAN menambah informasi yang tidak ada di deskripsi.
- Tanpa emoji, markdown, atau tanda kutip. Bahasa lisan yang natural dan jelas.
- Klip "benda": hanya menyebut bendanya dan arahnya (depan, kiri, atau kanan). JANGAN memberi perintah.
  JANGAN menyebut keadaan benda: jangan menulis bergerak, melaju, melintas, mendekat, parkir, berdiri,
  atau diam. Untuk arah depan tulis "di depan"; untuk kiri dan kanan boleh "di kiri" atau "di sebelah kiri".
- Klip "solusi": perintah singkat sesuai deskripsi. Sebut kiri atau kanan HANYA bila deskripsi menyebutnya.

Keluaran: SATU objek JSON murni tanpa teks lain dan tanpa pagar kode. Kunci sama persis dengan masukan,
nilainya array string."""



























































def _ekstrak_objek(teks: str) -> dict:



awal, akhir = teks.find("{"), teks.rfind("}")



if awal == -1 or akhir == -1:



raise ValueError("Keluaran LLM tidak memuat objek JSON.")



return json.loads(teks[awal:akhir + 1])











def _satu_kelompok(skenario: dict[str, Skenario], percobaan: int, penyedia: Optional[str]) -> dict[str, list[str]]:



hasil: dict[str, list[str]] = {}



galat_terakhir: Exception | None = None



for ke in range(1, percobaan + 1):



sisa = {k: s for k, s in skenario.items() if k not in hasil}



if not sisa:



break



muatan = {k: {"deskripsi": f"[{s.jenis}] " + s.deskripsi,



"maks_kata": s.maks_kata, "jumlah": s.jumlah} for k, s in sisa.items()}



try:



mentah = minta_teks(PROMPT, json.dumps(muatan, ensure_ascii=False), penyedia, maks_token=2000)



data = _ekstrak_objek(mentah)



for kunci, s in sisa.items():



daftar, terlihat = [], set()



for t in data.get(kunci, []):



t = str(t).strip()



if t and t.lower() not in terlihat and valid(t, s):



terlihat.add(t.lower())



daftar.append(t)



if daftar:



hasil[kunci] = daftar[:s.jumlah]



kurang = [k for k in skenario if k not in hasil]



if kurang:



print(f"  {len(kurang)} skenario belum punya kalimat valid (percobaan {ke}/{percobaan}); meminta ulang.")



except (ValueError, json.JSONDecodeError) as galat:



galat_terakhir = galat



print(f"  Keluaran LLM belum valid (percobaan {ke}/{percobaan}): {galat}")



except Exception as galat:



galat_terakhir = galat



ringkas = str(galat).replace("\n", " ")[:140]



jeda = min(60, 5 * 2 ** (ke - 1))



print(f"  Panggilan LLM gagal (percobaan {ke}/{percobaan}): {ringkas}")



if ke < percobaan:



print(f"  Menunggu {jeda} detik sebelum mencoba lagi...")



time.sleep(jeda)



kurang = [k for k in skenario if k not in hasil]



if kurang:



raise SystemExit(f"LLM gagal menyusun kalimat valid untuk: {', '.join(kurang[:6])}"



f"{' ...' if len(kurang) > 6 else ''} (galat terakhir: {galat_terakhir})")



return hasil











def susun_varian_llm(skenario: dict[str, Skenario], percobaan: int = 6,



penyedia: Optional[str] = None) -> dict[str, list[str]]:







kelompok: dict[str, dict[str, Skenario]] = {}



for k, s in skenario.items():



nama = f"benda {s.kelas}" if s.jenis == "benda" else s.jenis



kelompok.setdefault(nama, {})[k] = s



hasil: dict[str, list[str]] = {}



for no, (nama, isi) in enumerate(kelompok.items(), 1):



print(f"  [{no}/{len(kelompok)}] {nama}: {len(isi)} skenario")



hasil.update(_satu_kelompok(isi, percobaan, penyedia))



if no < len(kelompok):



time.sleep(2.0)



return hasil











def _teks_dari_pustaka(folder: Path, skenario: dict[str, Skenario]) -> dict[str, list[str]]:



jalur = Path(folder) / "manifest.json"



if not jalur.exists():



raise SystemExit(f"--teks-dari: '{folder}' tidak berisi manifest.json.")



sumber = json.loads(jalur.read_text(encoding="utf-8"))



if sumber.get("skema") != SKEMA:



raise SystemExit(f"--teks-dari: pustaka '{folder}' bukan skema {SKEMA}.")



hasil: dict[str, list[str]] = {}



for kunci, s in skenario.items():



daftar = [e["teks"] for e in sumber.get("pesan", {}).get(kunci, []) if valid(e["teks"], s)]



if daftar:



hasil[kunci] = daftar



return hasil











def pangkas(audio, sisa_ms: int = 15):







from pydub.silence import detect_leading_silence



awal = max(0, detect_leading_silence(audio, silence_threshold=-45.0) - sisa_ms)



akhir = max(0, detect_leading_silence(audio.reverse(), silence_threshold=-45.0) - sisa_ms)



return audio[awal:len(audio) - akhir] if len(audio) - awal - akhir > 60 else audio











def _meta() -> dict[str, dict]:



meta = {t: {"prioritas": p.prioritas, "cooldown": p.cooldown, "mendesak": p.mendesak}



for t, p in PENGATURAN_TINGKAT.items()}



meta[KUNCI_AMAN] = {"prioritas": 1, "cooldown": 12.0, "mendesak": False}



return meta











def _simpan(jalur: Path, manifest: dict) -> None:



jalur.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")











def _manifest_baru(suara: str, format_audio: str) -> dict:



from definisi_suara import daftar_kelas



return {"skema": SKEMA, "suara": suara, "format": format_audio, "kelas": daftar_kelas(),



"meta": {}, "pesan": {}}











async def siapkan_pustaka(folder: Path, suara: str, jumlah: int, paksa: bool, seed: Optional[int],



format_audio: str, laju_sampel: int, penyedia: Optional[str] = None,



teks_dari: Optional[Path] = None, tanpa_llm: bool = False) -> None:



from pydub import AudioSegment



from pydub.effects import normalize



from suara_natural import _parameter_prosodi, sintesis_segmen



_pasang_preset_emosi()







skenario = bangun_skenario(jumlah)



folder.mkdir(parents=True, exist_ok=True)



jalur_manifest = folder / "manifest.json"



manifest = _manifest_baru(suara, format_audio)



if jalur_manifest.exists() and not paksa:



lama = json.loads(jalur_manifest.read_text(encoding="utf-8"))



if lama.get("skema") != SKEMA:



print(f"Pustaka lama memakai skema {lama.get('skema')}; dibuat ulang dari awal (skema {SKEMA}).")



for entri in lama.get("pesan", {}).values():



for e in entri:



(folder / e["berkas"]).unlink(missing_ok=True)



else:



manifest = lama



if manifest.get("suara") != suara or manifest.get("format") != format_audio:



print(f"Catatan: pustaka lama memakai suara {manifest.get('suara')} format "



f"{manifest.get('format')}; dipertahankan. Gunakan --paksa untuk mengganti.")



suara, format_audio = manifest["suara"], manifest.get("format", format_audio)



from definisi_suara import daftar_kelas



manifest["kelas"] = daftar_kelas()



manifest["meta"] = _meta()



_simpan(jalur_manifest, manifest)







belum = {k: s for k, s in skenario.items() if k not in manifest["pesan"]}



if not belum:



print("Pustaka sudah lengkap (metadata diperbarui). Gunakan --paksa untuk membuat ulang.")



return







varian: dict[str, list[str]] = {k: teks_bawaan(s) for k, s in belum.items() if hanya_bawaan(s)}



perlu = {k: s for k, s in belum.items() if k not in varian}



if teks_dari is not None and perlu:



dipakai = _teks_dari_pustaka(teks_dari, perlu)



print(f"Memakai ulang kalimat dari '{teks_dari}' untuk {len(dipakai)} skenario (tanpa LLM).")



varian.update(dipakai)



perlu = {k: s for k, s in perlu.items() if k not in varian}



if perlu and tanpa_llm:



print(f"Memakai kalimat bawaan (tanpa LLM) untuk {len(perlu)} skenario.")



varian.update({k: teks_bawaan(s) for k, s in perlu.items()})



elif perlu:



print(f"Menyusun kalimat dengan LLM ({deskripsi_llm(penyedia)}) untuk {len(perlu)} skenario...")



varian.update(susun_varian_llm(perlu, penyedia=penyedia))







rng = random.Random(seed)



total = sum(len(v) for v in varian.values())



ke = 0



for kunci, daftar in varian.items():



s = skenario[kunci]



entri = []



for i, teks in enumerate(daftar, 1):



ke += 1



print(f"  [{ke}/{total}] {kunci} {i}: {teks}")



tampil = bersihkan_akhir(teks) if tekanan_sambung(s) else teks



ucap = tampil + "," if tekanan_sambung(s) else teks



audio = await sintesis_segmen(ucap, suara, _parameter_prosodi(s.emosi, rng))



audio = normalize(pangkas(audio).fade_in(8).fade_out(25), headroom=1.0)



nama = f"{kunci}_{i}.{format_audio}"



if format_audio == "wav":



audio.set_channels(1).set_frame_rate(laju_sampel).export(folder / nama, format="wav")



else:



audio.export(folder / nama, format="mp3", bitrate="128k")



entri.append({"teks": tampil, "berkas": nama})



manifest["pesan"][kunci] = entri



_simpan(jalur_manifest, manifest)



print(f"Selesai. Pustaka suara tersimpan di folder '{folder}'.")



periksa(folder)











def periksa(folder: Path, jumlah: int = 3) -> bool:



jalur = Path(folder) / "manifest.json"



if not jalur.exists():



print(f"Pustaka belum ada di '{folder}'.")



return False



manifest = json.loads(jalur.read_text(encoding="utf-8"))



perlu = set(bangun_skenario(jumlah))



ada = {k for k, v in manifest.get("pesan", {}).items() if v}



hilang, lebih = sorted(perlu - ada), sorted(ada - perlu)



berkas = [e["berkas"] for v in manifest.get("pesan", {}).values() for e in v



if not (Path(folder) / e["berkas"]).exists()]



if manifest.get("skema") != SKEMA:



print(f"Skema pustaka {manifest.get('skema')} tidak sama dengan {SKEMA}.")



if hilang:



print(f"Klip yang belum ada ({len(hilang)}): {', '.join(hilang[:8])}{' ...' if len(hilang) > 8 else ''}")



if lebih:



print(f"Klip di pustaka yang tidak dipakai ({len(lebih)}): {', '.join(lebih[:8])}")



if berkas:



print(f"Berkas audio hilang: {', '.join(berkas[:5])}")



ok = not hilang and not berkas and manifest.get("skema") == SKEMA



print("Pustaka SESUAI dengan fuzzysugeno.py." if ok else



"Pustaka BELUM sesuai; jalankan python siapkan_pustaka.py.")



return ok











def main() -> None:



ap = argparse.ArgumentParser(description="Membuat pustaka suara skema 3 (klip rakitan), selaras dengan fuzzysugeno.py.")



ap.add_argument("--folder", default=FOLDER_DEFAULT)



ap.add_argument("--suara", default="id-ID-GadisNeural", help="id-ID-GadisNeural atau id-ID-ArdiNeural.")



ap.add_argument("--llm", choices=PENYEDIA_VALID, default=None, help="Penyedia LLM (bawaan: gemini).")



ap.add_argument("--varian", type=int, default=3, help="Variasi per klip (bawaan 3).")



ap.add_argument("--format", choices=["mp3", "wav"], default="mp3", dest="format_audio")



ap.add_argument("--laju-sampel", type=int, default=22050, help="Hz untuk format wav.")



ap.add_argument("--paksa", action="store_true", help="Buat ulang seluruh pustaka.")



ap.add_argument("--teks-dari", default=None, metavar="FOLDER", help="Pakai ulang kalimat pustaka lain tanpa LLM.")



ap.add_argument("--tanpa-llm", action="store_true", help="Pakai kalimat bawaan (teks_bawaan.py), tanpa LLM.")



ap.add_argument("--periksa", action="store_true", help="Cek kecocokan pustaka lalu keluar.")



ap.add_argument("--seed", type=int, default=None)



a = ap.parse_args()



if a.periksa:



raise SystemExit(0 if periksa(Path(a.folder), a.varian) else 1)



asyncio.run(siapkan_pustaka(Path(a.folder), a.suara, a.varian, a.paksa, a.seed, a.format_audio,



a.laju_sampel, a.llm, Path(a.teks_dari) if a.teks_dari else None, a.tanpa_llm))











if __name__ == "__main__":



main()