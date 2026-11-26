
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Icon from "./Icon";
import { COLOR, DEFAULT_MAP_CONFIG, URGENCY_TONE, levelLabel } from "../data";

const MAP_HEIGHT = 460;
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
  tilt3d,
  onManualMove,
  onError,
}) {
  const containerRef = useRef(null);
  const tilt3dRef = useRef(tilt3d);
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

  useEffect(() => { tilt3dRef.current = tilt3d; }, [tilt3d]);
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
          mapTypeControl: true,
          streetViewControl: false,
          fullscreenControl: true,
          gestureHandling: "greedy",
          clickableIcons: false,
          // Peta vektor: mendukung kemiringan (3D) dan rotasi. DEMO_MAP_ID adalah Map ID
          // uji coba dari Google; ganti dengan Map ID milik sendiri untuk produksi.
          mapId: "DEMO_MAP_ID",
          tilt: tilt3dRef.current ? 45 : 0,
          heading: 0,
          rotateControl: true,
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

  // Beralih 2D/3D tanpa membuat ulang peta.
  useEffect(() => {
    const map = mapRef.current;
    if (!ready || !map) return;
    map.setTilt(tilt3d ? 45 : 0);
    if (!tilt3d) map.setHeading(0);
  }, [ready, tilt3d]);

  return <div ref={containerRef} style={{ height: MAP_HEIGHT, width: "100%" }} />;
}

function GoogleMapEmbed({ position, defaultCenter, zoom }) {
  const center = position || defaultCenter;
  // Bulatkan ~11 m agar iframe tidak dimuat ulang setiap kali GPS bergeser sedikit.
  const key = `${center.lat.toFixed(4)},${center.lng.toFixed(4)},${zoom}`;
  const src = `https://maps.google.com/maps?q=${center.lat},${center.lng}&z=${zoom}&hl=id&t=m&output=embed`;

  return (
    <div style={{ position: "relative", height: MAP_HEIGHT }}>
      <iframe
        key={key}
        title="Google Maps - posisi rompi VestCare"
        src={src}
        style={{ width: "100%", height: "100%", border: 0 }}
        loading="lazy"
        referrerPolicy="no-referrer-when-downgrade"
        allowFullScreen
      />
      <span className="vc-map-badge">Peta dasar</span>
    </div>
  );
}

function StatusPill({ tone, children }) {
  return <span className={`vc-pill vc-tone-${tone}`}>{children}</span>;
}

function Metric({ label, value, sub, tone, icon }) {
  return (
    <div className={`vc-metric ${tone ? `vc-tone-${tone}` : ""}`}>
      <p className="vc-metric-label"><Icon name={icon} size={14} />{label}</p>
      <p className="vc-metric-value" data-tone={tone || undefined}>{value}</p>
      {sub && <p className="vc-metric-sub">{sub}</p>}
    </div>
  );
}

export default function GpsMap({ position, detections = [], telemetry, trail = [], mapConfig }) {
  const config = mapConfig || DEFAULT_MAP_CONFIG;
  const [follow, setFollow] = useState(true);
  const [tilt3d, setTilt3d] = useState(true);
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

  const gpsFix = Boolean(telemetry?.online && telemetry?.fix && position);
  const gpsTone = gpsFix ? "safe" : telemetry?.online ? "warn" : telemetry?.updatedAt ? "danger" : "idle";
  const gpsLabel = gpsFix
    ? "GPS fix"
    : telemetry?.online
      ? "GPS belum fix"
      : telemetry?.updatedAt
        ? "GPS terputus"
        : "Menunggu GPS";
  const hasTelemetry = Boolean(telemetry?.updatedAt || telemetry?.fix || telemetry?.terbaca);
  const gpsHeaderMessage = telemetry?.online
    ? "GPS belum fix · bawa rompi ke area terbuka"
    : hasTelemetry
      ? "Menunggu data GPS dari rompi"
      : "Menunggu data dari rompi";
  const gpsWaitMessage = telemetry?.online
    ? "GPS belum mendapat koordinat. GPS sulit menerima sinyal di dalam ruangan; bawa rompi ke area terbuka dan pastikan antena/modul GPS terhubung."
    : hasTelemetry
      ? "Data GPS dari rompi terputus. Periksa koneksi perangkat."
      : "Menunggu data dari sensor GPS ESP32-S3.";
  const deviceTone = telemetry?.online ? "safe" : hasTelemetry ? "danger" : "idle";
  const deviceLabel = telemetry?.online ? "Rompi online" : hasTelemetry ? "Rompi offline" : "Rompi belum kirim data";

  const ageSeconds = telemetry?.updatedAt
    ? Math.max(0, Math.round((now - telemetry.updatedAt) / 1000))
    : null;
  const ageLabel = ageSeconds == null
    ? "-"
    : ageSeconds <= 2
      ? "baru saja"
      : `${ageSeconds} detik lalu`;

  const distance = telemetry?.jarak;
  const distanceTone = distance == null ? undefined : distance < 1 ? "danger" : distance < 2 ? "warn" : "safe";
  const hasApproxDetection = detections.some((item) => item.lat == null || item.lng == null);
  const mapsUrl = position
    ? `https://www.google.com/maps/search/?api=1&query=${position.lat},${position.lng}`
    : null;
  const directionsUrl = position
    ? `https://www.google.com/maps/dir/?api=1&destination=${position.lat},${position.lng}&travelmode=walking`
    : null;
  const useEmbed = !config.apiKey || Boolean(mapError);

  return (
    <section className="vc-panel" id="peta" aria-labelledby="peta-title">
      <div className="vc-panel-head">
        <div>
          <h2 className="vc-panel-title" id="peta-title">Lokasi rompi</h2>
          <p className="vc-coords">
            <Icon name="pin" size={15} />
            {position ? (
              <>
                <strong>{position.lat.toFixed(6)}, {position.lng.toFixed(6)}</strong>
                {position.updated ? <span>· {position.updated}</span> : null}
              </>
            ) : (
              <span>{gpsHeaderMessage}</span>
            )}
          </p>
        </div>
        <div className="vc-pills">
          <StatusPill tone={gpsTone}>{gpsLabel}</StatusPill>
          <StatusPill tone={deviceTone}>{deviceLabel}</StatusPill>
        </div>
      </div>

      <div className="vc-map-wrap">
        {!position ? (
          <div className="vc-map-empty" role="status">
            <strong>{telemetry?.online ? "Koordinat GPS belum terdeteksi" : "Menunggu sensor GPS"}</strong>
            <span>{gpsWaitMessage}</span>
          </div>
        ) : useEmbed ? (
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
            tilt3d={tilt3d}
            onManualMove={() => setFollow(false)}
            onError={handleMapError}
          />
        )}

        {position && !useEmbed && (
          <div className="vc-map-tools">
            <button type="button" onClick={() => setTilt3d((value) => !value)} className="vc-map-follow" aria-pressed={tilt3d}>
              <Icon name="mountain" size={14} />
              {tilt3d ? "Mode 2D" : "Mode 3D"}
            </button>
            {!follow && (
              <button type="button" onClick={() => setFollow(true)} className="vc-map-follow">
                <Icon name="navigation" size={14} />
                Ikuti posisi
              </button>
            )}
          </div>
        )}
      </div>

      {mapError && (
        <div className="vc-notice" data-tone="warn">
          <div className="vc-notice-head">
            <span className="vc-seg-chip vc-tone-warn"><Icon name="alert" size={16} /></span>
            <div>
              <p className="vc-notice-title">Kunci Google Maps tidak bisa dipakai</p>
              <p className="vc-notice-text">{mapError} Sementara, peta memakai tampilan dasar.</p>
            </div>
          </div>
        </div>
      )}
      <div className="vc-telemetry">
        <Metric
          label="Jarak sensor"
          icon="ruler"
          value={distance == null ? "-" : `${formatNumber(distance, 2)} m`}
          sub={distance == null ? (hasTelemetry ? "Di luar jangkauan" : "Menunggu rompi") : "Ultrasonik depan"}
          tone={distanceTone}
        />
        <Metric
          label="Kecepatan"
          icon="speed"
          value={telemetry?.spd == null ? "-" : `${formatNumber(telemetry.spd)} km/jam`}
          sub="Dari GPS"
        />
        <Metric
          label="Satelit"
          icon="satellite"
          value={telemetry?.sat == null ? "-" : telemetry.sat}
          sub={`HDOP ${telemetry?.hdop == null ? "-" : formatNumber(telemetry.hdop)}`}
        />
        <Metric
          label="Ketinggian"
          icon="mountain"
          value={telemetry?.alt == null ? "-" : `${formatNumber(telemetry.alt)} m`}
          sub={`Waktu GPS ${telemetry?.waktu || "--:--:--"} WIB`}
        />
      </div>

      {detections.length > 0 && (
        <div className="vc-detect">
          <p className="vc-detect-title">Deteksi aktif ({detections.length})</p>
          <div className="vc-chips">
            {detections.slice(0, 8).map((detection, index) => (
              <span
                key={`${detection.object}-${index}`}
                className={`vc-chip vc-tone-${URGENCY_TONE[detection.urgency] || "warn"}`}
              >
                <span className="vc-dot" />
                {detection.object} · {formatNumber(detection.distance)} m · {levelLabel(detection)}
              </span>
            ))}
          </div>
          {hasApproxDetection && (
            <p className="vc-hint">Posisi objek di peta adalah perkiraan dari arah (kiri/depan/kanan) dan jarak sensor.</p>
          )}
        </div>
      )}

      <div className="vc-map-foot">
        <span className="vc-map-age">
          <Icon name="clock" size={14} />
          Data terakhir <b>{ageLabel}</b>
          {telemetry?.age != null && telemetry.online === false ? " · data lama" : ""}
        </span>
        <div className="vc-actions">
          {directionsUrl && (
            <a className="vc-btn vc-btn--ghost" href={directionsUrl} target="_blank" rel="noreferrer">
              <Icon name="navigation" size={15} />
              Rute jalan kaki
            </a>
          )}
          {mapsUrl && (
            <a className="vc-btn vc-btn--primary" href={mapsUrl} target="_blank" rel="noreferrer">
              Buka di Google Maps
              <Icon name="external" size={15} />
            </a>
          )}
        </div>
      </div>
    </section>
  );
}
