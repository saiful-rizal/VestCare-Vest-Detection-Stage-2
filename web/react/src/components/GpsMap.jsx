import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { COLOR, DEFAULT_MAP_CONFIG } from "../data";

const MAP_HEIGHT = 380;
const MAX_DETECTION_MARKERS = 12;
const DETECTION_COLORS = {
  Tinggi: COLOR.Tinggi,
  Sedang: COLOR.Sedang,
  Rendah: COLOR.Rendah,
};

let googleMapsPromise = null;
let googleMapsKey = "";

function loadGoogleMaps(apiKey) {
  if (window.google?.maps) return Promise.resolve(window.google.maps);
  if (!apiKey) return Promise.reject(new Error("Kunci Google Maps belum diatur."));
  if (googleMapsPromise && googleMapsKey === apiKey) return googleMapsPromise;

  googleMapsKey = apiKey;
  googleMapsPromise = new Promise((resolve, reject) => {
    const callbackName = `__vestcareMapsReady_${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const bersihkanCallback = () => { delete window[callbackName]; };
    const selesai = () => {
      bersihkanCallback();
      window.google?.maps
        ? resolve(window.google.maps)
        : reject(new Error("Google Maps tidak siap."));
    };

    const existing = document.querySelector("script[data-vestcare-google-maps]");
    if (existing) {
      existing.addEventListener("load", selesai, { once: true });
      existing.addEventListener("error", () => {
        bersihkanCallback();
        reject(new Error("Gagal memuat Google Maps."));
      }, { once: true });
      return;
    }

    window[callbackName] = selesai;

    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&language=id&region=ID&callback=${callbackName}`;
    script.async = true;
    script.defer = true;
    script.dataset.vestcareGoogleMaps = "1";
    script.onerror = () => {
      bersihkanCallback();
      script.remove();
      reject(new Error("Gagal memuat Google Maps. Periksa koneksi internet."));
    };
    document.head.appendChild(script);
  }).catch((error) => {
    googleMapsPromise = null;
    throw error;
  });

  return googleMapsPromise;
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (character) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[character]);
}

function formatNumber(value, digits = 1) {
  return value == null || Number.isNaN(Number(value)) ? "-" : Number(value).toFixed(digits).replace(".", ",");
}

function accuracyRadius(hdop) {
  const value = Number(hdop);
  return Number.isFinite(value) && value > 0 ? Math.max(6, Math.min(60, value * 5)) : 8;
}

function vestMarkerIcon(maps) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="44" height="52" viewBox="0 0 44 52">
    <path d="M22 1C10.4 1 1 10.4 1 22c0 15 21 29 21 29s21-14 21-29C43 10.4 33.6 1 22 1z" fill="#8f1006" stroke="#ffffff" stroke-width="3"/>
    <circle cx="22" cy="22" r="7" fill="#ffffff"/>
  </svg>`;
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    scaledSize: new maps.Size(44, 52),
    anchor: new maps.Point(22, 50),
  };
}

function buildVestInfo(position, telemetry) {
  if (!position) {
    return `<div style="font-family:system-ui,sans-serif;font-size:13px;color:#4a201b;min-width:190px">
      <strong>Menunggu GPS fix</strong><br/>Rompi belum mengirim koordinat valid.
    </div>`;
  }

  const rows = [
    ["Koordinat", `${position.lat.toFixed(6)}, ${position.lng.toFixed(6)}`],
    ["Jarak sensor", telemetry?.jarak == null ? "-" : `${formatNumber(telemetry.jarak, 2)} m`],
    ["Kecepatan", telemetry?.spd == null ? "-" : `${formatNumber(telemetry.spd)} km/jam`],
    ["Satelit", telemetry?.sat == null ? "-" : telemetry.sat],
    ["HDOP", telemetry?.hdop == null ? "-" : formatNumber(telemetry.hdop)],
    ["Waktu GPS", `${telemetry?.waktu || "-"} WIB`],
  ];

  return `<div style="font-family:system-ui,sans-serif;font-size:13px;color:#4a201b;min-width:210px">
    <div style="font-weight:700;margin-bottom:6px;color:#8f1006">Posisi rompi (Wemos)</div>
    ${rows.map(([label, value]) => `<div style="display:flex;justify-content:space-between;gap:14px;padding:2px 0">
      <span style="color:#7a6460">${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong>
    </div>`).join("")}
  </div>`;
}

function buildDetectionInfo(detection) {
  return `<div style="font-family:system-ui,sans-serif;font-size:13px;color:#4a201b;min-width:170px">
    <div style="font-weight:700;margin-bottom:6px;color:${DETECTION_COLORS[detection.urgency] || COLOR.Sedang}">
      ${escapeHtml(detection.object)} - ${escapeHtml(detection.level || detection.urgency)}
    </div>
    <div style="display:flex;justify-content:space-between;gap:14px;padding:2px 0">
      <span style="color:#7a6460">Jarak</span><strong>${formatNumber(detection.distance, 1)} m</strong>
    </div>
    <div style="display:flex;justify-content:space-between;gap:14px;padding:2px 0">
      <span style="color:#7a6460">Arah</span><strong>${escapeHtml(detection.arah || "-")}</strong>
    </div>
    <div style="display:flex;justify-content:space-between;gap:14px;padding:2px 0">
      <span style="color:#7a6460">Confidence</span><strong>${Math.round(detection.confidence || 0)}%</strong>
    </div>
    <div style="margin-top:6px;color:#7a6460;font-size:11px">Posisi perkiraan dari arah &amp; jarak sensor.</div>
  </div>`;
}

// Objek hasil deteksi tidak membawa koordinat sendiri. Bila belum ada lat/lng,
// posisinya diperkirakan dari arah (kiri/depan/kanan) dan jarak terhadap rompi.
function detectionPoint(detection, origin, index) {
  const lat = Number(detection.lat);
  const lng = Number(detection.lng);
  if (Number.isFinite(lat) && Number.isFinite(lng) && Math.abs(lat) <= 90 && Math.abs(lng) <= 180) {
    return { lat, lng };
  }
  if (!origin) return null;

  const distance = Math.max(0.4, Math.min(Number(detection.distance) || 1.5, 25));
  const direction = { kiri: -55, kanan: 55, depan: 0 }[detection.arah] ?? 0;
  const jitter = ((index % 3) - 1) * 7;
  const bearing = ((direction + jitter) * Math.PI) / 180;
  const dLat = (distance * Math.cos(bearing)) / 111320;
  const dLng = (distance * Math.sin(bearing)) / (111320 * Math.cos((origin.lat * Math.PI) / 180));
  return { lat: origin.lat + dLat, lng: origin.lng + dLng };
}

function GoogleMapCanvas({
  apiKey,
  position,
  telemetry,
  detections,
  trail,
  defaultCenter,
  defaultZoom,
  follow,
  onManualMove,
  onError,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const markerRef = useRef(null);
  const circleRef = useRef(null);
  const trailRef = useRef(null);
  const infoRef = useRef(null);
  const detectionInfoRef = useRef(null);
  const detectionMarkersRef = useRef([]);
  const positionRef = useRef(position);
  const telemetryRef = useRef(telemetry);
  const onErrorRef = useRef(onError);
  const onManualMoveRef = useRef(onManualMove);
  const [ready, setReady] = useState(false);

  useEffect(() => { positionRef.current = position; }, [position]);
  useEffect(() => { telemetryRef.current = telemetry; }, [telemetry]);
  useEffect(() => { onErrorRef.current = onError; }, [onError]);
  useEffect(() => { onManualMoveRef.current = onManualMove; }, [onManualMove]);

  useEffect(() => {
    let cancelled = false;
    const container = containerRef.current;
    if (!container) return undefined;

    const handleAuthFailure = () => {
      onErrorRef.current?.("Kunci Google Maps ditolak. Periksa pembatasan API key atau tagihan Google Cloud.");
    };
    window.gm_authFailure = handleAuthFailure;

    loadGoogleMaps(apiKey)
      .then((maps) => {
        if (cancelled || !containerRef.current) return;
        const center = positionRef.current || defaultCenter;

        const map = new maps.Map(containerRef.current, {
          center: { lat: center.lat, lng: center.lng },
          zoom: defaultZoom,
          mapTypeControl: false,
          streetViewControl: false,
          fullscreenControl: true,
          gestureHandling: "greedy",
          clickableIcons: false,
        });
        mapRef.current = map;

        markerRef.current = new maps.Marker({
          map,
          position: { lat: center.lat, lng: center.lng },
          title: "Posisi rompi VestCare",
          icon: vestMarkerIcon(maps),
          visible: false,
          zIndex: 500,
        });
        circleRef.current = new maps.Circle({
          map,
          center: { lat: center.lat, lng: center.lng },
          radius: 8,
          visible: false,
          strokeColor: "#8f1006",
          strokeOpacity: 0.4,
          strokeWeight: 1,
          fillColor: "#8f1006",
          fillOpacity: 0.08,
        });
        trailRef.current = new maps.Polyline({
          map,
          path: [],
          geodesic: true,
          strokeColor: "#8f1006",
          strokeOpacity: 0.85,
          strokeWeight: 4,
        });
        infoRef.current = new maps.InfoWindow();
        detectionInfoRef.current = new maps.InfoWindow();

        markerRef.current.addListener("click", () => {
          infoRef.current?.setContent(buildVestInfo(positionRef.current, telemetryRef.current));
          infoRef.current?.open({ map, anchor: markerRef.current });
        });
        map.addListener("dragstart", () => onManualMoveRef.current?.());
        setReady(true);
      })
      .catch((error) => {
        if (!cancelled) onErrorRef.current?.(error instanceof Error ? error.message : "Gagal memuat Google Maps.");
      });

    return () => {
      cancelled = true;
      if (window.gm_authFailure === handleAuthFailure) delete window.gm_authFailure;
      detectionMarkersRef.current.forEach((marker) => marker.setMap(null));
      detectionMarkersRef.current = [];
      detectionInfoRef.current?.close();
      infoRef.current?.close();
      mapRef.current = null;
      markerRef.current = null;
      circleRef.current = null;
      trailRef.current = null;
      infoRef.current = null;
      detectionInfoRef.current = null;
      setReady(false);
    };
    // Peta dibuat ulang hanya bila kunci atau titik pusat bawaan berubah.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiKey, defaultCenter.lat, defaultCenter.lng, defaultZoom]);

  const infoHtml = useMemo(() => buildVestInfo(position, telemetry), [position, telemetry]);

  useEffect(() => {
    if (!ready) return;
    infoRef.current?.setContent(infoHtml);
  }, [ready, infoHtml]);

  useEffect(() => {
    if (!ready || !position) return;
    const point = { lat: position.lat, lng: position.lng };
    markerRef.current?.setPosition(point);
    markerRef.current?.setVisible(true);
    circleRef.current?.setCenter(point);
    circleRef.current?.setRadius(accuracyRadius(telemetry?.hdop));
    circleRef.current?.setVisible(true);

    if (follow) {
      const map = mapRef.current;
      const center = map?.getCenter();
      const moved = !center
        || Math.abs(center.lat() - position.lat) > 1e-6
        || Math.abs(center.lng() - position.lng) > 1e-6;
      if (moved) map?.panTo(point);
    }
  }, [ready, follow, position, telemetry?.hdop]);

  useEffect(() => {
    if (!ready || !trailRef.current) return;
    trailRef.current.setPath(trail.map((point) => ({ lat: point.lat, lng: point.lng })));
  }, [ready, trail]);

  useEffect(() => {
    if (!ready) return undefined;
    const maps = window.google?.maps;
    const map = mapRef.current;
    if (!maps || !map) return undefined;

    detectionMarkersRef.current.forEach((marker) => marker.setMap(null));
    detectionMarkersRef.current = [];

    detections.slice(0, MAX_DETECTION_MARKERS).forEach((detection, index) => {
      const point = detectionPoint(detection, position, index);
      if (!point) return;
      const color = DETECTION_COLORS[detection.urgency] || COLOR.Sedang;
      const marker = new maps.Marker({
        map,
        position: point,
        title: `${detection.object} - ${detection.level || detection.urgency}`,
        icon: {
          path: maps.SymbolPath.CIRCLE,
          scale: 8,
          fillColor: color,
          fillOpacity: 1,
          strokeColor: "#ffffff",
          strokeWeight: 2,
        },
        zIndex: 100 + index,
      });
      marker.addListener("click", () => {
        detectionInfoRef.current.setContent(buildDetectionInfo(detection));
        detectionInfoRef.current.open({ map, anchor: marker });
      });
      detectionMarkersRef.current.push(marker);
    });

    return () => {
      detectionMarkersRef.current.forEach((marker) => marker.setMap(null));
      detectionMarkersRef.current = [];
    };
  }, [ready, detections, position]);

  return <div ref={containerRef} style={{ height: MAP_HEIGHT, width: "100%", borderRadius: 12 }} />;
}

function GoogleMapEmbed({ position, defaultCenter, zoom }) {
  const center = position || defaultCenter;
  // Bulatkan ~11 m agar iframe tidak dimuat ulang setiap kali GPS bergeser sedikit.
  const key = `${center.lat.toFixed(4)},${center.lng.toFixed(4)},${zoom}`;
  const src = `https://maps.google.com/maps?q=${center.lat},${center.lng}&z=${zoom}&hl=id&t=m&output=embed`;

  return (
    <div className="relative overflow-hidden rounded-xl" style={{ height: MAP_HEIGHT }}>
      <iframe
        key={key}
        title="Google Maps - posisi rompi VestCare"
        src={src}
        className="h-full w-full border-0"
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
        allowFullScreen
      />
      <span className="pointer-events-none absolute left-3 top-3 rounded-full bg-white/90 px-3 py-1 text-[11px] font-semibold text-slate-700 shadow">
        Google Maps · mode embed
      </span>
    </div>
  );
}

function StatusPill({ tone, children }) {
  const tones = {
    ok: "bg-emerald-50 text-emerald-700 border-emerald-200",
    warn: "bg-amber-50 text-amber-700 border-amber-200",
    bad: "bg-red-50 text-red-700 border-red-200",
    idle: "bg-slate-50 text-slate-500 border-slate-200",
  };
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-semibold ${tones[tone] || tones.idle}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {children}
    </span>
  );
}

function Metric({ label, value, sub, color, icon }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-slate-50/70 px-3 py-2">
      <div className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
        {icon && <i className={`ni ${icon} text-xs`} style={{ color: color || "#660f08" }} />}
        {label}
      </div>
      <div className="mt-0.5 text-base font-bold" style={{ color: color || "#2a1412" }}>{value}</div>
      {sub && <div className="text-[10px] leading-tight text-slate-500">{sub}</div>}
    </div>
  );
}

export default function GpsMap({ position, detections = [], telemetry, trail = [], mapConfig }) {
  const config = mapConfig || DEFAULT_MAP_CONFIG;
  const [follow, setFollow] = useState(true);
  const [mapError, setMapError] = useState("");
  const [now, setNow] = useState(Date.now());

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => { setMapError(""); }, [config.apiKey]);

  const handleMapError = useCallback((message) => {
    setMapError(message);
    setFollow(true);
  }, []);

  const gpsTone = telemetry?.fix ? "ok" : telemetry?.terbaca ? "warn" : telemetry?.updatedAt ? "bad" : "idle";
  const gpsLabel = telemetry?.fix
    ? "GPS fix"
    : telemetry?.terbaca
      ? "Mencari satelit"
      : telemetry?.updatedAt
        ? "GPS tidak terbaca"
        : "Menunggu telemetri";
  const hasTelemetry = Boolean(telemetry?.updatedAt || telemetry?.fix || telemetry?.terbaca);
  const wemosTone = telemetry?.online ? "ok" : hasTelemetry ? "bad" : "idle";
  const wemosLabel = telemetry?.online ? "Wemos online" : hasTelemetry ? "Wemos offline" : "Wemos belum kirim";

  const ageSeconds = telemetry?.updatedAt
    ? Math.max(0, Math.round((now - telemetry.updatedAt) / 1000))
    : null;
  const ageLabel = ageSeconds == null
    ? "-"
    : ageSeconds <= 2
      ? "baru saja"
      : `${ageSeconds} detik lalu`;

  const distance = telemetry?.jarak;
  const distanceColor = distance == null
    ? "#7a6460"
    : distance < 1
      ? COLOR.Tinggi
      : distance < 2
        ? COLOR.Sedang
        : COLOR.Rendah;
  const distancePercent = distance == null ? 0 : Math.min(100, (distance / 4) * 100);
  const hasApproxDetection = detections.some((item) => item.lat == null || item.lng == null);
  const mapsUrl = position
    ? `https://www.google.com/maps/search/?api=1&query=${position.lat},${position.lng}`
    : null;
  const directionsUrl = position
    ? `https://www.google.com/maps/dir/?api=1&destination=${position.lat},${position.lng}&travelmode=walking`
    : null;
  const useEmbed = !config.apiKey || Boolean(mapError);

  return (
    <div className="w-full max-w-full px-3 mt-0 lg:w-7/12 lg:flex-none">
      <div className="border-black/12.5 dark:bg-slate-850 dark:shadow-dark-xl shadow-xl relative z-20 flex min-w-0 flex-col break-words rounded-2xl border-0 border-solid bg-white bg-clip-border">
        <div className="border-black/12.5 mb-0 rounded-t-2xl border-b-0 border-solid p-6 pb-2">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h6 className="mb-1 capitalize dark:text-white">Lokasi GPS realtime</h6>
              <p className="mb-0 text-sm leading-normal dark:text-white dark:opacity-60">
                <i className="ni ni-square-pin" style={{ color: "#660f08" }}></i>{" "}
                <span className="font-semibold">
                  {position
                    ? `${position.lat.toFixed(6)}, ${position.lng.toFixed(6)}${position.updated ? ` · ${position.updated}` : ""}`
                    : hasTelemetry
                      ? "Menunggu GPS fix dari Wemos"
                      : "Menunggu data Wemos"}
                </span>
              </p>
            </div>
            <div className="flex flex-wrap gap-1.5">
              <StatusPill tone={gpsTone}>{gpsLabel}</StatusPill>
              <StatusPill tone={wemosTone}>{wemosLabel}</StatusPill>
            </div>
          </div>
        </div>

        <div className="flex-auto p-4 pt-2">
          <div className="relative overflow-hidden rounded-xl bg-slate-100">
            {useEmbed ? (
              <GoogleMapEmbed
                position={position}
                defaultCenter={config.center}
                zoom={config.zoom}
              />
            ) : (
              <GoogleMapCanvas
                apiKey={config.apiKey}
                position={position}
                telemetry={telemetry}
                detections={detections}
                trail={trail}
                defaultCenter={config.center}
                defaultZoom={config.zoom}
                follow={follow}
                onManualMove={() => setFollow(false)}
                onError={handleMapError}
              />
            )}

            {!position && (
              <div className="pointer-events-none absolute inset-x-3 bottom-3 rounded-lg bg-white/95 px-3 py-2 text-center text-xs font-semibold text-slate-600 shadow">
                Peta menunggu koordinat valid dari GPS Wemos.
              </div>
            )}

            {!useEmbed && !follow && (
              <button
                type="button"
                onClick={() => setFollow(true)}
                className="absolute right-3 top-3 rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-[#660f08] shadow hover:bg-slate-50"
              >
                Ikuti posisi
              </button>
            )}
          </div>

          {mapError && (
            <p className="mt-2 mb-0 rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-800">
              {mapError} Sementara peta memakai Google Maps mode embed.
            </p>
          )}
          {!config.apiKey && (
            <p className="mt-2 mb-0 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
              Tambahkan <code className="font-semibold">GOOGLE_MAPS_API_KEY</code> di <code className="font-semibold">.env</code> server
              untuk marker realtime, jejak perjalanan, dan marker objek di peta.
            </p>
          )}

          <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric
              label="Jarak sensor"
              value={distance == null ? "-" : `${formatNumber(distance, 2)} m`}
              sub={distance == null ? (hasTelemetry ? "di luar jangkauan" : "menunggu Wemos") : "ultrasonik depan"}
              color={distanceColor}
              icon="ni-sound-wave"
            />
            <Metric
              label="Kecepatan"
              value={telemetry?.spd == null ? "-" : `${formatNumber(telemetry.spd)} km/jam`}
              sub="GPS"
              icon="ni-delivery-fast"
            />
            <Metric
              label="Satelit"
              value={telemetry?.sat == null ? "-" : telemetry.sat}
              sub={`HDOP ${telemetry?.hdop == null ? "-" : formatNumber(telemetry.hdop)}`}
              icon="ni-compass-04"
            />
            <Metric
              label="Ketinggian"
              value={telemetry?.alt == null ? "-" : `${formatNumber(telemetry.alt)} m`}
              sub={`Waktu GPS ${telemetry?.waktu || "--:--:--"} WIB`}
              icon="ni-vector"
            />
          </div>

          <div className="mt-3">
            <div className="flex items-center justify-between text-[11px] font-semibold text-slate-500">
              <span>Jarak ultrasonik (0–4 m)</span>
              <span style={{ color: distanceColor }}>{distance == null ? "tidak valid" : `${formatNumber(distance, 2)} m`}</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200">
              <div
                className="h-full rounded-full transition-all"
                style={{ width: `${distancePercent}%`, background: distanceColor }}
              />
            </div>
          </div>

          {detections.length > 0 && (
            <div className="mt-3">
              <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                Deteksi aktif ({detections.length})
              </div>
              <div className="flex flex-wrap gap-1.5">
                {detections.slice(0, 8).map((detection, index) => {
                  const color = DETECTION_COLORS[detection.urgency] || COLOR.Sedang;
                  return (
                    <span
                      key={`${detection.object}-${index}`}
                      className="inline-flex items-center gap-1.5 rounded-full border bg-white px-2.5 py-1 text-[11px] font-semibold"
                      style={{ borderColor: `${color}55`, color }}
                    >
                      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
                      {detection.object} · {formatNumber(detection.distance)} m · {detection.level}
                    </span>
                  );
                })}
              </div>
              {hasApproxDetection && (
                <p className="mt-1 mb-0 text-[10px] text-slate-400">
                  Marker objek di peta adalah perkiraan dari arah (kiri/depan/kanan) dan jarak sensor.
                </p>
              )}
            </div>
          )}

          <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
            <span className="text-[11px] text-slate-500">
              Telemetri terakhir: <strong>{ageLabel}</strong>
              {telemetry?.age != null && telemetry.online === false ? " · data lama" : ""}
            </span>
            <div className="flex flex-wrap gap-2">
              {mapsUrl && (
                <a
                  className="inline-flex rounded-lg bg-blue-600 px-3 py-2 text-xs font-semibold text-white hover:bg-blue-700"
                  href={mapsUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Buka di Google Maps
                </a>
              )}
              {directionsUrl && (
                <a
                  className="inline-flex rounded-lg border border-slate-300 bg-white px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-50"
                  href={directionsUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  Rute jalan kaki
                </a>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
