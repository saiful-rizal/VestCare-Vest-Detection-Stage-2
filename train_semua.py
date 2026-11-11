"""Latih satu model segmentasi YOLO dengan gabungan semua dataset dan kelas."""
import csv
import json
import logging
import math
import random
import sys
import subprocess
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import shutil
import zipfile

import torch
import yaml
from ultralytics import YOLO
from ultralytics.utils import LOGGER

ROOT = Path(__file__).resolve().parent
MODEL = "yolo26n-seg.pt"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}

DATASETS = [
    ("lubang", ROOT / "dataset_utama" / "dataset_lubang" / "3_pengayaan_gerak" / "data.yaml"),
    ("mobil", ROOT / "dataset_utama" / "dataset_mobil" / "3_pengayaan_gerak" / "data.yaml"),
    ("motor", ROOT / "dataset_utama" / "dataset_motor" / "3_pengayaan_gerak" / "data.yaml"),
    ("orang", ROOT / "dataset_utama" / "dataset_orang" / "3_pengayaan_gerak" / "data.yaml"),
    ("pohon", ROOT / "dataset_utama" / "dataset_pohon" / "3_pengayaan_gerak" / "data.yaml"),
]
EXPECTED_CLASSES = {
    0: "pohon",
    1: "mobil",
    2: "motor",
    3: "orang",
    4: "lubang",
}
SUPPORT_CLASS_ID = len(EXPECTED_CLASSES)
SUPPORT_CLASS_NAME = "__non_target_internal__"
TRAINING_CLASSES = {**EXPECTED_CLASSES, SUPPORT_CLASS_ID: SUPPORT_CLASS_NAME}
SUPPORTING_DATASET_DIR = ROOT / "dataset penunjang"
VAL_FRACTION = 0.10

EPOCHS = 100
IMGSZ = 512
BATCH = 4
WORKERS = 0
DEVICE = "0"
PROJECT = "runs"
EXIST_OK = False

PATIENCE = 50
MIN_METRIK_PER_KELAS = 0.98
METRIK_TARGET = ("box_p", "box_map50", "mask_p", "mask_map50")
SEED_LATIH = 0
DETERMINISTIC = True
CACHE = False
AMP = True

OPTIMIZER = "AdamW"
LR0 = 0.001
LRF = 0.01
MOMENTUM = 0.937
WEIGHT_DECAY = 0.0005
LABEL_SMOOTHING = 0.1
WARMUP_EPOCHS = 3.0
WARMUP_MOMENTUM = 0.8
WARMUP_BIAS_LR = 0.1
BOX = 7.5
CLS = 0.5
DFL = 1.5

HSV_H = 0.015
HSV_S = 0.7
HSV_V = 0.4
DEGREES = 10.0
TRANSLATE = 0.1
SCALE = 0.5
SHEAR = 0.0
FLIPUD = 0.0
FLIPLR = 0.5
MOSAIC = 1.0
MIXUP = 0.0
MODELS_DIR = ROOT / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)


class Tee:
    """Tulis output ke terminal dan file log sekaligus."""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, text):
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self):
        for stream in self.streams:
            stream.flush()

    def isatty(self):
        return any(getattr(stream, "isatty", lambda: False)() for stream in self.streams)

    def fileno(self):
        return self.streams[0].fileno()

    @property
    def encoding(self):
        return getattr(self.streams[0], "encoding", "utf-8")


@contextmanager
def capture_console(log_path):
    """Simpan stdout, stderr, dan log Ultralytics ke satu file tanpa mematikan terminal."""
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    handlers = [
        (handler, handler.stream)
        for handler in LOGGER.handlers
        if isinstance(handler, logging.StreamHandler)
    ]

    with Path(log_path).open("w", encoding="utf-8", buffering=1) as log_file:
        stdout = Tee(original_stdout, log_file)
        stderr = Tee(original_stderr, log_file)
        sys.stdout = stdout
        sys.stderr = stderr
        for handler, _ in handlers:
            handler.setStream(stdout)
        try:
            yield
        finally:
            stdout.flush()
            stderr.flush()
            sys.stdout = original_stdout
            sys.stderr = original_stderr
            for handler, stream in handlers:
                handler.setStream(stream)


def _siapkan_gambar_penunjang(output_dir):
    """Stage objek di luar kelas utama sebagai satu kelas internal untuk training."""
    archives = sorted(SUPPORTING_DATASET_DIR.glob("*.zip"))
    if not archives:
        raise FileNotFoundError(
            f"Arsip dataset penunjang tidak ditemukan: {SUPPORTING_DATASET_DIR}"
        )

    image_dir = output_dir / "images" / "train"
    label_dir = output_dir / "labels" / "train"
    image_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)
    staged_images = []
    seen_targets = set()

    for archive_path in archives:
        with zipfile.ZipFile(archive_path) as archive:
            data_member = next(
                (name for name in archive.namelist() if name.lower() == "data.yaml"),
                None,
            )
            if data_member is None:
                raise ValueError(f"data.yaml tidak ditemukan di {archive_path}")
            data = yaml.safe_load(archive.read(data_member)) or {}
            names = data.get("names")
            if isinstance(names, list):
                names = dict(enumerate(names))
            elif isinstance(names, dict):
                names = {int(class_id): str(name) for class_id, name in names.items()}
            else:
                raise ValueError(f"Daftar kelas tidak valid di {archive_path}")

            target_name = archive_path.stem.removeprefix("dataset_")
            target_ids = [
                class_id for class_id, name in names.items() if name == target_name
            ]
            if len(target_ids) != 1:
                raise ValueError(
                    f"Kelas '{target_name}' tidak cocok dengan data.yaml di {archive_path}"
                )
            target_id = target_ids[0]
            image_members = sorted(
                name for name in archive.namelist()
                if name.lower().startswith("images/train/")
                and Path(name).suffix.lower() in IMAGE_EXTENSIONS
            )
            if not image_members:
                raise ValueError(f"Tidak ada gambar train di {archive_path}")

            for member in image_members:
                relative_image = Path(member)
                relative_label = relative_image.with_suffix(".txt")
                label_member = f"labels/train/{relative_label.name}"
                if label_member not in archive.namelist():
                    raise FileNotFoundError(
                        f"Label untuk gambar {member} tidak ditemukan di {archive_path}"
                    )

                remapped_lines = []
                for line in archive.read(label_member).decode("utf-8-sig").splitlines():
                    fields = line.split()
                    if not fields:
                        continue
                    class_id = int(float(fields[0]))
                    if class_id != target_id:
                        raise ValueError(
                            f"Label kelas {class_id} bukan '{target_name}' di "
                            f"{archive_path}:{label_member}"
                        )
                    fields[0] = str(SUPPORT_CLASS_ID)
                    remapped_lines.append(" ".join(fields))
                if not remapped_lines:
                    raise ValueError(
                        f"Label kosong untuk gambar {member} di {archive_path}"
                    )

                staged_name = f"{archive_path.stem}_{relative_image.name}"
                image_target = image_dir / staged_name
                label_target = label_dir / f"{Path(staged_name).stem}.txt"
                if image_target in seen_targets:
                    raise ValueError(f"Nama gambar penunjang duplikat: {staged_name}")
                seen_targets.add(image_target)
                image_target.write_bytes(archive.read(member))
                label_target.write_text(
                    "\n".join(remapped_lines) + "\n", encoding="utf-8"
                )
                staged_images.append(image_target.resolve())

    return staged_images


def buat_data_gabungan(run_name=None):
    """Split kelas utama dan tambahkan objek penunjang hanya ke data train."""
    groups_by_dataset = {}

    for nama, data_yaml in DATASETS:
        if not data_yaml.is_file():
            raise FileNotFoundError(f"data.yaml untuk {nama} tidak ditemukan: {data_yaml}")

        with data_yaml.open(encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}

        names = data.get("names")
        if isinstance(names, list):
            names = dict(enumerate(names))
        elif isinstance(names, dict):
            names = {int(class_id): str(class_name) for class_id, class_name in names.items()}
        else:
            raise ValueError(f"Konfigurasi kelas tidak valid di {data_yaml}")
        if names != EXPECTED_CLASSES:
            raise ValueError(
                f"Kelas di {data_yaml} adalah {names}; seharusnya {EXPECTED_CLASSES}"
            )

        dataset_dir = data_yaml.parent
        if isinstance(data.get("train"), list):
            raise ValueError(f"Train harus menunjuk satu folder gambar di {data_yaml}")
        image_dir = Path(data.get("train", "images"))
        if not image_dir.is_absolute():
            image_dir = dataset_dir / image_dir
        image_dir = image_dir.resolve()
        if not image_dir.is_dir():
            raise FileNotFoundError(f"Folder gambar untuk {nama} tidak ditemukan: {image_dir}")

        groups = {}
        for image in sorted(image_dir.iterdir()):
            if not image.is_file() or image.suffix.lower() not in IMAGE_EXTENSIONS:
                continue
            group_key = image.stem.split("__", 1)[0]
            group = groups.setdefault(group_key, {"images": [], "classes": set()})
            group["images"].append(image.resolve())
            label = image_dir.parent / "labels" / f"{image.stem}.txt"
            if label.is_file():
                for line in label.read_text(encoding="utf-8").splitlines():
                    fields = line.split()
                    if fields:
                        class_id = int(float(fields[0]))
                        if class_id not in EXPECTED_CLASSES:
                            raise ValueError(f"Class ID {class_id} tidak dikenal di {label}")
                        group["classes"].add(class_id)
        if len(groups) < 2:
            raise ValueError(f"Dataset {nama} harus memiliki sedikitnya dua kelompok gambar.")
        groups_by_dataset[nama] = groups

    train_images = []
    val_images = []
    val_groups = set()
    image_classes = {}
    for dataset_name, groups in groups_by_dataset.items():
        keys = sorted(groups)
        random.Random(0).shuffle(keys)
        val_count = max(1, round(len(keys) * VAL_FRACTION))
        selected = set(keys[:val_count])
        val_groups.update((dataset_name, key) for key in selected)
        for key, group in groups.items():
            image_classes.update({image: group["classes"] for image in group["images"]})
            (val_images if key in selected else train_images).extend(group["images"])

    def classes_in(images):
        found = set()
        for image in images:
            found.update(image_classes[image])
        return found

    val_classes = classes_in(val_images)
    train_classes = classes_in(train_images)
    for class_id in sorted(set(EXPECTED_CLASSES) - val_classes):
        candidates = [
            (dataset_name, key, group)
            for dataset_name, groups in groups_by_dataset.items()
            for key, group in groups.items()
            if (dataset_name, key) not in val_groups and class_id in group["classes"]
        ]
        candidates.sort(key=lambda item: (len(item[2]["images"]), item[0], item[1]))
        for dataset_name, key, group in candidates:
            group_images = set(group["images"])
            remaining_train = [
                image for image in train_images if image not in group_images
            ]
            if classes_in(remaining_train) >= set(EXPECTED_CLASSES):
                val_groups.add((dataset_name, key))
                val_images.extend(group["images"])
                train_images = remaining_train
                val_classes = classes_in(val_images)
                train_classes = classes_in(train_images)
                break
        else:
            raise ValueError(
                f"Tidak dapat memastikan kelas {EXPECTED_CLASSES[class_id]} ada di train dan val."
            )

    if set(EXPECTED_CLASSES) - train_classes:
        raise ValueError(f"Kelas hilang dari data train: {set(EXPECTED_CLASSES) - train_classes}")
    if set(EXPECTED_CLASSES) - val_classes:
        raise ValueError(f"Kelas hilang dari data val: {set(EXPECTED_CLASSES) - val_classes}")

    run_name = run_name or f"training_{datetime.now():%Y%m%d_%H%M%S_%f}"
    split_dir = ROOT / "runs" / "dataset_splits" / run_name
    split_dir.mkdir(parents=True, exist_ok=True)
    supporting_images = _siapkan_gambar_penunjang(split_dir / "supporting")
    train_images.extend(supporting_images)

    train_manifest = split_dir / "train.txt"
    val_manifest = split_dir / "val.txt"
    train_manifest.write_text(
        "".join(f"{image.as_posix()}\n" for image in sorted(train_images)),
        encoding="utf-8",
    )
    val_manifest.write_text(
        "".join(f"{image.as_posix()}\n" for image in sorted(val_images)),
        encoding="utf-8",
    )

    config_path = ROOT / "dataset_gabungan.yaml"
    config = {
        "path": ROOT.as_posix(),
        "train": train_manifest.as_posix(),
        "val": val_manifest.as_posix(),
        "names": TRAINING_CLASSES,
    }
    with config_path.open("w", encoding="utf-8") as file:
        yaml.safe_dump(config, file, sort_keys=False, allow_unicode=True)
    return config_path


def _baca_gambar_split(source, root):
    """Ambil file gambar dari direktori atau manifest gambar YOLO."""
    path = Path(source)
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if path.is_file():
        return [
            (Path(line.strip()) if Path(line.strip()).is_absolute() else path.parent / line.strip()).resolve()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    if path.is_dir():
        return sorted(
            image.resolve() for image in path.iterdir()
            if image.is_file() and image.suffix.lower() in IMAGE_EXTENSIONS
        )
    raise FileNotFoundError(f"Path dataset tidak ditemukan: {path}")


def informasi_dataset(data_yaml):
    """Hitung jumlah gambar dan overlap sebenarnya antara train dan val."""
    with Path(data_yaml).open(encoding="utf-8") as file:
        data = yaml.safe_load(file)

    info = {}
    image_sets = {}
    for split in ("train", "val"):
        sources = data.get(split, "images")
        sources = sources if isinstance(sources, list) else [sources]
        root = Path(data.get("path", Path(data_yaml).parent))
        images = {
            image for source in sources
            for image in _baca_gambar_split(source, root)
        }
        image_sets[split] = images
        info[split] = {
            "image_count": len(images),
            "sources": [str(source) for source in sources],
        }

    info["train_val_image_overlap_count"] = len(image_sets["train"] & image_sets["val"])
    return info


def angka_json(value):
    """Konversi metrik numerik ke tipe JSON dan ubah NaN/inf menjadi null."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def ringkasan_metrik(results):
    """Ambil metrik agregat serta metrik box dan mask untuk setiap kelas."""
    names = results.names
    class_names = names if isinstance(names, dict) else dict(enumerate(names))
    summary_by_name = {row["Class"]: row for row in results.summary(decimals=6)}
    mask_by_name = {}
    mask_map75_by_name = {}
    for position, class_id in enumerate(results.seg.ap_class_index):
        values = results.seg.class_result(position)
        mask_by_name[class_names[class_id]] = values
        mask_map75_by_name[class_names[class_id]] = results.seg.all_ap[position][5]

    per_class = []
    for class_id, class_name in sorted(EXPECTED_CLASSES.items()):
        row = summary_by_name.get(class_name, {})
        mask = mask_by_name.get(class_name)
        per_class.append({
            "class_id": int(class_id),
            "class_name": class_name,
            "images": int(row.get("Images", 0)),
            "instances": int(row.get("Instances", 0)),
            "box_precision": angka_json(row.get("Box-P")),
            "box_recall": angka_json(row.get("Box-R")),
            "box_f1": angka_json(row.get("Box-F1")),
            "box_map50": angka_json(row.get("mAP50")),
            "box_map75": angka_json(row.get("mAP75")),
            "box_map50_95": angka_json(row.get("mAP50-95")),
            "mask_precision": angka_json(row.get("Mask-P")),
            "mask_recall": angka_json(row.get("Mask-R")),
            "mask_f1": angka_json(row.get("Mask-F1")),
            "mask_map50": angka_json(mask[2]) if mask else None,
            "mask_map75": angka_json(mask_map75_by_name.get(class_name)),
            "mask_map50_95": angka_json(mask[3]) if mask else None,
        })

    overall = {
        key: angka_json(value)
        for key, value in results.results_dict.items()
    }
    return {
        "overall": overall,
        "per_class": per_class,
        "speed_ms_per_image": {
            key: angka_json(value) for key, value in results.speed.items()
        },
    }


def simpan_laporan(run_dir, report):
    """Simpan laporan terstruktur JSON, CSV per kelas, dan ringkasan teks."""
    run_dir = Path(run_dir)
    reports_dir = Path(run_dir) / "reports"
    raw_dir = Path(run_dir) / "raw"
    reports_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    for source_name in ("results.csv", "args.yaml"):
        source = run_dir / source_name
        if source.is_file():
            shutil.copy2(source, raw_dir / source_name)

    report["artifacts"] = {
        "raw_dir": str(raw_dir),
        "reports_dir": str(reports_dir),
        "training_metrics_csv": str(run_dir / "results.csv"),
        "raw_training_metrics_csv": str(raw_dir / "results.csv"),
        "training_log": str(run_dir / "training.log"),
        "raw_training_log": str(raw_dir / "training.log"),
        "epoch_metrics_plot": str(run_dir / "results.png"),
        "validation_plots_dir": str(run_dir / "evaluation" / "val"),
        "detailed_evaluation_dir": report.get("detailed_evaluation_dir"),
        "best_checkpoint": report.get("checkpoint_best"),
    }

    (reports_dir / "training_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    lines = [
        "LAPORAN TRAINING YOLO SEGMENTASI",
        f"Model: {report['model']}",
        f"Epoch selesai: {report['training']['epochs_completed']} / {report['training']['epochs_requested']}",
        f"Gambar train: {report['dataset']['train']['image_count']}",
        f"Gambar val: {report['dataset']['val']['image_count']}",
    ]
    if report["dataset"]["train_val_image_overlap_count"]:
        lines.append("PERINGATAN: sumber train dan val memiliki gambar yang sama.")
    target = report.get("quality_gate")
    if target:
        lines.extend([
            "",
            f"TARGET PER KELAS: {'LULUS' if target['passed'] else 'BELUM LULUS'}",
            f"Ambang semua metrik: {target['threshold']:.2%}",
            f"Metrik wajib: {', '.join(target['metrics'])}",
            f"Bobot aktif diganti: {'ya' if target.get('deployed') else 'tidak'}",
            f"Laporan, grafik, dan log evaluasi: {target['report_dir']}",
        ])
        lines.extend([
            "",
            f"{'Kelas':<12}{'Box P':>10}{'Box mAP50':>12}"
            f"{'Mask P':>10}{'Mask mAP50':>12}",
        ])

        def format_target_metric(value):
            return f"{value:.4f}" if value is not None else "n/a"

        for class_name, metrics in target["per_class"].items():
            lines.append(
                f"{class_name:<12}"
                f"{format_target_metric(metrics['box_p']):>10}"
                f"{format_target_metric(metrics['box_map50']):>12}"
                f"{format_target_metric(metrics['mask_p']):>10}"
                f"{format_target_metric(metrics['mask_map50']):>12}"
            )
    for split, result in report["validation"].items():
        lines.extend(["", f"HASIL VALIDASI SPLIT {split.upper()}"])
        lines.extend(f"{key}: {value}" for key, value in result["overall"].items())
        lines.extend([
            "",
            f"{'Kelas':<12}{'Box P':>9}{'Box R':>9}{'Box F1':>9}{'Box mAP50':>12}"
            f"{'Box mAP50-95':>15}{'Mask P':>9}{'Mask R':>9}{'Mask F1':>9}"
            f"{'Mask mAP50':>12}{'Mask mAP50-95':>15}",
        ])
        for row in result["per_class"]:
            def format_metric(value):
                return f"{value:.4f}" if isinstance(value, (int, float)) else "n/a"

            lines.append(
                f"{row['class_name']:<12}"
                f"{format_metric(row['box_precision']):>9}"
                f"{format_metric(row['box_recall']):>9}"
                f"{format_metric(row['box_f1']):>9}"
                f"{format_metric(row['box_map50']):>12}"
                f"{format_metric(row['box_map50_95']):>15}"
                f"{format_metric(row['mask_precision']):>9}"
                f"{format_metric(row['mask_recall']):>9}"
                f"{format_metric(row['mask_f1']):>9}"
                f"{format_metric(row['mask_map50']):>12}"
                f"{format_metric(row['mask_map50_95']):>15}"
            )
        lines.append(f"CSV detail per kelas: {split}_class_metrics.csv.")
    (reports_dir / "training_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    for split, result in report["validation"].items():
        class_rows = result["per_class"]
        if not class_rows:
            continue
        csv_path = reports_dir / f"{split}_class_metrics.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(class_rows[0]))
            writer.writeheader()
            writer.writerows(class_rows)

    plot_files = sorted(
        str(path) for path in run_dir.glob("*.png")
    )
    (reports_dir / "artifacts.json").write_text(
        json.dumps(
            {
                **report["artifacts"],
                "training_plots": plot_files,
                "validation_reports": [
                    str(path) for path in sorted(reports_dir.glob("*_class_metrics.csv"))
                ],
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


def periksa_target(rows, report_dir):
    metrics_by_class = {
        row["kelas"]: {
            metric: angka_json(row.get(metric))
            for metric in METRIK_TARGET
        }
        for row in rows
    }
    if (
        len(metrics_by_class) != len(rows)
        or set(metrics_by_class) != set(EXPECTED_CLASSES.values())
    ):
        raise ValueError(
            f"Hasil evaluasi tidak mencakup semua kelas: {sorted(metrics_by_class)}"
        )

    failures = [
        {
            "kelas": class_name,
            "metrik": metric,
            "nilai": value,
            "ambang": MIN_METRIK_PER_KELAS,
        }
        for class_name, metrics in metrics_by_class.items()
        for metric, value in metrics.items()
        if value is None or value < MIN_METRIK_PER_KELAS
    ]
    passed = not failures
    print(
        f"\n[TARGET] {'LULUS' if passed else 'BELUM LULUS'}: "
        f"{len(METRIK_TARGET)} metrik x {len(metrics_by_class)} kelas "
        f"harus >= {MIN_METRIK_PER_KELAS:.0%}."
    )
    if failures:
        for failure in failures:
            value = failure["nilai"]
            shown = "n/a" if value is None else f"{value:.2%}"
            print(
                f"[TARGET] {failure['kelas']} {failure['metrik']}: "
                f"{shown} (target {MIN_METRIK_PER_KELAS:.0%})"
            )
    return {
        "passed": passed,
        "threshold": MIN_METRIK_PER_KELAS,
        "metrics": list(METRIK_TARGET),
        "per_class": metrics_by_class,
        "failures": failures,
        "report_dir": str(report_dir),
    }


def evaluasi_laporan(best, data_yaml, run_dir):
    """Jalankan evaluasi lengkap dengan laporan kelas, grafik, dan log."""
    output_dir = Path(run_dir) / "evaluation" / "final"
    command = [
        sys.executable,
        str(ROOT / "start_eval.py"),
        "--dataset", str(data_yaml),
        "--split", "val",
        "--model", str(best),
        "--out", str(output_dir),
        "--imgsz", str(IMGSZ),
        "--batch", "1",
        "--device", DEVICE,
    ]
    process = subprocess.Popen(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout is None:
        raise RuntimeError("Tidak dapat membaca keluaran proses evaluasi.")
    for line in process.stdout:
        print(line, end="")
    return_code = process.wait()
    if return_code:
        raise subprocess.CalledProcessError(return_code, command)

    required_outputs = (
        output_dir / "per_kelas.csv",
        output_dir / "ringkasan_test.json",
        output_dir / "laporan_akurasi.txt",
        output_dir / "grafik" / "1_ringkasan_total.png",
        output_dir / "grafik" / "2_per_kelas.png",
    )
    missing = [str(path) for path in required_outputs if not path.is_file()]
    if not list(output_dir.glob("evaluation_*.log")):
        missing.append(str(output_dir / "evaluation_*.log"))
    if missing:
        raise FileNotFoundError(
            "Laporan evaluasi belum lengkap: " + ", ".join(missing)
        )

    with (output_dir / "per_kelas.csv").open(
        encoding="utf-8-sig", newline=""
    ) as file:
        rows = list(csv.DictReader(file))
    return periksa_target(rows, output_dir)


def pasang_model(best):
    """Ganti bobot layanan secara atomik setelah seluruh target validasi lulus."""
    serving_model = MODELS_DIR / "best.pt"
    temporary_model = MODELS_DIR / f".best-{datetime.now():%Y%m%d%H%M%S%f}.tmp"
    try:
        shutil.copy2(best, temporary_model)
        temporary_model.replace(serving_model)
    finally:
        temporary_model.unlink(missing_ok=True)
    print(f"[INFO] Bobot lolos target dipasang: {serving_model}")
    return serving_model


def bersihkan_hasil_lama(run_dir, log_path):
    """Hapus hanya artefak training/evaluasi VestCare yang sudah digantikan."""
    run_dir = Path(run_dir).resolve()
    old_run = (ROOT / "runs" / "segment" / "runs" / "semua_kelas_yolo26n").resolve()
    expected_parent = (ROOT / "runs" / "segment" / "runs").resolve()
    if old_run != run_dir and old_run.parent == expected_parent and old_run.is_dir():
        shutil.rmtree(old_run)
        print(f"[INFO] Hasil training/evaluasi lama dihapus: {old_run}")

    duplicate_model = MODELS_DIR / "best_semua_kelas.pt"
    if duplicate_model.is_file():
        duplicate_model.unlink()
        print(f"[INFO] Checkpoint duplikat dihapus: {duplicate_model}")

    current_log = Path(log_path).resolve()
    for old_log in ROOT.glob("training_semua_*.log"):
        if old_log.resolve() != current_log and old_log.is_file():
            old_log.unlink()
            print(f"[INFO] Log training lama dihapus: {old_log}")


def latih(data_yaml, run_name):
    if not torch.cuda.is_available():
        raise RuntimeError(
            "Training ini dikonfigurasi untuk GPU, tetapi CUDA tidak tersedia pada "
            "interpreter Python aktif. Jalankan dengan .venv\\Scripts\\python.exe."
        )

    print("\n" + "=" * 60)
    print("[INFO] Melatih satu model dengan gabungan semua dataset dan kelas")
    print(f"[INFO] Dataset config : {data_yaml}")
    print(f"[INFO] Jumlah kelas keluaran: {len(EXPECTED_CLASSES)}")
    print(f"[INFO] Kelas internal penolak objek: {SUPPORT_CLASS_NAME}")
    print(f"[INFO] model          : {MODEL}")
    print(f"[INFO] device         : {DEVICE}")
    print(f"[INFO] GPU            : {torch.cuda.get_device_name(int(DEVICE))}")
    print(f"[INFO] Resolusi       : {IMGSZ}px | batch: {BATCH} | epoch maks: {EPOCHS}")
    print("=" * 60 + "\n")

    model = YOLO(MODEL)
    model.train(
        data=str(data_yaml),
        model=MODEL,
        epochs=EPOCHS,
        imgsz=IMGSZ,
        batch=BATCH,
        workers=WORKERS,
        device=DEVICE,
        project=PROJECT,
        name=run_name,
        task="segment",
        exist_ok=EXIST_OK,
        verbose=True,
        patience=PATIENCE,
        seed=SEED_LATIH,
        deterministic=DETERMINISTIC,
        cache=CACHE,
        amp=AMP,
        optimizer=OPTIMIZER,
        lr0=LR0,
        lrf=LRF,
        momentum=MOMENTUM,
        weight_decay=WEIGHT_DECAY,
        label_smoothing=LABEL_SMOOTHING,
        warmup_epochs=WARMUP_EPOCHS,
        warmup_momentum=WARMUP_MOMENTUM,
        warmup_bias_lr=WARMUP_BIAS_LR,
        box=BOX,
        cls=CLS,
        dfl=DFL,
        hsv_h=HSV_H,
        hsv_s=HSV_S,
        hsv_v=HSV_V,
        degrees=DEGREES,
        translate=TRANSLATE,
        scale=SCALE,
        shear=SHEAR,
        flipud=FLIPUD,
        fliplr=FLIPLR,
        mosaic=MOSAIC,
        mixup=MIXUP,
    )

    best = Path(model.trainer.save_dir) / "weights" / "best.pt"
    if not best.is_file():
        raise FileNotFoundError(f"best.pt tidak ditemukan setelah training: {best}")
    return Path(model.trainer.save_dir).resolve(), best.resolve()


def main():
    log_path = ROOT / f"training_semua_{datetime.now():%Y%m%d_%H%M%S_%f}.log"
    run_name = f"semua_kelas_yolo26n_{datetime.now():%Y%m%d_%H%M%S}"
    run_dir = None
    exit_code = 0
    try:
        with capture_console(log_path):
            data_yaml = buat_data_gabungan(run_name)
            dataset = informasi_dataset(data_yaml)
            print(f"[INFO] Menggabungkan {len(DATASETS)} dataset utama ke satu proses training.")
            print(
                f"[INFO] Kelas keluaran: {', '.join(EXPECTED_CLASSES.values())} | "
                f"train: {dataset['train']['image_count']} gambar | "
                f"val: {dataset['val']['image_count']} gambar"
            )
            if dataset["train_val_image_overlap_count"]:
                raise ValueError(
                    "Data train dan val beririsan sebanyak "
                    f"{dataset['train_val_image_overlap_count']} gambar."
                )

            run_dir, best = latih(data_yaml, run_name)
            results_csv = run_dir / "results.csv"
            with results_csv.open(encoding="utf-8-sig", newline="") as file:
                history = list(csv.DictReader(file))
            if not history:
                raise ValueError(f"Tidak ada riwayat metrik training di {results_csv}")

            report = {
                "model": MODEL,
                "checkpoint_best": str(best),
                "dataset_config": str(data_yaml),
                "dataset": dataset,
                "classes": EXPECTED_CLASSES,
                "training": {
                    "epochs_requested": EPOCHS,
                    "epochs_completed": len(history),
                    "last_epoch": history[-1].get("epoch"),
                    "last_epoch_metrics": history[-1],
                    "results_csv": str(results_csv),
                    "args_yaml": str(run_dir / "args.yaml"),
                },
                "validation": {},
                "console_log": str(run_dir / "training.log"),
            }
            simpan_laporan(run_dir, report)

            validation_model = YOLO(str(best))
            for split in ("val",):
                print(f"\n[INFO] Evaluasi checkpoint terbaik pada split {split}...")
                results = validation_model.val(
                    data=str(data_yaml),
                    split=split,
                    imgsz=IMGSZ,
                    batch=BATCH,
                    workers=WORKERS,
                    device=DEVICE,
                    project=str(run_dir / "evaluation"),
                    name=split,
                    task="segment",
                    exist_ok=True,
                    verbose=True,
                    plots=True,
                    save_json=True,
                    save_txt=True,
                    save_conf=True,
                    classes=sorted(EXPECTED_CLASSES),
                )
                report["validation"][split] = ringkasan_metrik(results)
                report["validation"][split]["artifacts_dir"] = str(
                    run_dir / "evaluation" / split
                )
                simpan_laporan(run_dir, report)
                print(
                    (run_dir / "reports" / "training_report.txt")
                    .read_text(encoding="utf-8")
                )

            report["quality_gate"] = evaluasi_laporan(best, data_yaml, run_dir)
            report["detailed_evaluation_dir"] = report["quality_gate"]["report_dir"]
            report["quality_gate"]["deployed"] = False
            if report["quality_gate"]["passed"]:
                pasang_model(best)
                report["quality_gate"]["deployed"] = True
                report["quality_gate"]["serving_model"] = str(MODELS_DIR / "best.pt")
                print(
                    "[INFO] Restart server_rest_api.py agar server memuat bobot baru."
                )
            else:
                exit_code = 2
                report["quality_gate"]["serving_model"] = str(MODELS_DIR / "best.pt")
                print(
                    "[PERINGATAN] Target 98% belum tercapai. Model layanan lama "
                    "dipertahankan; periksa laporan per kelas dan anotasi yang salah."
                )
            simpan_laporan(run_dir, report)
            bersihkan_hasil_lama(run_dir, log_path)
            print(f"\n[INFO] Laporan lengkap: {run_dir / 'reports'}")
            print(f"[INFO] Laporan evaluasi, grafik, dan log: {run_dir / 'evaluation' / 'final'}")
            print(f"[INFO] Log mentah: {log_path}")
            print(f"[INFO] Bobot akhir ada di: {MODELS_DIR}")
    finally:
        if run_dir is not None and log_path.is_file():
            run_dir = Path(run_dir)
            shutil.copy2(log_path, run_dir / "training.log")
            raw_dir = run_dir / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(log_path, raw_dir / "training.log")
            artifacts_file = run_dir / "reports" / "artifacts.json"
            if artifacts_file.is_file():
                artifacts = json.loads(artifacts_file.read_text(encoding="utf-8"))
                artifacts["training_log"] = str(run_dir / "training.log")
                artifacts["raw_training_log"] = str(raw_dir / "training.log")
                artifacts_file.write_text(
                    json.dumps(artifacts, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
