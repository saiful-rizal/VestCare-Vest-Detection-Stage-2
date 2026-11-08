// Warna & helper yang dipakai banyak komponen
export const COLOR = { Tinggi: "#c8281c", Sedang: "#d98a0b", Rendah: "#1f8a5b" };
export const ICON = {
  Lubang: "ni-support-16",
  Mobil: "ni-delivery-fast",
  Motor: "ni-bus-front-12",
  Orang: "ni-satisfied",
  Pohon: "ni-world-2",
};
export const fmt = (n) => Number(n).toFixed(1).replace(".", ",");

export const profile = {
  nama: "Nama Siswa",
  sekolah: "SLBN Branjangan, Jember",
  perangkat: "Vest-Care (ESP32-S3)",
};

/* DATA CONTOH. Ganti dengan data dari Supabase di hook useVestData (src/useVestData.js). */
export const initialState = {
  device: { online: false, battery: null, name: null, studentName: null, school: null },
  position: null,
  detections: [],
  history: [],
  detectionHistoryLoading: true,
  detectionHistoryError: null,
};

export function normalizeDetections(payload) {
  const items = Array.isArray(payload)
    ? payload
    : payload?.deteksi || payload?.detections || payload?.predictions || payload?.data;

  if (!Array.isArray(items)) {
    throw new Error("Respons server tidak berisi daftar deteksi yang valid.");
  }

  const urgencyLabels = { BAHAYA: "Tinggi", WASPADA: "Sedang", INFO: "Rendah", AMAN: "Rendah" };
  const time = payload?.waktu || new Date().toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" });

  return items.filter((item) => !item.ragu).map((item) => {
    const confidence = Number(item.confidence ?? item.score ?? item.conf ?? 0);
    const className = item.object || item.class || item.label || item.kelas;
    const level = String(item.level ?? item.urgency ?? "").toUpperCase();
    const rawUrgency = item.urgency;
    const urgencyLabels = { BAHAYA: "Tinggi", WASPADA: "Sedang", INFO: "Rendah", AMAN: "Rendah" };
    const createdAt = item.created_at ? new Date(item.created_at) : null;
    const detectionTime = createdAt && !Number.isNaN(createdAt.getTime())
      ? createdAt.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit" })
      : time;

    return {
      ...item,
      object: className ? className[0].toUpperCase() + className.slice(1) : "Tidak dikenal",
      confidence: Number.isFinite(confidence) && confidence <= 1 ? confidence * 100 : confidence,
      distance: Number(item.distance ?? item.distance_m ?? item.jarak_m ?? 0) || 0,
      level,
      urgency: urgencyLabels[level] || (["Tinggi", "Sedang", "Rendah"].includes(rawUrgency) ? rawUrgency : "Sedang"),
      time: item.time || detectionTime,
    };
  });
}
