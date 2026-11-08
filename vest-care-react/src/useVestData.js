import { useCallback, useEffect, useRef, useState } from "react";
import { initialState, normalizeDetections } from "./data";
import { supabase } from "./supabaseClient";

// Satu-satunya tempat data hidup. Komponen lain hanya menerima props.
export default function useVestData() {
  const [state, setState] = useState(initialState);
  const deviceIdRef = useRef(null);
  const positionRef = useRef(null);
  const lastSavedSignatureRef = useRef("");
  const lastSavedAtRef = useRef(0);

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
        deviceIdRef.current = device?.id || null;
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
        positionRef.current = position;

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

  const saveDetections = useCallback(async (detections) => {
    if (!detections.length) {
      lastSavedSignatureRef.current = "";
      return;
    }

    if (!supabase) {
      throw new Error("Konfigurasi Supabase belum lengkap.");
    }

    let deviceId = deviceIdRef.current;
    if (!deviceId) {
      const { data: devices, error } = await supabase
        .from("devices")
        .select("id")
        .order("last_seen", { ascending: false, nullsFirst: false })
        .limit(1);
      if (error) throw new Error(`Gagal mencari perangkat di Supabase: ${error.message}`);
      deviceId = devices[0]?.id || null;
      deviceIdRef.current = deviceId;
    }
    if (!deviceId) {
      throw new Error("Tidak ada perangkat yang dapat diakses di tabel devices; data deteksi belum dikirim.");
    }

    const signature = detections
      .map((item) => `${item.object}:${item.level}:${item.arah || ""}`)
      .sort()
      .join("|");
    const now = Date.now();
    if (signature === lastSavedSignatureRef.current && now - lastSavedAtRef.current < 10000) return;

    const position = positionRef.current;
    const rows = detections.map((item) => ({
      device_id: deviceId,
      object: item.object,
      distance_m: Number(item.distance) || 0,
      confidence: Number(item.confidence) / 100 || 0,
      urgency: item.level || "INFO",
      urgency_score: Number(item.urgensi ?? item.urgency_score) || 0,
      lat: position?.lat ?? null,
      lng: position?.lng ?? null,
    }));

    const { error } = await supabase.from("detections").insert(rows);
    if (error) {
      throw new Error(`Gagal menyimpan deteksi ke Supabase: ${error.message}`);
    }

    lastSavedSignatureRef.current = signature;
    lastSavedAtRef.current = now;
  }, []);

  return [state, setState, saveDetections];
}
