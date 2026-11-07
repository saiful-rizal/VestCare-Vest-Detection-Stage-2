import argparse
import math
from pathlib import Path

import cv2
from ultralytics import YOLO

from fuzzysugeno import analisis_hasil


def sumber_video(value):
    return int(value) if value.isdigit() else value


TINGGI_REFERENSI_M = {
    "pohon": 2.0,
    "lubang": 0.4,
    "orang": 1.7,
    "motor": 1.2,
    "mobil": 1.5,
}


def estimasi_jarak(box_xyxy, nama, tinggi_gambar, fov_vertikal, jarak_maks):
    """Estimasi jarak monocular; wajib dikalibrasi untuk hasil meter yang akurat."""
    tinggi_box = max(1.0, float(box_xyxy[3]) - float(box_xyxy[1]))
    focal_px = tinggi_gambar / (2.0 * math.tan(math.radians(fov_vertikal) / 2.0))
    tinggi_objek = TINGGI_REFERENSI_M.get(nama, 1.5)
    jarak = focal_px * tinggi_objek / tinggi_box
    return max(0.2, min(jarak_maks, jarak))


def gambar_box_rapat(res, conf_min):
    frame = res.orig_img.copy()
    masks = res.masks.xy if res.masks is not None else []
    for i, box in enumerate(res.boxes):
        conf = float(box.conf)
        if conf < conf_min:
            continue
        kelas_id = int(box.cls)
        nama = res.names[kelas_id]
        warna = (
            int((kelas_id * 67 + 80) % 255),
            int((kelas_id * 113 + 120) % 255),
            int((kelas_id * 173 + 160) % 255),
        )
        if i < len(masks) and len(masks[i]) >= 3:
            polygon = masks[i].astype("int32")
            x, y, lebar, tinggi = cv2.boundingRect(polygon)
            overlay = frame.copy()
            cv2.fillPoly(overlay, [polygon], warna)
            frame = cv2.addWeighted(overlay, 0.18, frame, 0.82, 0)
        else:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            x, y = round(x1), round(y1)
            lebar, tinggi = round(x2 - x1), round(y2 - y1)
        cv2.rectangle(frame, (x, y), (x + lebar, y + tinggi), warna, 2)
        cv2.putText(frame, f"{nama} {conf:.2f}", (x, max(20, y - 6)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, warna, 2, cv2.LINE_AA)
    return frame


def main():
    ap = argparse.ArgumentParser(description="YOLO-seg + Fuzzy Sugeno")
    ap.add_argument("--model", type=Path, default=Path("models") / "best.pt")
    ap.add_argument("--source", default="0", help="0 untuk webcam, atau path gambar/video")
    ap.add_argument("--conf", type=float, default=0.60,
                    help="confidence minimum YOLO sebelum diteruskan ke fuzzy")
    ap.add_argument("--jarak", type=float, default=None,
                    help="override jarak tetap dalam meter; tanpa opsi ini memakai estimasi bounding box")
    ap.add_argument("--fov-vertikal", type=float, default=60.0,
                    help="field of view vertikal kamera untuk estimasi jarak")
    ap.add_argument("--jarak-maks", type=float, default=2.0,
                    help="batas maksimum estimasi jarak dalam meter")
    args = ap.parse_args()

    if not args.model.exists():
        raise SystemExit(f"Model tidak ditemukan: {args.model}")

    model = YOLO(str(args.model))
    kelas_model = set(model.names.values())
    kelas_fuzzy = {"pohon", "lubang", "orang", "motor", "mobil"}
    kelas_tidak_didukung = kelas_model - kelas_fuzzy
    if kelas_tidak_didukung:
        raise SystemExit(
            "Kelas model tidak sesuai dataset fuzzy: "
            + ", ".join(sorted(kelas_tidak_didukung))
        )
    source = sumber_video(args.source)
    hasil = model.predict(source=source, imgsz=416, conf=args.conf, stream=True, verbose=False)

    for res in hasil:
        analisis = analisis_hasil(
            res,
            jarak_fn=(
                (lambda box, nama: args.jarak)
                if args.jarak is not None
                else (lambda box, nama: estimasi_jarak(
                    box, nama, res.orig_shape[0], args.fov_vertikal, args.jarak_maks))
            ),
            conf_min=args.conf,
        )
        frame = gambar_box_rapat(res, args.conf)
        if not analisis:
            cv2.putText(frame, "Tidak ada deteksi yang memenuhi confidence",
                        (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.65,
                        (180, 180, 180), 2, cv2.LINE_AA)
        for i, item in enumerate(analisis):
            teks = (f"{item['kelas']} {item['conf']:.2f} -> {item['level']} "
                    f"{item['urgensi']:.1f} | {item['jarak_m']:.1f} m")
            cv2.putText(frame, teks, (10, 30 + i * 28), cv2.FONT_HERSHEY_SIMPLEX,
                        0.65, (0, 0, 255) if item["urgensi"] >= 75 else (0, 200, 255),
                        2, cv2.LINE_AA)
            print(item["pesan"])
        cv2.imshow("YOLO + Fuzzy Sugeno", frame)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
