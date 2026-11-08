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

        if (!device) {
          const statusResponse = await fetch("/status", { credentials: "same-origin" });
          const statusPayload = await statusResponse.json();
          if (!statusResponse.ok) {
            throw new Error(statusPayload.detail || `Server VestCare mengembalikan ${statusResponse.status}.`);
          }

          let serverData = null;
          if (statusPayload.supabase_sinkronisasi_aktif && statusPayload.supabase_device_id) {
            const response = await fetch("/dashboard/data", { credentials: "same-origin" });
            serverData = await response.json();
            if (!response.ok) {
              throw new Error(serverData.detail || `Dashboard Supabase mengembalikan ${response.status}.`);
            }
          }
          const serverDetections = serverData?.detections || [];

          let latestDetections;
          let history;
          let serverPosition = null;
          const gps = serverData?.gps;
          const detectionWithLocation = serverDetections.find((item) => item.lat != null && item.lng != null);
          const coordinates = gps || detectionWithLocation;
          if (coordinates) {
            serverPosition = {
              lat: Number(coordinates.lat),
              lng: Number(coordinates.lng),
              updated: coordinates.created_at
                ? new Date(coordinates.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
                : "",
            };
          }

          if (serverDetections.length) {
            const latestTimestamp = serverDetections[0].created_at;
            const latestRows = serverDetections.filter((item) => item.created_at === latestTimestamp);
            latestDetections = normalizeDetections(latestRows).sort((a, b) => {
              const rank = { BAHAYA: 3, WASPADA: 2, INFO: 1, AMAN: 0 };
              return (rank[b.level] || 0) - (rank[a.level] || 0)
                || Number(b.urgensi ?? b.urgency_score ?? 0) - Number(a.urgensi ?? a.urgency_score ?? 0);
            });
            history = normalizeDetections(serverDetections).slice(0, 20);
          } else {
            const historyResponse = await fetch("/riwayat?limit=20", { credentials: "same-origin" });
            const historyPayload = await historyResponse.json();
            if (!historyResponse.ok) {
              throw new Error(historyPayload.detail || `Riwayat server mengembalikan ${historyResponse.status}.`);
            }
            if (!Array.isArray(historyPayload.data)) {
              throw new Error("Respons riwayat server tidak valid.");
            }

            const latest = historyPayload.data[0];
            latestDetections = latest ? normalizeDetections(latest) : [];
            history = historyPayload.data.flatMap((entry) => normalizeDetections(entry));
            serverPosition = latest?.lat != null && latest?.lng != null
              ? {
                lat: Number(latest.lat),
                lng: Number(latest.lng),
                updated: latest.waktu || "",
              }
              : null;
          }

          if (active) {
            setState((current) => ({
              ...current,
              device: serverData?.device
                ? {
                  id: serverData.device.id,
                  online: Boolean(serverData.device.online),
                  battery: serverData.device.battery == null ? null : Number(serverData.device.battery),
                  name: serverData.device.name,
                  studentName: serverData.device.student_name,
                  school: serverData.device.school,
                }
                : {
                  id: statusPayload.supabase_device_id || null,
                  online: Boolean(statusPayload.engine_siap),
                  battery: null,
                  name: "Perangkat Sementara (Server)",
                  studentName: null,
                  school: null,
                },
              position: serverPosition,
              detections: latestDetections,
              history: history.slice(0, 20),
              detectionHistoryLoading: false,
              detectionHistoryError: null,
            }));
          }
          return;
        }

        let detectionsQuery = supabase
          .from("detections")
          .select("id,device_id,object,distance_m,confidence,urgency,lat,lng,urgency_score,created_at")
          .order("created_at", { ascending: false })
          .order("urgency_score", { ascending: false })
          .limit(100);
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

        const history = normalizeDetections(detectionRows || []);
        const newestTimestamp = detectionRows[0]?.created_at;
        const latestRows = newestTimestamp
          ? detectionRows.filter((item) => item.created_at === newestTimestamp)
          : [];
        const detections = normalizeDetections(latestRows).sort((a, b) => {
          const rank = { BAHAYA: 3, WASPADA: 2, INFO: 1, AMAN: 0 };
          return (rank[b.level] || 0) - (rank[a.level] || 0)
            || Number(b.urgensi ?? b.urgency_score ?? 0) - Number(a.urgensi ?? a.urgency_score ?? 0);
        });
        const gps = gpsRows[0];
        const latestDetection = detectionRows[0];
        const coordinates = gps || (latestDetection?.lat != null && latestDetection?.lng != null
          ? latestDetection
          : null);
        const position = coordinates
          ? {
            lat: Number(coordinates.lat),
            lng: Number(coordinates.lng),
            updated: coordinates.created_at
              ? new Date(coordinates.created_at).toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
              : "",
          }
          : null;

        if (active) {
          setState((current) => ({
            ...current,
            device: device
              ? {
                id: device.id,
                online: Boolean(device.online),
                battery: device.battery == null ? null : Number(device.battery),
                name: device.name,
                studentName: device.student_name,
                school: device.school,
              }
              : initialState.device,
            position,
            detections,
            history: history.slice(0, 20),
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
