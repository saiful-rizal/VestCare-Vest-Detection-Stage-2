import { useEffect, useState } from "react";
import { initialState, normalizeDetections } from "./data";
import { supabase } from "./supabaseClient";

// Satu-satunya tempat data hidup. Komponen lain hanya menerima props.
export default function useVestData() {
  const [state, setState] = useState(initialState);

  useEffect(() => {
    let active = true;
    let loading = false;

    async function loadSupabaseData() {
      if (loading) return;
      loading = true;
      try {
        if (!supabase) {
          throw new Error("Konfigurasi Supabase belum lengkap. Isi VITE_SUPABASE_URL dan VITE_SUPABASE_ANON_KEY.");
        }

        const { data: devices, error: deviceError } = await supabase
          .from("devices")
          .select("id,name,student_name,school,battery,online")
          .order("last_seen", { ascending: false, nullsFirst: false })
          .limit(1);
        if (deviceError) throw new Error(`Gagal membaca tabel devices: ${deviceError.message}`);

        const device = devices[0] || null;
        let detectionsQuery = supabase
          .from("detections")
          .select("id,device_id,object,distance_m,confidence,urgency,lat,lng,urgency_score,created_at")
          .order("created_at", { ascending: false })
          .limit(20);
        let gpsQuery = supabase
          .from("gps_log")
          .select("id,device_id,lat,lng,accuracy,created_at")
          .order("created_at", { ascending: false })
          .limit(1);

        if (device) {
          detectionsQuery = detectionsQuery.eq("device_id", device.id);
          gpsQuery = gpsQuery.eq("device_id", device.id);
        }

        const [
          { data: detectionRows, error: detectionError },
          { data: gpsRows, error: gpsError },
        ] = await Promise.all([detectionsQuery, gpsQuery]);
        if (detectionError) throw new Error(`Gagal membaca tabel detections: ${detectionError.message}`);
        if (gpsError) throw new Error(`Gagal membaca tabel gps_log: ${gpsError.message}`);

        const detections = normalizeDetections(detectionRows || []);
        const gps = gpsRows[0];
        const latestDetection = detectionRows[0];
        const coordinates = gps || (latestDetection?.lat != null && latestDetection?.lng != null
          ? latestDetection
          : null);
        const position = coordinates
          ? {
            lat: Number(coordinates.lat),
            lng: Number(coordinates.lng),
            updated: new Date(coordinates.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" }),
          }
          : null;

        if (active) {
          setState((current) => ({
            ...current,
            device: device
              ? {
                online: Boolean(device.online),
                battery: device.battery == null ? null : Number(device.battery),
                name: device.name,
                studentName: device.student_name,
                school: device.school,
              }
              : initialState.device,
            position,
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
      } finally {
        loading = false;
      }
    }

    loadSupabaseData();
    const intervalId = window.setInterval(loadSupabaseData, 10000);
    return () => {
      active = false;
      window.clearInterval(intervalId);
    };
  }, []);

  return [state, setState];
}
