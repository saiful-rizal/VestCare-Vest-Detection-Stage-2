import { useEffect, useState } from "react";
import { initialState, normalizeDetections } from "./data";

// Satu-satunya tempat data hidup. Komponen lain hanya menerima props.
export default function useVestData() {
  const [state, setState] = useState(initialState);

  useEffect(() => {
    let active = true;

    async function loadLatestDetection() {
      try {
        const response = await fetch("/riwayat?limit=1");
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || `Server riwayat mengembalikan ${response.status}.`);
        }
        if (!Array.isArray(payload.data)) {
          throw new Error("Respons riwayat server tidak valid.");
        }

        const latest = payload.data[0];
        const detections = latest ? normalizeDetections(latest) : [];
        if (active) {
          setState((current) => ({
            ...current,
            detections,
            detectionHistoryLoading: false,
            detectionHistoryError: null,
          }));
        }
      } catch (error) {
        if (active) {
          setState((current) => ({
            ...current,
            detectionHistoryLoading: false,
            detectionHistoryError: error instanceof Error ? error.message : "Gagal memuat riwayat deteksi.",
          }));
        }
      }
    }

    loadLatestDetection();
    return () => { active = false; };
  }, []);

  return [state, setState];
}
