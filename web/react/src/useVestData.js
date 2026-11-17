import { useEffect, useState } from "react";
import { DEFAULT_MAP_CONFIG, initialState, normalizeDetections } from "./data";

// Dashboard mengambil data dari server VestCare (same-origin) agar service role
// Supabase tidak pernah masuk ke bundle browser. Telemetri Wemos didorong lewat
// Server-Sent Events agar peta bergerak seketika, dengan polling 1 detik sebagai
// cadangan bila koneksi SSE terputus (mis. di balik ngrok).
const RISK_RANK = { BAHAYA: 3, WASPADA: 2, INFO: 1, AMAN: 0 };
const MAX_TRAIL = 300;
const TELEMETRI_POLL_MS = 1000;
const DASHBOARD_POLL_MS = 10000;
const TELEMETRI_STALE_MS = 15000;

function sortByRisk(detections) {
  return [...detections].sort((a, b) => (
    (RISK_RANK[b.level] || 0) - (RISK_RANK[a.level] || 0)
    || Number(b.urgensi ?? b.urgency_score ?? 0) - Number(a.urgensi ?? a.urgency_score ?? 0)
  ));
}

function latestBatch(rows) {
  if (!rows.length) return [];
  const newest = rows[0]?.created_at;
  return newest ? rows.filter((row) => row.created_at === newest) : rows;
}

function numberOrNull(value) {
  if (value == null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function validCoordinate(lat, lng) {
  return Number.isFinite(lat) && Number.isFinite(lng)
    && lat >= -90 && lat <= 90 && lng >= -180 && lng <= 180;
}

function formatTime(value) {
  const date = value ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime())
    ? date.toLocaleTimeString("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" })
    : "";
}

function toPosition(point) {
  if (!point || point.lat == null || point.lng == null) return null;
  const lat = Number(point.lat);
  const lng = Number(point.lng);
  if (!validCoordinate(lat, lng)) return null;
  return {
    lat,
    lng,
    updated: point.updated || formatTime(point.created_at) || formatTime(point.waktu),
  };
}

function toDevice(row) {
  if (!row) return null;
  return {
    id: row.id,
    online: Boolean(row.online),
    battery: row.battery == null ? null : Number(row.battery),
    name: row.name,
    studentName: row.student_name,
    school: row.school,
    lastSeen: row.last_seen || null,
  };
}

function toTelemetry(payload) {
  if (!payload) return null;
  const source = payload.telemetri && typeof payload.telemetri === "object"
    ? payload.telemetri
    : payload;

  const lat = numberOrNull(source.lat);
  const lng = numberOrNull(source.lng);
  const updatedAt = numberOrNull(source.updated_at);
  const fix = Boolean(source.fix) && validCoordinate(lat, lng);
  const serverAge = numberOrNull(payload.umur_detik);
  const localAge = updatedAt ? Math.max(0, Date.now() / 1000 - updatedAt) : null;
  const age = serverAge ?? localAge;

  return {
    jarak: source.valid_jarak && numberOrNull(source.jarak) != null ? Number(source.jarak) : null,
    validJarak: Boolean(source.valid_jarak),
    lat: fix ? lat : null,
    lng: fix ? lng : null,
    alt: numberOrNull(source.alt),
    spd: numberOrNull(source.spd),
    sat: Number(source.sat || 0),
    hdop: numberOrNull(source.hdop),
    fix,
    terbaca: Boolean(source.terbaca),
    waktu: source.waktu || null,
    battery: numberOrNull(source.battery),
    updatedAt: updatedAt ? updatedAt * 1000 : null,
    updatedLabel: formatTime(source.updated_at ? updatedAt * 1000 : null),
    online: payload.online == null
      ? age != null && age < TELEMETRI_STALE_MS / 1000
      : Boolean(payload.online),
    age,
  };
}

function normalizeTrail(raw) {
  if (!Array.isArray(raw)) return [];
  return raw
    .map((point) => {
      const lat = numberOrNull(point?.lat);
      const lng = numberOrNull(point?.lng);
      if (!validCoordinate(lat, lng)) return null;
      return { lat, lng, waktu: point?.waktu || null };
    })
    .filter(Boolean)
    .slice(-MAX_TRAIL);
}

function appendTrail(currentTrail, serverTrail, telemetry) {
  let trail = currentTrail;
  const fromServer = normalizeTrail(serverTrail);
  if (fromServer.length && fromServer.length >= currentTrail.length) {
    trail = fromServer;
  }

  if (telemetry?.fix && validCoordinate(telemetry.lat, telemetry.lng)) {
    const last = trail[trail.length - 1];
    const moved = !last
      || Math.abs(last.lat - telemetry.lat) > 1e-6
      || Math.abs(last.lng - telemetry.lng) > 1e-6;
    if (moved) {
      trail = [...trail, {
        lat: telemetry.lat,
        lng: telemetry.lng,
        waktu: telemetry.waktu,
      }].slice(-MAX_TRAIL);
    }
  }
  return trail;
}

function readMapConfig(payload) {
  const center = payload?.map_default_center;
  const lat = numberOrNull(center?.lat);
  const lng = numberOrNull(center?.lng);
  const zoom = numberOrNull(payload?.map_zoom);
  return {
    apiKey: String(payload?.google_maps_api_key || import.meta.env.VITE_GOOGLE_MAPS_API_KEY || ""),
    center: validCoordinate(lat, lng) ? { lat, lng } : DEFAULT_MAP_CONFIG.center,
    zoom: zoom ?? DEFAULT_MAP_CONFIG.zoom,
  };
}

async function getJson(url) {
  const response = await fetch(url, {
    credentials: "same-origin",
    cache: "no-store",
    headers: { "ngrok-skip-browser-warning": "1" },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || `Server VestCare mengembalikan ${response.status}.`);
  }
  return payload;
}

function historyPosition(entry) {
  if (!entry) return null;
  if (entry.posisi && entry.posisi.lat != null && entry.posisi.lng != null) {
    return toPosition({ ...entry.posisi, updated: entry.waktu });
  }
  return toPosition(entry);
}

// Satu-satunya tempat data hidup. Komponen lain hanya menerima props.
export default function useVestData() {
  const [state, setState] = useState(initialState);

  // Konfigurasi peta (kunci Google Maps bisa diisi lewat .env server tanpa rebuild).
  useEffect(() => {
    let active = true;
    getJson("/config")
      .then((config) => {
        if (active) {
          setState((current) => ({ ...current, mapConfig: readMapConfig(config) }));
        }
      })
      .catch(() => {
        // Konfigurasi opsional; fallback ke nilai bawaan + env Vite.
        if (active) {
          setState((current) => ({
            ...current,
            mapConfig: readMapConfig({ google_maps_api_key: import.meta.env.VITE_GOOGLE_MAPS_API_KEY }),
          }));
        }
      });
    return () => { active = false; };
  }, []);

  // Telemetri realtime: SSE terlebih dahulu, lalu polling 1 detik bila gagal.
  useEffect(() => {
    let active = true;
    let source = null;
    let pollTimer = null;
    let retryTimer = null;
    let pollingEnabled = false;

    function applyPayload(payload) {
      const telemetry = toTelemetry(payload);
      if (!telemetry) return;

      setState((current) => {
        const position = telemetry.fix
          ? {
            lat: telemetry.lat,
            lng: telemetry.lng,
            updated: telemetry.waktu || formatTime(Date.now()),
          }
          : current.position;

        return {
          ...current,
          telemetry,
          telemetryOnline: telemetry.online,
          trail: appendTrail(current.trail, payload?.jalur, telemetry),
          position,
          device: {
            ...current.device,
            online: telemetry.online,
            battery: telemetry.battery ?? current.device.battery,
          },
        };
      });
    }

    function stopPolling() {
      pollingEnabled = false;
      if (pollTimer) {
        window.clearTimeout(pollTimer);
        pollTimer = null;
      }
    }

    async function pollOnce() {
      if (!active || !pollingEnabled) return;
      try {
        const payload = await getJson("/api/telemetri");
        if (active && pollingEnabled) applyPayload(payload);
      } catch {
        // Server mungkin sedang restart; coba lagi pada interval berikutnya.
      }
      if (active && pollingEnabled) pollTimer = window.setTimeout(pollOnce, TELEMETRI_POLL_MS);
    }

    function startPolling() {
      if (!active || pollingEnabled) return;
      pollingEnabled = true;
      void pollOnce();
    }

    function scheduleStreamRetry() {
      if (!active || retryTimer) return;
      retryTimer = window.setTimeout(() => {
        retryTimer = null;
        startStream();
      }, 30000);
    }

    function startStream() {
      if (!active || source) return;
      if (typeof EventSource === "undefined") {
        startPolling();
        return;
      }

      try {
        source = new EventSource("/api/telemetri/stream");
      } catch {
        startPolling();
        scheduleStreamRetry();
        return;
      }

      source.onopen = () => stopPolling();
      source.onmessage = (event) => {
        try {
          applyPayload(JSON.parse(event.data));
        } catch {
          // Abaikan pesan heartbeat/format yang tidak dikenal.
        }
      };
      source.onerror = () => {
        source?.close();
        source = null;
        startPolling();
        scheduleStreamRetry();
      };
    }

    startStream();
    startPolling();

    return () => {
      active = false;
      source?.close();
      stopPolling();
      if (retryTimer) window.clearTimeout(retryTimer);
    };
  }, []);

  // Data perangkat, deteksi, dan riwayat dari server/Supabase.
  useEffect(() => {
    let active = true;
    let loading = false;
    let timer = null;

    async function loadDashboardData() {
      if (!active || loading) return;
      loading = true;
      try {
        let dashboard = null;
        let status = null;
        try {
          dashboard = await getJson("/dashboard/data");
        } catch {
          // Supabase/server bisa sedang offline; riwayat lokal tetap ditampilkan.
          try {
            status = await getJson("/status");
          } catch {
            status = null;
          }
        }

        const device = toDevice(dashboard?.device);
        const rows = Array.isArray(dashboard?.detections) ? dashboard.detections : [];
        const dashboardPosition = dashboard && Object.prototype.hasOwnProperty.call(dashboard, "gps")
          ? toPosition(dashboard.gps)
          : toPosition(rows.find((row) => row.lat != null && row.lng != null));

        let history = null;
        let historyPositionValue = null;
        try {
          const historyPayload = await getJson("/riwayat?limit=20");
          if (Array.isArray(historyPayload.data)) {
            history = historyPayload.data.flatMap((entry) => normalizeDetections(entry)).slice(0, 20);
            historyPositionValue = historyPosition(historyPayload.data[0]);
          }
        } catch {
          history = null;
        }

        if (!active) return;
        setState((current) => {
          const telemetryFresh = current.telemetry?.fix
            && current.telemetry?.updatedAt
            && Date.now() - current.telemetry.updatedAt < TELEMETRI_STALE_MS;

          const position = telemetryFresh
            ? current.position
            : dashboardPosition || historyPositionValue || current.position;

          let nextDevice = device ? { ...current.device, ...device } : current.device;
          if (!nextDevice.id && !nextDevice.name) {
            nextDevice = {
              ...nextDevice,
              id: status?.supabase_device_id || null,
              name: "Perangkat VestCare",
              studentName: null,
              school: null,
              online: current.telemetryOnline,
            };
          }
          if (current.telemetry) {
            nextDevice = { ...nextDevice, online: current.telemetry.online };
            if (current.telemetry.battery != null) {
              nextDevice.battery = current.telemetry.battery;
            }
          }

          const detections = rows.length
            ? sortByRisk(normalizeDetections(latestBatch(rows)))
            : current.detections;
          const nextHistory = history?.length ? history : current.history;

          return {
            ...current,
            device: nextDevice,
            position,
            detections,
            history: nextHistory,
            trail: Array.isArray(dashboard?.jalur) && dashboard.jalur.length
              ? appendTrail(current.trail, dashboard.jalur, null)
              : current.trail,
            detectionHistoryLoading: false,
            detectionHistoryError: null,
          };
        });
      } catch (error) {
        if (active) {
          setState((current) => ({
            ...current,
            detectionHistoryLoading: false,
            detectionHistoryError: error instanceof Error
              ? error.message
              : "Gagal memuat riwayat deteksi.",
          }));
        }
      } finally {
        loading = false;
        if (active) timer = window.setTimeout(loadDashboardData, DASHBOARD_POLL_MS);
      }
    }

    void loadDashboardData();

    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, []);

  return [state, setState];
}
