"""Jalankan pipeline evaluasi final (tahap 08) dengan GPU secara default."""
import argparse
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import os
import subprocess
import sys
from collections import defaultdict
from collections.abc import Generator, Mapping
from typing import Any, Optional, TextIO, cast


ROOT = Path(__file__).resolve().parent
VENV_PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"


if VENV_PYTHON.is_file() and os.path.normcase(sys.executable) != os.path.normcase(str(VENV_PYTHON)):
    sys.exit(
        subprocess.call(
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=ROOT,
        )
    )

if not any(arg == "--device" or arg.startswith("--device=") for arg in sys.argv[1:]):
    sys.argv.extend(("--device", "0"))

os.chdir(ROOT)


import csv
import json
import logging
import random
import shutil
import statistics
import tempfile
import time
import yaml

JsonRecord = dict[str, Any]


class EvalArgs(argparse.Namespace):
    dataset: Path
    splits_dir: Optional[Path]
    hasil07: Path
    split: Optional[str]
    model: Optional[Path]
    out: Path
    imgsz: int
    batch: int
    conf: float
    contoh: int
    n_kecepatan: int
    device: Optional[str]


def _baca_kelas(raw_names: Any, source: str | Path) -> dict[int, str]:
    if isinstance(raw_names, list):
        if not all(isinstance(name, str) for name in cast(list[Any], raw_names)):
            raise ValueError(f"Daftar kelas tidak valid di {source}")
        return dict(enumerate(cast(list[str], raw_names)))
    if isinstance(raw_names, dict):
        return {
            int(class_id): str(name)
            for class_id, name in cast(dict[Any, Any], raw_names).items()
        }
    raise ValueError(f"Daftar kelas tidak valid di {source}")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
EXPECTED_CLASSES = {
    0: "pohon",
    1: "mobil",
    2: "motor",
    3: "orang",
    4: "lubang",
}
INTERNAL_CLASSES = {5: "__non_target_internal__"}
METRIC_COLUMNS = [
    "mask_p", "mask_r", "mask_f1", "mask_map50", "mask_map5095",
    "box_p", "box_r", "box_f1", "box_map50", "box_map5095",
]


class Tee:
    def __init__(self, *streams: TextIO) -> None:
        self.streams: tuple[TextIO, ...] = streams

    def write(self, text: str) -> int:
        for stream in self.streams:
            stream.write(text)
        return len(text)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()

    def isatty(self) -> bool:
        return any(stream.isatty() for stream in self.streams)

    def fileno(self) -> int:
        return self.streams[0].fileno()

    @property
    def encoding(self) -> str:
        return self.streams[0].encoding or "utf-8"


@contextmanager
def capture_console(log_path: str | Path) -> Generator[None, None, None]:
    from ultralytics.utils import LOGGER

    original_stdout, original_stderr = sys.stdout, sys.stderr
    handlers: list[tuple[logging.StreamHandler[TextIO], TextIO]] = []
    for raw_handler in LOGGER.handlers:
        if isinstance(raw_handler, logging.StreamHandler):
            handler = cast(logging.StreamHandler[TextIO], raw_handler)
            handlers.append((handler, handler.stream))
    with Path(log_path).open("w", encoding="utf-8", buffering=1) as log_file:
        stdout, stderr = Tee(original_stdout, log_file), Tee(original_stderr, log_file)
        sys.stdout, sys.stderr = stdout, stderr
        for handler, _ in handlers:
            handler.setStream(cast(TextIO, stdout))
        try:
            yield
        finally:
            stdout.flush()
            stderr.flush()
            sys.stdout, sys.stderr = original_stdout, original_stderr
            for handler, stream in handlers:
                handler.setStream(stream)


def f1(precision: float, recall: float) -> float:
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0


def read_dataset(data_yaml: str | Path) -> tuple[JsonRecord, dict[int, str]]:
    with Path(data_yaml).open(encoding="utf-8") as file:
        raw_data: Any = yaml.safe_load(file) or {}
    if not isinstance(raw_data, dict):
        raise ValueError(f"Konfigurasi dataset tidak valid di {data_yaml}")
    data = cast(JsonRecord, raw_data)
    names = _baca_kelas(data.get("names"), data_yaml)
    if names not in (EXPECTED_CLASSES, {**EXPECTED_CLASSES, **INTERNAL_CLASSES}):
        raise ValueError(
            f"Dataset harus memakai kelas target {EXPECTED_CLASSES} "
            f"dengan atau tanpa kelas internal; ditemukan {names}."
        )
    return data, names


def list_split_images(data_yaml: str | Path, split: str) -> list[Path]:
    data, _ = read_dataset(data_yaml)
    root = Path(data.get("path", Path(data_yaml).parent))
    if not root.is_absolute():
        root = Path(data_yaml).parent / root
    raw_sources: Any = data.get(split)
    if raw_sources is None:
        raise ValueError(f"Split '{split}' tidak tersedia di {data_yaml}")
    sources: list[Any] = (
        cast(list[Any], raw_sources) if isinstance(raw_sources, list) else [raw_sources]
    )
    if not all(isinstance(source, (str, Path)) for source in sources):
        raise ValueError(f"Path split '{split}' tidak valid di {data_yaml}")
    sources = cast(list[str | Path], sources)
    images: set[Path] = set()
    for source in sources:
        path = Path(source)
        if not path.is_absolute():
            path = root / path
        path = path.resolve()
        if path.is_file():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    candidate = Path(line.strip())
                    images.add(
                        candidate.resolve()
                        if candidate.is_absolute()
                        else (path.parent / candidate).resolve()
                    )
        elif path.is_dir():
            images.update(
                image.resolve() for image in path.iterdir()
                if image.is_file() and image.suffix.lower() in IMAGE_EXTENSIONS
            )
        else:
            raise FileNotFoundError(f"Path split '{split}' tidak ditemukan: {path}")
    result = sorted(images)
    if not result:
        raise SystemExit(f"Tidak ada gambar di split '{split}' pada {data_yaml}")
    return result


def label_path_for_image(image: str | Path) -> Path:
    image = Path(image)
    return image.parent.parent / "labels" / f"{image.stem}.txt"


def read_ground_truth_classes(image: str | Path) -> set[int]:
    label = label_path_for_image(image)
    if not label.is_file():
        return set()
    classes: set[int] = set()
    for line in label.read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields:
            classes.add(int(float(fields[0])))
    return classes


def write_test_yaml(path: Path, split_dir: Path, names: Mapping[int, str]) -> Path:
    lines = [
        f"path: {Path(split_dir).resolve().as_posix()}",
        "train: images/test",
        "val: images/test",
        "test: images/test",
        "names:",
    ]
    lines.extend(f"  {index}: {name}" for index, name in sorted(names.items()))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def metric_summary(results: Any) -> JsonRecord:
    values: JsonRecord = {}
    for kind, metrics in (("mask", results.seg), ("box", results.box)):
        precision, recall = float(metrics.mp), float(metrics.mr)
        values.update({
            f"{kind}_p": precision,
            f"{kind}_r": recall,
            f"{kind}_f1": f1(precision, recall),
            f"{kind}_map50": float(metrics.map50),
            f"{kind}_map5095": float(metrics.map),
        })
    return values


def evaluate_total(
    model: Any,
    yaml_path: Path,
    args: argparse.Namespace,
    output_dir: Path,
    split: str,
) -> tuple[JsonRecord, list[JsonRecord]]:
    results: Any = model.val(
        data=str(yaml_path),
        split=split,
        imgsz=args.imgsz,
        batch=args.batch,
        workers=0,
        cache=False,
        device=args.device,
        plots=True,
        verbose=True,
        classes=sorted(EXPECTED_CLASSES),
        project=str((output_dir / "ultralytics").resolve()),
        name=f"total_{split}",
        exist_ok=True,
    )
    total = metric_summary(results)
    total["speed_ms_ultralytics"] = {
        key: float(value) for key, value in results.speed.items()
    }

    class_rows: list[JsonRecord] = []
    read_dataset(yaml_path)
    image_counts = getattr(results, "nt_per_image", None)
    instance_counts = getattr(results, "nt_per_class", None)
    result_indices: dict[int, int] = {
        int(class_id): index
        for index, class_id in enumerate(getattr(results, "ap_class_index", []))
    }
    for class_id, class_name in sorted(EXPECTED_CLASSES.items()):
        row: JsonRecord = {"kelas": class_name}
        result_index = result_indices.get(class_id)
        for kind, metrics in (("mask", results.seg), ("box", results.box)):
            if result_index is None:
                row.update({f"{kind}_{key}": None for key in ("p", "r", "f1", "map50", "map5095")})
            else:
                precision, recall, map50, map5095 = metrics.class_result(result_index)
                row.update({
                    f"{kind}_p": float(precision),
                    f"{kind}_r": float(recall),
                    f"{kind}_f1": f1(float(precision), float(recall)),
                    f"{kind}_map50": float(map50),
                    f"{kind}_map5095": float(map5095),
                })
        row["n_gambar"] = int(image_counts[class_id]) if image_counts is not None else ""
        row["n_instance"] = int(instance_counts[class_id]) if instance_counts is not None else ""
        class_rows.append(row)
    return total, class_rows


def variant_name(stem: str) -> str:
    return stem.split("__", 1)[1] if "__" in stem else "asli"


def evaluate_variants(
    model: Any,
    images: list[Path],
    names: Mapping[int, str],
    args: argparse.Namespace,
) -> list[JsonRecord]:
    groups: dict[str, list[Path]] = defaultdict(list)
    for image in images:
        groups[variant_name(image.stem)].append(image)

    variants = dict(sorted(groups.items()))
    originals = groups.get("asli", [])
    augmented = [image for key, group in groups.items() if key != "asli" for image in group]
    if originals and augmented:
        variants = {"ASLI": originals, "SEMUA_VARIAN": augmented, **variants}

    rows: list[JsonRecord] = []
    for variant, group in variants.items():
        if len(group) < 3:
            rows.append({
                "varian": variant,
                "n_gambar": len(group),
                "catatan": "terlalu sedikit (<3), dilewati",
            })
            continue

        with tempfile.TemporaryDirectory(prefix="vestcare_eval_") as temporary:
            temp_dir = Path(temporary)
            image_dir = temp_dir / "images" / "test"
            label_dir = temp_dir / "labels" / "test"
            image_dir.mkdir(parents=True)
            label_dir.mkdir(parents=True)
            for image in group:
                shutil.copy2(image, image_dir / image.name)
                source_label = label_path_for_image(image)
                destination_label = label_dir / source_label.name
                if source_label.is_file():
                    shutil.copy2(source_label, destination_label)
                else:
                    destination_label.write_text("", encoding="utf-8")

            yaml_path = write_test_yaml(temp_dir / "data.yaml", temp_dir, names)
            results: Any = model.val(
                data=str(yaml_path),
                split="test",
                imgsz=args.imgsz,
                batch=args.batch,
                workers=0,
                cache=False,
                device=args.device,
                plots=False,
                verbose=False,
                classes=sorted(EXPECTED_CLASSES),
                project=str(temp_dir / "runs"),
                name="evaluation",
                exist_ok=True,
            )
            rows.append({
                "varian": variant,
                "n_gambar": len(group),
                **metric_summary(results),
                "catatan": "",
            })
    return rows


def write_csv(path: Path, rows: list[JsonRecord], columns: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def analyze_image_errors(
    model: Any,
    images: list[Path],
    args: argparse.Namespace,
    output_dir: Path,
) -> JsonRecord:
    errors: list[tuple[JsonRecord, Path, Any]] = []
    correct: list[tuple[JsonRecord, Path, Any]] = []
    true_positive: defaultdict[int, int] = defaultdict(int)
    false_positive: defaultdict[int, int] = defaultdict(int)
    false_negative: defaultdict[int, int] = defaultdict(int)
    for image in images:
        actual = read_ground_truth_classes(image)
        result = model.predict(
            str(image), imgsz=args.imgsz, conf=args.conf, device=args.device,
            classes=sorted(EXPECTED_CLASSES), verbose=False
        )[0]
        predicted: set[int] = (
            set(int(class_id) for class_id in result.boxes.cls.tolist())
            if result.boxes is not None and len(result.boxes)
            else set()
        )
        missed, extra = actual - predicted, predicted - actual
        for class_id in actual & predicted:
            true_positive[class_id] += 1
        for class_id in extra:
            false_positive[class_id] += 1
        for class_id in missed:
            false_negative[class_id] += 1

        row: JsonRecord = {
            "file_gambar": image.name,
            "varian": variant_name(image.stem),
            "kelas_asli": ";".join(str(model.names[class_id]) for class_id in sorted(actual)),
            "kelas_prediksi": ";".join(str(model.names[class_id]) for class_id in sorted(predicted)),
            "terlewat": ";".join(str(model.names[class_id]) for class_id in sorted(missed)),
            "nyasar": ";".join(str(model.names[class_id]) for class_id in sorted(extra)),
        }
        (errors if missed or extra else correct).append((row, image, result))

    columns = ["file_gambar", "varian", "kelas_asli", "kelas_prediksi", "terlewat", "nyasar"]
    write_csv(output_dir / "kesalahan_gambar.csv", [row for row, _, _ in errors], columns)

    import cv2

    rng = random.Random(0)
    for folder, samples in (("salah", errors), ("benar", correct)):
        destination = output_dir / "contoh_prediksi" / folder
        destination.mkdir(parents=True, exist_ok=True)
        selected = samples if len(samples) <= args.contoh else rng.sample(samples, args.contoh)
        for _, image, result in selected:
            if not cv2.imwrite(str(destination / image.name), result.plot()):
                raise OSError(f"Gagal menyimpan contoh prediksi untuk {image}")

    per_variant_errors: defaultdict[str, int] = defaultdict(int)
    for row, _, _ in errors:
        per_variant_errors[row["varian"]] += 1

    class_ids = sorted(EXPECTED_CLASSES)
    per_class: list[JsonRecord] = []
    for class_id in class_ids:
        tp, fp, fn = (
            true_positive[class_id],
            false_positive[class_id],
            false_negative[class_id],
        )
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        tn = len(images) - tp - fp - fn
        per_class.append({
            "kelas": EXPECTED_CLASSES[class_id],
            "TP": tp,
            "FP": fp,
            "FN": fn,
            "TN": tn,
            "akurasi_gambar": (tp + tn) / len(images),
            "presisi_gambar": precision,
            "recall_gambar": recall,
            "f1_gambar": f1(precision, recall),
        })
    write_csv(
        output_dir / "tingkat_gambar_per_kelas.csv",
        per_class,
        [
            "kelas", "TP", "FP", "FN", "TN", "akurasi_gambar",
            "presisi_gambar", "recall_gambar", "f1_gambar",
        ],
    )

    tp, fp, fn = sum(true_positive.values()), sum(false_positive.values()), sum(false_negative.values())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "gambar_test": len(images),
        "salah_tingkat_gambar": len(errors),
        "akurasi_tingkat_gambar": round(1 - len(errors) / len(images), 4),
        "presisi_mikro_gambar": round(precision, 4),
        "recall_mikro_gambar": round(recall, 4),
        "f1_mikro_gambar": round(f1(precision, recall), 4),
        "f1_makro_gambar": round(statistics.fmean(row["f1_gambar"] for row in per_class), 4)
        if per_class else 0.0,
        "salah_per_varian": dict(per_variant_errors),
        "per_kelas": per_class,
    }


def measure_speed(
    model: Any,
    images: list[Path],
    args: argparse.Namespace,
) -> JsonRecord:
    sample_count = min(args.n_kecepatan, len(images))
    if sample_count < 1:
        raise ValueError("Jumlah gambar untuk pengukuran kecepatan harus lebih dari nol.")
    sample = images[:sample_count]
    for image in sample[:5]:
        model.predict(str(image), imgsz=args.imgsz, conf=args.conf, device=args.device, verbose=False)

    elapsed_ms: list[float] = []
    for image in sample:
        started = time.perf_counter()
        model.predict(str(image), imgsz=args.imgsz, conf=args.conf, device=args.device, verbose=False)
        elapsed_ms.append((time.perf_counter() - started) * 1000)
    average = statistics.fmean(elapsed_ms)
    return {
        "n_gambar": sample_count,
        "ms_rata2": round(average, 2),
        "ms_median": round(statistics.median(elapsed_ms), 2),
        "ms_maks": round(max(elapsed_ms), 2),
        "fps_rata2": round(1000 / average, 1) if average else 0.0,
        "catatan": "diukur pada perangkat ini (batch 1, termasuk pra/pasca-proses)",
    }


def save_plots(
    output_dir: Path,
    total: Mapping[str, Any],
    class_rows: list[JsonRecord],
    variant_rows: list[JsonRecord],
    image_class_rows: list[JsonRecord],
    title: str,
) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plot_dir = output_dir / "grafik"
    plot_dir.mkdir(parents=True, exist_ok=True)
    metric_names: list[tuple[str, str]] = [
        ("p", "Presisi"),
        ("r", "Recall"),
        ("f1", "F1"),
        ("map50", "mAP50"),
        ("map5095", "mAP50-95"),
    ]

    def plot_series(
        axis: Any,
        labels: list[str],
        series: Mapping[str, list[float]],
        heading: str,
    ) -> None:
        count = max(1, len(series))
        width = 0.8 / count
        for index, (name, values) in enumerate(series.items()):
            positions = [item - 0.4 + width * (index + 0.5) for item in range(len(labels))]
            axis.bar(positions, values, width, label=name)
        axis.set_xticks(range(len(labels)))
        axis.set_xticklabels(labels, rotation=30 if len(labels) > 4 else 0, ha="right")
        axis.set_ylim(0, 1.2)
        axis.set_title(heading)
        axis.grid(axis="y", alpha=0.3)
        axis.legend(fontsize=8, ncol=min(count, 5))

    names = [name for _, name in metric_names]
    fig, axis = plt.subplots(figsize=(8, 5))
    plot_series(axis, names, {
        "Mask": [total.get(f"mask_{key}", 0.0) for key, _ in metric_names],
        "Kotak": [total.get(f"box_{key}", 0.0) for key, _ in metric_names],
    }, f"Akurasi total {title}")
    fig.tight_layout()
    cast(Any, fig).savefig(plot_dir / "1_ringkasan_total.png", dpi=150)
    plt.close(fig)

    if class_rows:
        labels = [row["kelas"] for row in class_rows]
        fig, axes = plt.subplots(2, 1, figsize=(max(8, 1.3 * len(labels) + 3), 10))
        for axis, kind, label in ((axes[0], "mask", "Mask"), (axes[1], "box", "Kotak")):
            plot_series(axis, labels, {
                name: [row.get(f"{kind}_{key}") or 0.0 for row in class_rows]
                for key, name in metric_names
            }, f"Akurasi per kelas - {label}")
        fig.tight_layout()
        cast(Any, fig).savefig(plot_dir / "2_per_kelas.png", dpi=150)
        plt.close(fig)

    variant_metric_rows = [row for row in variant_rows if "mask_map5095" in row]
    if variant_metric_rows:
        labels = [f"{row['varian']} (n={row['n_gambar']})" for row in variant_metric_rows]
        fig, axis = plt.subplots(figsize=(max(8, 1.3 * len(labels) + 3), 5.5))
        plot_series(axis, labels, {
            name: [row.get(f"mask_{key}", 0.0) for row in variant_metric_rows]
            for key, name in metric_names
        }, f"Akurasi mask per varian gambar {title}")
        fig.tight_layout()
        cast(Any, fig).savefig(plot_dir / "3_per_varian.png", dpi=150)
        plt.close(fig)

    if image_class_rows:
        labels = [row["kelas"] for row in image_class_rows]
        fig, axis = plt.subplots(figsize=(max(8, 1.3 * len(labels) + 3), 5))
        plot_series(axis, labels, {
            "Presisi": [row["presisi_gambar"] for row in image_class_rows],
            "Recall": [row["recall_gambar"] for row in image_class_rows],
            "F1": [row["f1_gambar"] for row in image_class_rows],
        }, "Akurasi tingkat-gambar per kelas")
        fig.tight_layout()
        cast(Any, fig).savefig(plot_dir / "4_tingkat_gambar.png", dpi=150)
        plt.close(fig)
    print(f"Grafik disimpan di: {plot_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluasi model YOLO pada gabungan lima kelas dataset Vestcare."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "dataset_gabungan.yaml",
        help="YAML dataset gabungan (default: dataset_gabungan.yaml)",
    )
    parser.add_argument(
        "--splits-dir",
        type=Path,
        default=None,
        help="opsional: folder split_r*_s* dari pipeline lama",
    )
    parser.add_argument(
        "--hasil07",
        type=Path,
        default=ROOT / "data" / "results" / "hasil_07",
        help="folder pipeline lama yang berisi pilihan_final.json",
    )
    parser.add_argument(
        "--split",
        default=None,
        help="split val/train/test (default val), atau nama split_rXX_sYY jika memakai --splits-dir",
    )
    parser.add_argument(
        "--model",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=ROOT / "data" / "results" / "hasil_08",
    )
    parser.add_argument("--imgsz", type=int, default=512)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--contoh", type=int, default=20, help="maksimum contoh per folder salah/benar")
    parser.add_argument("--n-kecepatan", type=int, default=100)
    parser.add_argument("--device", default=None)
    args: EvalArgs = parser.parse_args(namespace=EvalArgs())

    if args.imgsz < 1 or args.batch < 1 or args.contoh < 0 or args.n_kecepatan < 1:
        raise SystemExit("--imgsz, --batch, dan --n-kecepatan harus positif; --contoh tidak boleh negatif.")

    if args.splits_dir is not None:
        split_name: Optional[str] = args.split
        if not split_name:
            selection_file = args.hasil07 / "pilihan_final.json"
            if not selection_file.is_file():
                raise SystemExit(f"{selection_file} tidak ada. Beri --split split_rXX_sYY.")
            selection_data: Any = json.loads(selection_file.read_text(encoding="utf-8"))
            if not isinstance(selection_data, dict):
                raise ValueError(f"Pilihan split tidak valid di {selection_file}")
            selection_record = cast(JsonRecord, selection_data)
            selected_split = selection_record.get("split")
            if not isinstance(selected_split, str):
                raise ValueError(f"Pilihan split tidak valid di {selection_file}")
            split_name = selected_split
        if not split_name:
            raise ValueError(f"Nama split tidak valid di {args.splits_dir}")
        split_dir = args.splits_dir / split_name
        dataset_yaml = split_dir / "data.yaml"
        eval_split = "test"
        title_split = split_name
    else:
        dataset_yaml = args.dataset
        eval_split = args.split or "val"
        title_split = eval_split
    if not dataset_yaml.is_file():
        raise SystemExit(f"Konfigurasi dataset tidak ditemukan: {dataset_yaml}")
    if eval_split not in {"train", "val", "test"}:
        raise SystemExit("--split harus salah satu: train, val, test.")

    model_candidates = [
        ROOT / "models" / "best.pt",
        ROOT / "models" / "best_semua_kelas.pt",
        ROOT / "data" / "results" / "runs" / "segment" / "runs"
        / "semua_kelas_yolo26n" / "weights" / "best.pt",
    ]
    model_path: Optional[Path] = args.model or next(
        (path for path in model_candidates if path.is_file()),
        None,
    )
    if model_path is None or not model_path.is_file():
        raise SystemExit(
            "Model tidak ditemukan. Jalankan start_train.py terlebih dahulu atau beri --model."
        )

    args.out.mkdir(parents=True, exist_ok=True)
    from ultralytics import YOLO

    names = read_dataset(dataset_yaml)[1]
    images = list_split_images(dataset_yaml, eval_split)
    log_path = args.out / f"evaluation_{datetime.now():%Y%m%d_%H%M%S}.log"
    with capture_console(log_path):
        model: Any = YOLO(str(model_path))
        model_names = _baca_kelas(model.names, model_path)
        if model_names != names:
            raise ValueError(f"Kelas model {model_names} tidak sama dengan dataset {names}.")

        print(
            f"Model: {model_path}\nDataset: {dataset_yaml}\n"
            f"Split: {title_split} | kelas: {len(names)} | gambar: {len(images)}"
        )
        print("\n[1/4] Evaluasi total dan per kelas...")
        total, class_rows = evaluate_total(model, dataset_yaml, args, args.out, eval_split)
        write_csv(
            args.out / "per_kelas.csv",
            class_rows,
            ["kelas", "n_gambar", "n_instance"] + METRIC_COLUMNS,
        )

        print("[2/4] Evaluasi per varian...")
        variant_rows = evaluate_variants(model, images, names, args)
        write_csv(
            args.out / "per_varian.csv",
            variant_rows,
            ["varian", "n_gambar"] + METRIC_COLUMNS + ["catatan"],
        )

        print("[3/4] Analisis kesalahan dan contoh prediksi...")
        errors = analyze_image_errors(model, images, args, args.out)

        print("[4/4] Mengukur kecepatan...")
        speed = measure_speed(model, images, args)
        (args.out / "kecepatan.json").write_text(
            json.dumps(speed, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        report: JsonRecord = {
            "model": str(model_path),
            "dataset": str(dataset_yaml),
            "split": title_split,
            "kelas": names,
            "total": total,
            "per_kelas": class_rows,
            "per_varian": variant_rows,
            "kesalahan": errors,
            "kecepatan": speed,
        }
        (args.out / "ringkasan_test.json").write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        lines = [
            "RINGKASAN AKURASI",
            f"Model: {model_path} | Split: {title_split} | gambar: {len(images)}",
            "",
            f"{'':<6}{'P':>8}{'R':>8}{'F1':>8}{'mAP50':>8}{'mAP50-95':>10}",
        ]
        for kind, label in (("mask", "MASK"), ("box", "KOTAK")):
            lines.append(
                f"{label:<6}{total[f'{kind}_p']:>8.4f}{total[f'{kind}_r']:>8.4f}"
                f"{total[f'{kind}_f1']:>8.4f}{total[f'{kind}_map50']:>8.4f}"
                f"{total[f'{kind}_map5095']:>10.4f}"
            )
        lines.extend([
            "",
            "METRIK DETEKSI PER KELAS (P | R | F1 | mAP50 | mAP50-95)",
        ])
        for row in class_rows:
            values: list[str] = []
            for kind in ("mask", "box"):
                values.append(
                    " | ".join(
                        f"{row[f'{kind}_{key}']:.4f}"
                        if isinstance(row[f"{kind}_{key}"], (int, float))
                        else "n/a"
                        for key in ("p", "r", "f1", "map50", "map5095")
                    )
                )
            lines.append(f"{row['kelas']:<12} mask: {values[0]} | box: {values[1]}")
        lines.extend([
            "",
            f"Akurasi tingkat-gambar (conf>={args.conf}): "
            f"{errors['akurasi_tingkat_gambar']:.4f} "
            f"({len(images) - errors['salah_tingkat_gambar']}/{len(images)} benar)",
            f"P {errors['presisi_mikro_gambar']:.4f} R {errors['recall_mikro_gambar']:.4f} "
            f"F1-mikro {errors['f1_mikro_gambar']:.4f} F1-makro {errors['f1_makro_gambar']:.4f}",
            "",
            "AKURASI TINGKAT-GAMBAR PER KELAS (TP | FP | FN | TN | akurasi | F1)",
        ])
        for row in errors["per_kelas"]:
            lines.append(
                f"{row['kelas']:<12} {row['TP']:>5} | {row['FP']:>5} | "
                f"{row['FN']:>5} | {row['TN']:>5} | {row['akurasi_gambar']:.4f} | "
                f"{row['f1_gambar']:.4f}"
            )
        lines.extend([
            "",
            f"Kecepatan: {speed['ms_rata2']} ms/gambar (~{speed['fps_rata2']} FPS)",
            f"Log lengkap: {log_path}",
        ])
        summary = "\n".join(lines)
        print("\n" + summary)
        (args.out / "laporan_akurasi.txt").write_text(summary + "\n", encoding="utf-8")
        save_plots(args.out, total, class_rows, variant_rows, errors["per_kelas"], f"- {title_split}")
        print(f"\nSemua hasil disimpan di: {args.out}")


if __name__ == "__main__":
    main()
