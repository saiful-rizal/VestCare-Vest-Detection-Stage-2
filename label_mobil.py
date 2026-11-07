"""Generate label .txt (YOLO-seg format) for dataset_mobil using COCO-seg model.

Classes mapping (COCO id -> project class id):
  COCO 0 person   -> project 3 orang
  COCO 2 car      -> project 1 mobil
  COCO 3 motorcycle -> project 2 motor

COCO tidak memiliki 'pohon' (0) dan 'lubang' (4), jadi kelas tersebut
tidak akan di-label (zero-shot, sesuai dokumentasi README).

Output:
  dataset_mobil/3_pengayaan_gerak/labels/<stem>.txt
  dataset_mobil/3_pengayaan_gerak/data.yaml
"""
from pathlib import Path
import csv

from ultralytics import YOLO

ROOT = Path(__file__).resolve().parent
IMG_DIR = ROOT / "dataset_mobil" / "3_pengayaan_gerak" / "images"
LABEL_DIR = ROOT / "dataset_mobil" / "3_pengayaan_gerak" / "labels"
YAML_PATH = ROOT / "dataset_mobil" / "3_pengayaan_gerak" / "data.yaml"

# COCO class id -> project class id
COCO_TO_PROJECT = {
    0: 3,   # person -> orang
    2: 1,   # car -> mobil
    3: 2,   # motorcycle -> motor
}

CONF = 0.25
IOU = 0.7
IMGSZ = 640
DEVICE = "cpu"  # pakai CPU agar tidak bentrok dengan training GPU yang berjalan

NAMES = {0: "pohon", 1: "mobil", 2: "motor", 3: "orang", 4: "lubang"}


def polygon_to_yoloseg(seg, orig_shape, cls_id):
    """Convert ultralytics segmentation polygon (pixels) to YOLO-seg line (normalized 0-1)."""
    h, w = orig_shape
    lines = []
    for poly in seg:
        # poly is Nx2 pixel coordinates -> normalize ke 0-1
        flat = []
        for x, y in poly:
            flat.extend([float(x) / w, float(y) / h])
        if len(flat) >= 6:  # at least 3 points
            coord_str = " ".join(f"{v:.6f}" for v in flat)
            lines.append(f"{cls_id} {coord_str}")
    return lines


def main():
    if not IMG_DIR.exists():
        raise SystemExit(f"Folder images tidak ditemukan: {IMG_DIR}")

    LABEL_DIR.mkdir(parents=True, exist_ok=True)

    exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    images = sorted(p for p in IMG_DIR.iterdir() if p.suffix.lower() in exts)
    if not images:
        raise SystemExit(f"Tidak ada gambar di {IMG_DIR}")

    print(f"[INFO] Model COCO-seg akan diunduh/dimuat (yolov8n-seg.pt)...")
    model = YOLO("yolov8n-seg.pt")

    print(f"[INFO] Melabeli {len(images)} gambar (device={DEVICE}, conf={CONF})...")
    n_labeled = 0
    n_obj_total = 0

    for img_path in images:
        results = model.predict(
            str(img_path),
            imgsz=IMGSZ,
            conf=CONF,
            iou=IOU,
            device=DEVICE,
            verbose=False,
        )
        res = results[0]

        lines = []
        if res.masks is not None and res.masks.data is not None:
            orig_shape = res.orig_shape  # (h, w)
            cls_ids = res.boxes.cls.tolist() if res.boxes is not None else []
            for i, poly in enumerate(res.masks.xy):
                coco_cls = int(cls_ids[i]) if i < len(cls_ids) else -1
                if coco_cls not in COCO_TO_PROJECT:
                    continue
                proj_cls = COCO_TO_PROJECT[coco_cls]
                for line in polygon_to_yoloseg([poly], orig_shape, proj_cls):
                    lines.append(line)
                    n_obj_total += 1

        out_txt = LABEL_DIR / f"{img_path.stem}.txt"
        out_txt.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        if lines:
            n_labeled += 1

    print(f"[INFO] Selesai. {n_labeled}/{len(images)} gambar punya minimal 1 objek.")
    print(f"[INFO] Total objek terlabel: {n_obj_total}")
    print(f"[INFO] Label disimpan di: {LABEL_DIR}")

    # Tulis data.yaml
    yaml_lines = [
        f"path: {YAML_PATH.parent.resolve().as_posix()}",
        "train: images",
        "val: images",
        "",
        "names:",
    ]
    for i in sorted(NAMES):
        yaml_lines.append(f"  {i}: {NAMES[i]}")
    YAML_PATH.write_text("\n".join(yaml_lines) + "\n", encoding="utf-8")
    print(f"[INFO] data.yaml ditulis: {YAML_PATH}")


if __name__ == "__main__":
    main()
