from __future__ import annotations

import json
import os
import random
import shutil
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

import yaml

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
EXPECTED_CLASSES = {0: "pohon", 1: "mobil", 2: "motor", 3: "orang", 4: "lubang"}
SUPPORT_CLASS_ID = len(EXPECTED_CLASSES)
SUPPORT_CLASS_NAME = "__non_target_internal__"
TRAINING_CLASSES = {**EXPECTED_CLASSES, SUPPORT_CLASS_ID: SUPPORT_CLASS_NAME}
SPLITS = ("train", "val", "test")
RASIO = {"train": 0.70, "val": 0.15, "test": 0.15}
SEED_KANDIDAT = tuple(range(200))
SEED_DEFAULT = 42


@dataclass
class Rekaman:
    nama: str
    gambar: Path
    kelompok: str
    baris: list[tuple[int, list[float]]]
    asal: str
    kelas: Counter[int] = field(default_factory=lambda: Counter[int]())


@dataclass
class Kelompok:
    kunci: str
    rekaman: list[Rekaman] = field(default_factory=lambda: list[Rekaman]())
    kelas_gambar: Counter[int] = field(default_factory=lambda: Counter[int]())
    kelas_instans: Counter[int] = field(default_factory=lambda: Counter[int]())

    @property
    def ukuran(self) -> int:
        return len(self.rekaman)


class PerhatianData:

    def __init__(self) -> None:
        self.pesan: list[str] = []
        self.hitung: Counter[str] = Counter()

    def catat(self, jenis: str, detail: str = "") -> None:
        self.hitung[jenis] += 1
        if detail and len([p for p in self.pesan if p.startswith(jenis)]) < 5:
            self.pesan.append(f"{jenis}: {detail}")

    def cetak(self) -> None:
        for jenis, jumlah in self.hitung.items():
            print(f"[DATA] {jenis}: {jumlah}")
        for pesan in self.pesan:
            print(f"[DATA]   contoh -> {pesan}")


def baca_names(data: dict[str, Any], sumber: Path) -> dict[int, str]:
    names = data.get("names")
    if isinstance(names, list):
        names_list = cast(list[Any], names)
        return {index: str(name) for index, name in enumerate(names_list)}
    if isinstance(names, dict):
        names_mapping = cast(dict[Any, Any], names)
        return {int(key): str(value) for key, value in names_mapping.items()}
    raise ValueError(f"Daftar kelas tidak valid di {sumber}")


def _sumber_ke_list(nilai: Any) -> list[Any]:
    if nilai is None:
        return []
    if isinstance(nilai, list):
        sumber: list[Any] = cast(list[Any], nilai)
        return sumber
    return [nilai]


def daftar_gambar(data_yaml: Path) -> list[Path]:
    data: dict[str, Any] = yaml.safe_load(data_yaml.read_text(encoding="utf-8-sig")) or {}
    akar = Path(data.get("path", "."))
    if not akar.is_absolute():
        akar = data_yaml.parent / akar
    ditemukan: dict[Path, None] = {}
    for kunci in SPLITS:
        for sumber in _sumber_ke_list(data.get(kunci)):
            jalur = Path(str(sumber))
            if not jalur.is_absolute():
                jalur = akar / jalur
            jalur = jalur.resolve()
            if jalur.is_file() and jalur.suffix.lower() == ".txt":
                for baris in jalur.read_text(encoding="utf-8").splitlines():
                    baris = baris.strip()
                    if not baris:
                        continue
                    p = Path(baris)
                    p = (p if p.is_absolute() else jalur.parent / p).resolve()
                    if p.is_file():
                        ditemukan[p] = None
            elif jalur.is_file() and jalur.suffix.lower() in IMAGE_EXTENSIONS:
                ditemukan[jalur] = None
            elif jalur.is_dir():
                for p in sorted(jalur.rglob("*")):
                    if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS:
                        ditemukan[p.resolve()] = None
    return sorted(ditemukan)


def jalur_label(gambar: Path) -> Path:
    bagian = list(gambar.parts)
    for indeks in range(len(bagian) - 2, -1, -1):
        if bagian[indeks] == "images":
            bagian[indeks] = "labels"
            return Path(*bagian).with_suffix(".txt")
    return gambar.parent.parent / "labels" / f"{gambar.stem}.txt"


def baca_label(
    label: Path,
    peta_kelas: dict[int, int] | None,
    perhatian: PerhatianData,
) -> tuple[list[tuple[int, list[float]]], bool]:
    hasil: list[tuple[int, list[float]]] = []
    if not label.is_file():
        return hasil, False
    for baris in label.read_text(encoding="utf-8-sig").splitlines():
        kolom = baris.split()
        if not kolom:
            continue
        try:
            id_kelas = int(float(kolom[0]))
            angka = [float(x) for x in kolom[1:]]
        except ValueError:
            perhatian.catat("baris label rusak dibuang", f"{label.name}: {baris[:40]}")
            continue
        if peta_kelas is None:
            if id_kelas not in EXPECTED_CLASSES:
                perhatian.catat("id kelas tak dikenal dibuang", f"{label.name}: {id_kelas}")
                continue
        else:
            if id_kelas not in peta_kelas:
                perhatian.catat("id kelas tidak ada di pemetaan dibuang")
                continue
            id_kelas = peta_kelas[id_kelas]
        if len(angka) == 4:
            x, y, w, h = angka
            angka = [x - w / 2, y - h / 2, x + w / 2, y - h / 2,
                     x + w / 2, y + h / 2, x - w / 2, y + h / 2]
        if len(angka) < 6 or len(angka) % 2:
            perhatian.catat("poligon tidak valid dibuang", f"{label.name}: {len(angka)} nilai")
            continue
        if any(v != v or abs(v) > 1e6 for v in angka):
            perhatian.catat("koordinat NaN/inf dibuang", label.name)
            continue
        angka = [min(1.0, max(0.0, v)) for v in angka]
        hasil.append((id_kelas, angka))
    return hasil, True


def _kumpulkan_dataset_utama(
    daftar: list[tuple[str, Path]],
    perhatian: PerhatianData,
) -> list[Rekaman]:
    rekaman: dict[str, Rekaman] = {}
    for nama, data_yaml in daftar:
        if not data_yaml.is_file():
            raise FileNotFoundError(f"data.yaml untuk {nama} tidak ditemukan: {data_yaml}")
        data: dict[str, Any] = yaml.safe_load(data_yaml.read_text(encoding="utf-8-sig")) or {}
        names = baca_names(data, data_yaml)
        if len(names) != len(EXPECTED_CLASSES) or set(names.values()) != set(EXPECTED_CLASSES.values()):
            raise ValueError(
                f"Kelas di {data_yaml} adalah {names}; harus berisi "
                f"{sorted(EXPECTED_CLASSES.values())}"
            )
        id_training = {nama: id_kelas for id_kelas, nama in EXPECTED_CLASSES.items()}
        peta_kelas = {id_sumber: id_training[nama] for id_sumber, nama in names.items()}
        gambar_list = daftar_gambar(data_yaml)
        if not gambar_list:
            raise ValueError(f"Tidak ada gambar di {data_yaml}")
        for gambar in gambar_list:
            baris, ada = baca_label(jalur_label(gambar), peta_kelas, perhatian)
            if not ada:
                perhatian.catat("gambar tanpa file label dilewati", gambar.name)
                continue
            kelompok = gambar.stem.split("__", 1)[0]
            nama_file = gambar.name
            if nama_file in rekaman:
                lama = rekaman[nama_file]
                if lama.gambar.stat().st_size == gambar.stat().st_size:
                    perhatian.catat("gambar duplikat antar-dataset dilewati")
                    continue
                kelompok_baru = f"{kelompok}~{nama}"
                sisa = gambar.stem.split("__", 1)[1] if "__" in gambar.stem else None
                nama_file = f"{kelompok_baru}__{sisa}{gambar.suffix}" if sisa else f"{kelompok_baru}{gambar.suffix}"
                kelompok = kelompok_baru
                if nama_file in rekaman:
                    continue
            item = Rekaman(nama_file, gambar, kelompok, baris, "utama",
                           Counter(k for k, _ in baris))
            rekaman[nama_file] = item
    return list(rekaman.values())


def _kumpulkan_penunjang(folder: Path, perhatian: PerhatianData) -> list[Rekaman]:
    hasil: list[Rekaman] = []
    if not folder.is_dir():
        return hasil
    for sub in sorted(p for p in folder.iterdir() if p.is_dir()):
        data_yaml = sub / "data.yaml"
        if not data_yaml.is_file():
            perhatian.catat("folder penunjang tanpa data.yaml dilewati", sub.name)
            continue
        data: dict[str, Any] = yaml.safe_load(data_yaml.read_text(encoding="utf-8-sig")) or {}
        names = baca_names(data, data_yaml)
        target = sub.name.removeprefix("dataset_")
        if target in EXPECTED_CLASSES.values():
            perhatian.catat("folder berisi kelas utama, bukan penunjang, dilewati", sub.name)
            continue
        ids = [i for i, n in names.items() if n == target]
        if len(ids) != 1 and len(names) == 1:
            ids = list(names)
        if len(ids) != 1:
            perhatian.catat("kelas penunjang tidak cocok dengan data.yaml, dilewati", sub.name)
            continue
        peta = {ids[0]: SUPPORT_CLASS_ID}
        for gambar in daftar_gambar(data_yaml):
            baris, ada = baca_label(jalur_label(gambar), peta, perhatian)
            if not ada or not baris:
                perhatian.catat("gambar penunjang tanpa label dilewati")
                continue
            nama_file = f"{sub.name}~{gambar.name}"
            kelompok = f"penunjang~{sub.name}~{gambar.stem.split('__', 1)[0]}"
            hasil.append(Rekaman(nama_file, gambar, kelompok, baris, "penunjang",
                                 Counter(k for k, _ in baris)))
    return hasil


def kelompokkan(rekaman: list[Rekaman]) -> dict[str, Kelompok]:
    kelompok: dict[str, Kelompok] = {}
    for item in rekaman:
        g = kelompok.setdefault(item.kelompok, Kelompok(item.kelompok))
        g.rekaman.append(item)
        g.kelas_instans.update(item.kelas)
        g.kelas_gambar.update(item.kelas.keys())
    return kelompok


def bagi(kelompok: dict[str, Kelompok], seed: int) -> dict[str, str]:
    rng = random.Random(seed)
    kunci_urut = sorted(kelompok)
    jumlah_kelompok_per_kelas: Counter[int] = Counter()
    for kunci in kunci_urut:
        jumlah_kelompok_per_kelas.update(kelompok[kunci].kelas_gambar.keys())
    urutan_kelas = sorted(jumlah_kelompok_per_kelas, key=lambda c: (jumlah_kelompok_per_kelas[c], c))

    penugasan: dict[str, str] = {}
    for kelas in urutan_kelas:
        tertunda = [k for k in kunci_urut if k not in penugasan and kelas in kelompok[k].kelas_gambar]
        rng.shuffle(tertunda)
        sudah: Counter[str] = Counter()
        for k, split in penugasan.items():
            sudah[split] += kelompok[k].kelas_gambar.get(kelas, 0)
        total = sum(sudah.values()) + sum(kelompok[k].kelas_gambar[kelas] for k in tertunda)
        for k in tertunda:
            ukuran = kelompok[k].kelas_gambar[kelas]
            pilih = max(SPLITS, key=lambda s: (RASIO[s] * total - sudah[s], RASIO[s]))
            penugasan[k] = pilih
            sudah[pilih] += ukuran
    for k in kunci_urut:
        if k not in penugasan:
            penugasan[k] = rng.choices(SPLITS, weights=[RASIO[s] for s in SPLITS])[0]
    _perbaiki_cakupan(kelompok, penugasan, urutan_kelas)
    return penugasan


def _perbaiki_cakupan(
    kelompok: dict[str, Kelompok],
    penugasan: dict[str, str],
    kelas_list: Sequence[int],
) -> None:
    def instans(kelas: int, split: str) -> int:
        return sum(g.kelas_instans.get(kelas, 0) for k, g in kelompok.items() if penugasan[k] == split)

    for kelas in kelas_list:
        for target in ("val", "test"):
            if instans(kelas, target):
                continue
            kandidat = [k for k, g in kelompok.items()
                        if penugasan[k] == "train" and kelas in g.kelas_gambar]
            kandidat.sort(key=lambda k: (kelompok[k].ukuran, k))
            for k in kandidat:
                penugasan[k] = target
                if instans(kelas, "train"):
                    break
                penugasan[k] = "train"


def skor_split(
    kelompok: dict[str, Kelompok],
    penugasan: dict[str, str],
) -> dict[str, Any]:
    per_kelas: dict[int, Counter[str]] = {}
    gambar: Counter[str] = Counter()
    for k, g in kelompok.items():
        s = penugasan[k]
        gambar[s] += g.ukuran
        for kelas, n in g.kelas_instans.items():
            per_kelas.setdefault(kelas, Counter())[s] += n
    deviasi: list[float] = []
    kosong = 0
    for kelas, hitung in per_kelas.items():
        total = sum(hitung.values())
        for s in SPLITS:
            if hitung[s] == 0:
                kosong += 1
            deviasi.append(abs(hitung[s] / total - RASIO[s]))
    total_gambar = sum(gambar.values()) or 1
    deviasi.extend(abs(gambar[s] / total_gambar - RASIO[s]) for s in SPLITS)
    skor = (max(deviasi) + sum(deviasi) / len(deviasi)) + 10.0 * kosong
    return {"skor": round(skor, 6), "kelas_kosong": kosong, "gambar": dict(gambar),
            "instans": {TRAINING_CLASSES[c]: dict(h) for c, h in sorted(per_kelas.items())}}


def cari_seed_terbaik(
    kelompok: dict[str, Kelompok],
    kandidat: Iterable[int] = SEED_KANDIDAT,
) -> tuple[int, dict[str, Any]]:
    terbaik: tuple[int, dict[str, Any]] | None = None
    for seed in kandidat:
        info = skor_split(kelompok, bagi(kelompok, seed))
        if terbaik is None or info["skor"] < terbaik[1]["skor"]:
            terbaik = (seed, info)
    assert terbaik is not None
    return terbaik


def _tautkan_atau_salin(sumber: Path, tujuan: Path) -> None:
    try:
        os.link(sumber, tujuan)
    except OSError:
        shutil.copy2(sumber, tujuan)


def tulis_split(
    kelompok: dict[str, Kelompok],
    penugasan: dict[str, str],
    folder: Path,
) -> dict[str, int]:
    if folder.exists():
        shutil.rmtree(folder)
    for s in SPLITS:
        (folder / "images" / s).mkdir(parents=True)
        (folder / "labels" / s).mkdir(parents=True)
    cacah: Counter[str] = Counter()
    for k, g in kelompok.items():
        s = penugasan[k]
        for item in g.rekaman:
            _tautkan_atau_salin(item.gambar, folder / "images" / s / item.nama)
            isi = "".join(
                f"{kelas} " + " ".join(f"{v:.6f}" for v in angka) + "\n" for kelas, angka in item.baris
            )
            (folder / "labels" / s / f"{Path(item.nama).stem}.txt").write_text(isi, encoding="utf-8")
            cacah[s] += 1
    return dict(cacah)


def siapkan_dataset(daftar_utama: list[tuple[str, Path]], folder_penunjang: Path,
                    folder_keluaran: Path, config_path: Path,
                    seed: int | None = None, cari_seed: bool = True) -> dict[str, Any]:
    perhatian = PerhatianData()
    rekaman = _kumpulkan_dataset_utama(daftar_utama, perhatian)
    penunjang = _kumpulkan_penunjang(folder_penunjang, perhatian)
    if not penunjang:
        print(f"[PERINGATAN] Data penunjang kosong/tidak ditemukan di {folder_penunjang}. "
              "Model tidak belajar menolak objek selain 5 kelas utama.")
    perhatian.cetak()
    kelompok = kelompokkan(rekaman + penunjang)
    if len(kelompok) < 6:
        raise ValueError(f"Kelompok gambar terlalu sedikit ({len(kelompok)}) untuk split 70/15/15.")

    if cari_seed or seed is None:
        seed_pilih, info = cari_seed_terbaik(kelompok)
        print(f"[SPLIT] Seed split terbaik dari {len(SEED_KANDIDAT)} kandidat: {seed_pilih} "
              f"(skor keseimbangan {info['skor']})")
    else:
        seed_pilih = seed
        info = skor_split(kelompok, bagi(kelompok, seed_pilih))
        print(f"[SPLIT] Memakai seed split tetap: {seed_pilih} (skor {info['skor']})")
    penugasan = bagi(kelompok, seed_pilih)
    if info["kelas_kosong"]:
        raise ValueError(
            "Ada kelas yang tidak punya data di salah satu split (train/val/test). "
            f"Tambah data kelas tersebut. Detail: {info['instans']}"
        )
    cacah = tulis_split(kelompok, penugasan, folder_keluaran)

    config: dict[str, Any] = {
        "path": folder_keluaran.resolve().as_posix(),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": TRAINING_CLASSES,
    }
    config_path.write_text(yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")
    ringkasan: dict[str, Any] = {
        "seed_split": seed_pilih,
        "rasio_target": RASIO,
        "jumlah_gambar": cacah,
        "jumlah_kelompok": len(kelompok),
        "instans_per_kelas": info["instans"],
        "skor_keseimbangan": info["skor"],
        "peringatan_data": dict(perhatian.hitung),
        "config": str(config_path),
    }
    (folder_keluaran / "split_manifest.json").write_text(
        json.dumps(ringkasan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ringkasan


def main(argv: Sequence[str] | None = None) -> int:
    import argparse
    from datetime import datetime

    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(
        description="Bangun split 70/15/15 VestCare (train/val/test) tanpa kebocoran data."
    )
    parser.add_argument("--seed-split", type=int, default=None,
                        help="kunci seed pembagian data; default: dicari otomatis")
    parser.add_argument("--out", type=Path, default=None,
                        help="folder split tujuan (default: data/results/runs/dataset_splits/split_<waktu>)")
    parser.add_argument("--config", type=Path, default=None,
                        help="YAML dataset gabungan yang ditulis (default: dataset_gabungan.yaml)")
    args = parser.parse_args(argv)

    from train_semua import DATASETS, SUPPORTING_DATASET_DIR

    stempel = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = args.out or root / "data" / "results" / "runs" / "dataset_splits" / f"split_{stempel}"
    config_path = args.config or root / "dataset_gabungan.yaml"
    ringkasan = siapkan_dataset(
        DATASETS, SUPPORTING_DATASET_DIR, folder, config_path,
        seed=args.seed_split, cari_seed=args.seed_split is None,
    )
    print(json.dumps(ringkasan, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
