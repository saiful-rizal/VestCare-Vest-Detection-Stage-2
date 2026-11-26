import { useEffect, useRef, useState } from "react";
import Icon from "./Icon";
import { normalizeDetections } from "../data";
import { apiFetch, errorMessage } from "../api";

const API_URL = "/deteksi";
const ESP32_FRAME_URL = "/api/esp32/frame/latest";
const ESP32_STATUS_URL = "/api/esp32/status";
const ESP32_FRAME_POLL_INTERVAL_MS = 100;
const REALTIME_DETECTION_INTERVAL_MS = 80;
const REALTIME_REQUEST_TIMEOUT_MS = 60000;
const CAPTURE_MAX_WIDTH = 640;
const CAPTURE_JPEG_QUALITY = 0.85;
const BOX_SMOOTHING = 0.9;
const MAX_TRACK_CENTER_DISTANCE = 0.3;
const CLOSE_FRONT_ALERT_DISTANCE_M = 0.5;
const BUZZER_STALE_TIMEOUT_MS = 1500;

function isCloseFrontObject(detection) {
  return !detection.ragu
    && detection.arah === "depan"
    && Number.isFinite(detection.distance)
    && detection.distance > 0
    && detection.distance < CLOSE_FRONT_ALERT_DISTANCE_M;
}

function createSessionId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID().replace(/-/g, "");
  return `s${Date.now().toString(36)}${Math.random().toString(36).slice(2, 10)}`;
}

function validBox(bbox) {
  return Array.isArray(bbox) && bbox.length === 4 && bbox.every(Number.isFinite);
}

function smoothDetectionBoxes(detections, previousDetections) {
  // Pencocokan global (pasangan terdekat lebih dulu) supaya beberapa objek sekelas tidak tertukar.
  const pairs = [];
  detections.forEach((detection, i) => {
    if (!validBox(detection.bbox)) return;
    const cx = (detection.bbox[0] + detection.bbox[2]) / 2;
    const cy = (detection.bbox[1] + detection.bbox[3]) / 2;
    previousDetections.forEach((previous, j) => {
      if (previous.object !== detection.object || !validBox(previous.bbox)) return;
      const sameId = Number.isFinite(detection.id) && detection.id === previous.id;
      const px = (previous.bbox[0] + previous.bbox[2]) / 2;
      const py = (previous.bbox[1] + previous.bbox[3]) / 2;
      const distance = Math.hypot(cx - px, cy - py);
      if (sameId || distance < MAX_TRACK_CENTER_DISTANCE) {
        pairs.push({ i, j, cost: sameId ? -1 : distance });
      }
    });
  });
  pairs.sort((x, y) => x.cost - y.cost);

  const matchedDetections = new Map();
  const usedPrevious = new Set();
  pairs.forEach(({ i, j }) => {
    if (matchedDetections.has(i) || usedPrevious.has(j)) return;
    matchedDetections.set(i, j);
    usedPrevious.add(j);
  });

  return detections.map((detection, i) => {
    const j = matchedDetections.get(i);
    if (j === undefined) return detection;
    const previousBox = previousDetections[j].bbox;
    return {
      ...detection,
      bbox: detection.bbox.map((coordinate, index) => (
        previousBox[index] * (1 - BOX_SMOOTHING) + coordinate * BOX_SMOOTHING
      )),
    };
  });
}

function labelGerak(detection) {
  if (detection.gerak === "diam") return "DIAM";
  if (detection.gerak !== "bergerak") return null;
  return detection.object.toLowerCase() === "orang" ? "BERJALAN" : "BERGERAK";
}

function labelObjek(detection) {
  return Number.isFinite(detection.id) ? `${detection.object} #${detection.id}` : detection.object;
}

function getVoiceDecision(plan, previousSignature, previousLevel, lastSpokenAt, now, audioPaused) {
  const level = String(plan?.level || "AMAN").toUpperCase();
  const levelRank = { AMAN: 0, INFO: 1, WASPADA: 2, BAHAYA: 3 }[level] || 0;
  const segments = Array.isArray(plan?.segmen) ? plan.segmen : [];
  const signature = `${level}:${plan?.aksi || ""}:${segments
    .map((segment) => segment.kunci || "")
    .join("|")}`;
  const escalation = levelRank > previousLevel;
  const shouldSpeak = levelRank > 0
    && segments.length > 0
    && (
      (escalation && now - lastSpokenAt >= 1200)
      || (signature !== previousSignature && audioPaused && now - lastSpokenAt >= 1800)
      || (signature === previousSignature && audioPaused && now - lastSpokenAt >= 8000)
    );

  return { levelRank, signature, shouldSpeak };
}

function createSilentWavUrl() {
  const sampleRate = 8000;
  const sampleCount = 800;
  const dataSize = sampleCount * 2;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);
  const writeText = (offset, text) => {
    for (let index = 0; index < text.length; index += 1) {
      view.setUint8(offset + index, text.charCodeAt(index));
    }
  };

  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, dataSize, true);

  return URL.createObjectURL(new Blob([buffer], { type: "audio/wav" }));
}

// "12 detik lalu", "3 menit lalu" dari stempel waktu (ms)
function formatAgo(timestamp) {
  if (!timestamp) return "";
  const seconds = Math.max(0, Math.round((Date.now() - timestamp) / 1000));
  if (seconds < 5) return "baru saja";
  if (seconds < 60) return `${seconds} detik lalu`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} menit lalu`;
  return `${Math.round(seconds / 3600)} jam lalu`;
}

export default function CameraCapture({ onDetections, deviceOnline, lastSeen }) {
  const inputRef = useRef(null);
  const videoRef = useRef(null);
  const esp32ImageRef = useRef(null);
  const esp32FrameLoadedRef = useRef(false);
  const boxesRef = useRef(null);
  const audioRef = useRef(null);
  const buzzerContextRef = useRef(null);
  const dashboardAlarmActiveRef = useRef(false);
  const dashboardVoicePendingRef = useRef(false);
  const dashboardLatestDetectionsRef = useRef([]);
  const dashboardLatestPlanRef = useRef(null);
  const buzzerOscillatorRef = useRef(null);
  const buzzerGainRef = useRef(null);
  const lastBuzzerDetectionAtRef = useRef(0);
  const silentAudioUrlRef = useRef(null);
  const audioUnlockedRef = useRef(false);
  const audioTokenRef = useRef(0);
  const cancelPlaybackRef = useRef(null);
  const isPlayingRef = useRef(false);
  const lastPlayedSignatureRef = useRef("");
  const lastPlayedAtRef = useRef(0);
  const streamRef = useRef(null);
  const sessionIdRef = useRef(createSessionId());
  const detectingRef = useRef(false);
  const openingRef = useRef(false);
  const onDetectionsRef = useRef(onDetections);
  const [preview, setPreview] = useState(null);
  const [file, setFile] = useState(null);
  const [liveDetections, setLiveDetections] = useState([]);
  const [esp32FrameUrl, setEsp32FrameUrl] = useState(null);
  const [status, setStatus] = useState("idle");
  const [message, setMessage] = useState("");
  const [dashboardAlarmActive, setDashboardAlarmActive] = useState(false);
  const [dashboardAudioReady, setDashboardAudioReady] = useState(false);
  const [dashboardAlertError, setDashboardAlertError] = useState("");
  // Status tampilan saja: apakah gambar stream ESP32 berhasil dimuat.
  const [streamState, setStreamState] = useState("connecting");
  useEffect(() => {
    if (status === "esp32") setStreamState("connecting");
  }, [status]);

  useEffect(() => {
    onDetectionsRef.current = onDetections;
  }, [onDetections]);

  useEffect(() => () => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    audioTokenRef.current += 1;
    isPlayingRef.current = false;
    cancelPlaybackRef.current?.();
    audioRef.current?.pause();
    stopBuzzer();
    void buzzerContextRef.current?.close();
    buzzerContextRef.current = null;
    if (silentAudioUrlRef.current) URL.revokeObjectURL(silentAudioUrlRef.current);
  }, []);

  useEffect(() => () => {
    if (preview) URL.revokeObjectURL(preview);
  }, [preview]);

  useEffect(() => {
    const audio = new Audio();
    audio.preload = "auto";
    audioRef.current = audio;
    silentAudioUrlRef.current = createSilentWavUrl();

    return () => {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      audioRef.current = null;
    };
  }, []);

  useEffect(() => {
    let active = true;
    let unlocking = false;

    async function tryUnlockAudio() {
      if (unlocking) return;
      unlocking = true;
      await unlockAudio({ quiet: true });
      unlocking = false;
      if (!active) return;

      const ready = buzzerContextRef.current?.state === "running" && audioUnlockedRef.current;
      setDashboardAudioReady(ready);
      if (ready && dashboardAlarmActiveRef.current) {
        buzzForCloseFront(
          dashboardLatestDetectionsRef.current,
          dashboardLatestPlanRef.current,
        );
      }
      if (
        ready
        && dashboardVoicePendingRef.current
        && !isPlayingRef.current
        && dashboardLatestPlanRef.current?.segmen?.length
      ) {
        dashboardVoicePendingRef.current = false;
        void playPlan(dashboardLatestPlanRef.current);
      }

      if (ready) {
        document.removeEventListener("pointerdown", onUserInteraction, true);
        document.removeEventListener("keydown", onUserInteraction, true);
      }
    }

    function onUserInteraction() {
      void tryUnlockAudio();
    }

    void tryUnlockAudio();
    document.addEventListener("pointerdown", onUserInteraction, true);
    document.addEventListener("keydown", onUserInteraction, true);

    return () => {
      active = false;
      document.removeEventListener("pointerdown", onUserInteraction, true);
      document.removeEventListener("keydown", onUserInteraction, true);
    };
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      if (
        dashboardAlarmActiveRef.current
        && Date.now() - lastBuzzerDetectionAtRef.current > BUZZER_STALE_TIMEOUT_MS
      ) {
        stopBuzzer();
        dashboardAlarmActiveRef.current = false;
        dashboardVoicePendingRef.current = false;
        dashboardLatestDetectionsRef.current = [];
        dashboardLatestPlanRef.current = null;
        setDashboardAlarmActive(false);
      }
    }, 250);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!esp32FrameUrl) return undefined;
    return () => URL.revokeObjectURL(esp32FrameUrl);
  }, [esp32FrameUrl]);

  function stopAudio() {
    audioTokenRef.current += 1;
    isPlayingRef.current = false;
    isPlayingRef.current = false;
    cancelPlaybackRef.current?.();
    cancelPlaybackRef.current = null;
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    audio.removeAttribute("src");
    audio.load();
  }

  async function unlockAudio({ quiet = false } = {}) {
    const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
    if (AudioContextConstructor) {
      try {
        if (!buzzerContextRef.current || buzzerContextRef.current.state === "closed") {
          buzzerContextRef.current = new AudioContextConstructor();
        }
        if (buzzerContextRef.current.state !== "running") {
          await buzzerContextRef.current.resume();
        }
      } catch {
        if (!quiet) {
          setMessage("Browser belum mengizinkan audio. Klik halaman sekali untuk mengaktifkan suara.");
        }
      }
    }

    const audio = audioRef.current;
    const silentUrl = silentAudioUrlRef.current;
    if (!audio || !silentUrl || audioUnlockedRef.current) {
      setDashboardAudioReady(
        buzzerContextRef.current?.state === "running" && audioUnlockedRef.current,
      );
      return audioUnlockedRef.current;
    }

    try {
      audio.src = silentUrl;
      await audio.play();
      audio.pause();
      audio.currentTime = 0;
      audio.removeAttribute("src");
      audio.load();
      audioUnlockedRef.current = true;
      setDashboardAudioReady(buzzerContextRef.current?.state === "running");
      return true;
    } catch {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
      if (!quiet) {
        setMessage("Suara belum diizinkan browser. Klik halaman sekali untuk mengaktifkan suara.");
      }
      setDashboardAudioReady(false);
      return false;
    }
  }

  function stopBuzzer() {
    const oscillator = buzzerOscillatorRef.current;
    const gain = buzzerGainRef.current;
    if (!oscillator || !gain) return;

    const context = buzzerContextRef.current;
    if (context?.state === "running") {
      const now = context.currentTime;
      gain.gain.cancelScheduledValues(now);
      gain.gain.setTargetAtTime(0.0001, now, 0.01);
      oscillator.stop(now + 0.04);
    } else if (context?.state !== "closed") {
      oscillator.stop();
    }

    buzzerOscillatorRef.current = null;
    buzzerGainRef.current = null;
  }

  function buzzForCloseFront(detections, plan = null) {
    lastBuzzerDetectionAtRef.current = Date.now();
    dashboardLatestPlanRef.current = plan;
    if (!detections.some(isCloseFrontObject)) {
      dashboardAlarmActiveRef.current = false;
      dashboardLatestDetectionsRef.current = [];
      setDashboardAlarmActive(false);
      stopBuzzer();
      return;
    }

    const newlyActive = !dashboardAlarmActiveRef.current;
    dashboardAlarmActiveRef.current = true;
    dashboardLatestDetectionsRef.current = detections;
    dashboardVoicePendingRef.current = dashboardVoicePendingRef.current || newlyActive;
    setDashboardAlarmActive(true);

    const context = buzzerContextRef.current;
    if (context?.state === "running" && !buzzerOscillatorRef.current) {
      const startAt = context.currentTime;
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      oscillator.type = "square";
      oscillator.frequency.setValueAtTime(880, startAt);
      gain.gain.setValueAtTime(0.0001, startAt);
      gain.gain.exponentialRampToValueAtTime(0.16, startAt + 0.02);
      oscillator.connect(gain);
      gain.connect(context.destination);
      oscillator.onended = () => {
        if (buzzerOscillatorRef.current === oscillator) {
          buzzerOscillatorRef.current = null;
          buzzerGainRef.current = null;
        }
      };
      buzzerOscillatorRef.current = oscillator;
      buzzerGainRef.current = gain;
      oscillator.start(startAt);
    }

    if (
      dashboardVoicePendingRef.current
      && audioUnlockedRef.current
      && !isPlayingRef.current
      && dashboardLatestPlanRef.current?.segmen?.length
    ) {
      dashboardVoicePendingRef.current = false;
      void playPlan(dashboardLatestPlanRef.current);
    }
  }

  function playUrl(url) {
    const audio = audioRef.current;
    if (!audio) return Promise.reject(new Error("Pemutar suara tidak tersedia."));

    return new Promise((resolve, reject) => {
      let settled = false;
      const cleanup = () => {
        audio.removeEventListener("ended", onEnded);
        audio.removeEventListener("error", onError);
        if (cancelPlaybackRef.current === cancel) cancelPlaybackRef.current = null;
      };
      const finish = (callback, value) => {
        if (settled) return;
        settled = true;
        cleanup();
        callback(value);
      };
      const onEnded = () => finish(resolve);
      const onError = () => finish(reject, new Error("Berkas suara tidak dapat diputar."));
      const cancel = () => finish(reject, new Error("Pemutaran suara dihentikan."));

      cancelPlaybackRef.current = cancel;
      audio.addEventListener("ended", onEnded);
      audio.addEventListener("error", onError);
      audio.src = url;
      audio.play().catch((error) => finish(reject, error));
    });
  }

  async function playPlan(plan) {
    if (!plan || !Array.isArray(plan.segmen) || !plan.segmen.length) {
      setMessage("Instruksi suara tidak tersedia untuk hasil deteksi ini.");
      return;
    }

    if (!audioUnlockedRef.current) {
      setMessage("Hasil terdeteksi, tetapi browser belum mengizinkan audio. Klik halaman sekali untuk mengaktifkan suara.");
      return;
    }

    const signature = `${plan.level || ""}:${plan.aksi || ""}:${plan.segmen
      .map((segment) => segment.kunci || "")
      .join("|")}`;
    const now = Date.now();

    if (isPlayingRef.current) return;

    if (
      signature === lastPlayedSignatureRef.current
      && now - lastPlayedAtRef.current < 1800
    ) {
      return;
    }

    stopAudio();
    const token = audioTokenRef.current;

    isPlayingRef.current = true;
    lastPlayedSignatureRef.current = signature;
    lastPlayedAtRef.current = now;

    setMessage(`Memutar instruksi ${plan.level}...`);

    try {
      for (const segment of plan.segmen) {
        if (token !== audioTokenRef.current) return;
        await playUrl(segment.url);
      }

      if (token === audioTokenRef.current) {
        setMessage(`Instruksi ${plan.level} selesai diputar.`);
      }
    } catch (error) {
      if (token === audioTokenRef.current) {
        setMessage(`Suara gagal diputar: ${error.message}`);
      }
    } finally {
      if (token === audioTokenRef.current) {
        isPlayingRef.current = false;
      }
    }
  }

  useEffect(() => {
    if (status !== "camera") return undefined;

    const video = videoRef.current;
    const stream = streamRef.current;
    if (!video || !stream) return undefined;

    video.srcObject = stream;
    video.play().catch(() => {});

    return () => {
      video.srcObject = null;
    };
  }, [status]);

  useEffect(() => {
    if (status !== "esp32") return undefined;

    let active = true;
    let reconnectTimer = null;
    let eventSource = null;
    let lastUpdatedAt = 0;
    let previousDetections = [];
    let lastAudioSignature = "";
    let lastAudioLevel = 0;
    let lastSpokenAt = 0;
    let lastSessionRefreshAt = 0;

    function applyLatestDetection(payload) {
      const updatedAt = Number(payload?.updated_at);
      const serverAge = Number(payload?.umur_detik);
      const stale = payload?.online === false
        || !Number.isFinite(updatedAt)
        || (Number.isFinite(serverAge) ? serverAge > 30 : Date.now() / 1000 - updatedAt > 30);

      if (stale) {
        stopBuzzer();
        dashboardAlarmActiveRef.current = false;
        dashboardVoicePendingRef.current = false;
        dashboardLatestDetectionsRef.current = [];
        dashboardLatestPlanRef.current = null;
        setDashboardAlarmActive(false);
        if (lastUpdatedAt !== 0) {
          lastUpdatedAt = 0;
          previousDetections = [];
          setLiveDetections([]);
          onDetectionsRef.current([]);
        }
        if (audioRef.current?.paused) {
          setMessage("Menunggu hasil deteksi terbaru dari kamera ESP32...");
        }
        return;
      }
      if (updatedAt <= lastUpdatedAt || !payload?.data) return;

      const detections = smoothDetectionBoxes(
        normalizeDetections(payload.data, { includeUncertain: true }),
        previousDetections,
      );
      previousDetections = detections;
      lastUpdatedAt = updatedAt;
      const plan = payload.data.suara;
      buzzForCloseFront(detections, plan);
      setLiveDetections(detections);
      onDetectionsRef.current(detections.filter((detection) => !detection.ragu));

      const now = Date.now();
      const audioPaused = audioRef.current?.paused !== false;
      const voice = getVoiceDecision(
        plan,
        lastAudioSignature,
        lastAudioLevel,
        lastSpokenAt,
        now,
        audioPaused,
      );

      if (voice.shouldSpeak) {
        lastAudioSignature = voice.signature;
        lastAudioLevel = voice.levelRank;
        lastSpokenAt = now;
        void playPlan(plan);
      } else if (voice.levelRank === 0 && now - lastSpokenAt > 5000) {
        lastAudioSignature = "";
        lastAudioLevel = 0;
      }

      if (audioPaused && !voice.shouldSpeak) {
        setMessage(detections.length
          ? `${detections.length} objek terdeteksi dari kamera ESP32.`
          : "Kamera ESP32 aktif. Belum ada objek yang yakin.");
      }
    }

    const staleTimer = window.setInterval(() => {
      if (!lastUpdatedAt || Date.now() / 1000 - lastUpdatedAt <= 30) return;
      lastUpdatedAt = 0;
      previousDetections = [];
      dashboardVoicePendingRef.current = false;
      dashboardLatestDetectionsRef.current = [];
      dashboardLatestPlanRef.current = null;
      dashboardAlarmActiveRef.current = false;
      setDashboardAlarmActive(false);
      stopBuzzer();
      setLiveDetections([]);
      onDetectionsRef.current([]);
      if (audioRef.current?.paused) {
        setMessage("Menunggu hasil deteksi terbaru dari kamera ESP32...");
      }
    }, 1000);

    async function connectDetectionStream() {
      try {
        const response = await apiFetch("/api/deteksi/latest");
        if (!active) return;
        const payload = await response.json().catch(() => ({}));
        if (!active) return;
        if (!response.ok) {
          throw new Error(errorMessage(
            payload,
            `Server VestCare mengembalikan ${response.status}.`,
          ));
        }
        applyLatestDetection(payload);
        eventSource = new EventSource("/api/deteksi/stream");
        eventSource.onmessage = (event) => {
          try {
            applyLatestDetection(JSON.parse(event.data));
          } catch {
            setMessage("Respons realtime deteksi tidak dapat dibaca.");
          }
        };
        eventSource.onerror = () => {
          const now = Date.now();
          if (!active || now - lastSessionRefreshAt < 5000) return;
          lastSessionRefreshAt = now;
          void apiFetch("/api/deteksi/latest")
            .then(async (sessionResponse) => {
              const sessionPayload = await sessionResponse.json().catch(() => ({}));
              if (!sessionResponse.ok) {
                throw new Error(errorMessage(
                  sessionPayload,
                  `Server VestCare mengembalikan ${sessionResponse.status}.`,
                ));
              }
              applyLatestDetection(sessionPayload);
            })
            .catch((error) => {
              if (!active) return;
              setMessage(error instanceof Error
                ? `Koneksi hasil deteksi gagal: ${error.message}`
                : "Koneksi hasil deteksi gagal.");
            });
        };
      } catch (error) {
        if (!active) return;
        setMessage(error instanceof Error
          ? `Koneksi hasil deteksi gagal: ${error.message}`
          : "Koneksi hasil deteksi gagal.");
        reconnectTimer = window.setTimeout(connectDetectionStream, 1000);
      }
    }

    void connectDetectionStream();
    return () => {
      active = false;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      window.clearInterval(staleTimer);
      eventSource?.close();
    };
  }, [status]);

  useEffect(() => {
    if (status === "esp32" || status === "camera") return undefined;

    let active = true;
    let reconnectTimer = null;
    let eventSource = null;
    let lastUpdatedAt = 0;
    let lastDetectionAt = 0;
    let lastAudioSignature = "";
    let lastAudioLevel = 0;
    let lastSpokenAt = 0;
    let lastSessionRefreshAt = 0;

    function applyDashboardDetection(payload) {
      const updatedAt = Number(payload?.updated_at);
      const serverAge = Number(payload?.umur_detik);
      const stale = payload?.online === false
        || !Number.isFinite(updatedAt)
        || (Number.isFinite(serverAge) ? serverAge > 30 : Date.now() / 1000 - updatedAt > 30);

      if (stale || !payload?.data) {
        buzzForCloseFront([]);
        setLiveDetections([]);
        onDetectionsRef.current([]);
        lastUpdatedAt = 0;
        lastDetectionAt = 0;
        lastAudioSignature = "";
        lastAudioLevel = 0;
        lastSpokenAt = 0;
        dashboardVoicePendingRef.current = false;
        dashboardLatestPlanRef.current = null;
        return;
      }
      if (updatedAt <= lastUpdatedAt) return;

      const detections = normalizeDetections(payload.data, { includeUncertain: true });
      const plan = payload.data.suara;
      lastUpdatedAt = updatedAt;
      lastDetectionAt = Date.now();
      setLiveDetections(detections);
      onDetectionsRef.current(detections.filter((detection) => !detection.ragu));
      buzzForCloseFront(detections, plan);
      dashboardLatestPlanRef.current = plan || null;

      const now = Date.now();
      const audioPaused = audioRef.current?.paused !== false;
      const voice = getVoiceDecision(
        plan,
        lastAudioSignature,
        lastAudioLevel,
        lastSpokenAt,
        now,
        audioPaused,
      );
      if (voice.shouldSpeak) {
        lastAudioSignature = voice.signature;
        lastAudioLevel = voice.levelRank;
        lastSpokenAt = now;
        if (audioUnlockedRef.current) {
          dashboardVoicePendingRef.current = false;
          void playPlan(plan);
        } else {
          dashboardVoicePendingRef.current = true;
        }
      } else if (voice.levelRank === 0) {
        dashboardVoicePendingRef.current = false;
        if (now - lastSpokenAt > 5000) {
          lastAudioSignature = "";
          lastAudioLevel = 0;
        }
      }
    }

    async function readLatestDetection() {
      const response = await apiFetch("/api/deteksi/latest");
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(errorMessage(
          payload,
          `Server VestCare mengembalikan ${response.status}.`,
        ));
      }
      applyDashboardDetection(payload);
    }

    async function connectDetectionStream() {
      try {
        await readLatestDetection();
        if (!active) return;
        eventSource = new EventSource("/api/deteksi/stream");
        eventSource.onopen = () => setDashboardAlertError("");
        eventSource.onmessage = (event) => {
          try {
            applyDashboardDetection(JSON.parse(event.data));
          } catch {
            setDashboardAlertError("Respons deteksi realtime tidak dapat dibaca.");
          }
        };
        eventSource.onerror = () => {
          const now = Date.now();
          if (!active || now - lastSessionRefreshAt < 5000) return;
          lastSessionRefreshAt = now;
          void readLatestDetection().catch((error) => {
            if (!active) return;
            setDashboardAlertError(error instanceof Error ? error.message : String(error));
          });
        };
      } catch (error) {
        if (!active) return;
        setDashboardAlertError(error instanceof Error ? error.message : String(error));
        reconnectTimer = window.setTimeout(connectDetectionStream, 1000);
      }
    }

    const staleTimer = window.setInterval(() => {
      if (!lastDetectionAt || Date.now() - lastDetectionAt <= 30000) return;
      lastDetectionAt = 0;
      lastUpdatedAt = 0;
      setLiveDetections([]);
      onDetectionsRef.current([]);
      buzzForCloseFront([]);
      dashboardVoicePendingRef.current = false;
      dashboardLatestPlanRef.current = null;
    }, 1000);

    void connectDetectionStream();
    return () => {
      active = false;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      window.clearInterval(staleTimer);
      eventSource?.close();
      stopBuzzer();
      dashboardAlarmActiveRef.current = false;
      dashboardVoicePendingRef.current = false;
      dashboardLatestDetectionsRef.current = [];
      dashboardLatestPlanRef.current = null;
      setDashboardAlarmActive(false);
    };
  }, [status]);

  useEffect(() => {
    if (status !== "esp32") return undefined;

    let active = true;
    let timer = null;
    let etag = "";
    let failures = 0;
    let lastFrameAt = Date.now();

    async function pollLatestFrame() {
      try {
        const headers = { "ngrok-skip-browser-warning": "1" };
        if (etag) headers["If-None-Match"] = etag;
        const response = await apiFetch(ESP32_FRAME_URL, { headers });
        if (!active) return;

        if (response.status === 204) {
          failures = 0;
          if (Date.now() - lastFrameAt > 5000) {
            setStreamState("error");
            setMessage("Belum ada frame kamera baru; mencoba kembali.");
          }
        } else if (response.status === 304) {
          failures = 0;
          lastFrameAt = Date.now();
          if (esp32FrameLoadedRef.current) setStreamState("live");
        } else if (!response.ok) {
          throw new Error(`Server kamera mengembalikan ${response.status}.`);
        } else {
          const blob = await response.blob();
          if (!active) return;
          etag = response.headers.get("ETag") || etag;
          failures = 0;
          lastFrameAt = Date.now();
          esp32FrameLoadedRef.current = false;
          setStreamState("connecting");
          setEsp32FrameUrl(URL.createObjectURL(blob));
        }
      } catch {
        if (!active) return;
        failures = Math.min(failures + 1, 4);
        if (Date.now() - lastFrameAt > 5000) {
          setStreamState("error");
          setMessage("Koneksi kamera gagal; mencoba mengambil gambar kembali.");
        }
      }

      if (active) {
        const delay = Math.min(ESP32_FRAME_POLL_INTERVAL_MS * (2 ** failures), 1200);
        timer = window.setTimeout(pollLatestFrame, delay);
      }
    }

    void pollLatestFrame();
    return () => {
      active = false;
      if (timer) window.clearTimeout(timer);
    };
  }, [status]);

  useEffect(() => {
    if (status !== "esp32") return undefined;

    const image = esp32ImageRef.current;
    const canvas = boxesRef.current;
    if (!image || !canvas) return undefined;

    function drawBoxes() {
      const context = canvas.getContext("2d");
      if (!context) return;

      const canvasRect = canvas.getBoundingClientRect();
      const imageRect = image.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(canvasRect.width * ratio);
      canvas.height = Math.round(canvasRect.height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, canvasRect.width, canvasRect.height);

      if (!image.naturalWidth || !image.naturalHeight) return;

      const scale = Math.min(
        imageRect.width / image.naturalWidth,
        imageRect.height / image.naturalHeight,
      );
      const offsetX = imageRect.left - canvasRect.left
        + (imageRect.width - image.naturalWidth * scale) / 2;
      const offsetY = imageRect.top - canvasRect.top
        + (imageRect.height - image.naturalHeight * scale) / 2;

      context.font = "600 13px system-ui, sans-serif";
      context.lineWidth = 3;
      liveDetections.forEach((detection) => {
        const [left, top, right, bottom] = detection.bbox || [];
        if (![left, top, right, bottom].every(Number.isFinite)) return;

        const color = detection.ragu ? "#60a5fa"
          : detection.level === "BAHAYA" ? "#ff4055"
          : detection.level === "WASPADA" ? "#ffbd35"
          : detection.level === "INFO" ? "#46dd91" : "#31c7e8";
        const x = offsetX + left * image.naturalWidth * scale;
        const y = offsetY + top * image.naturalHeight * scale;
        const width = (right - left) * image.naturalWidth * scale;
        const height = (bottom - top) * image.naturalHeight * scale;
        const label = `${labelObjek(detection)} ${Math.round(detection.confidence)}%${detection.ragu ? " | KANDIDAT" : ""}`;

        context.strokeStyle = color;
        context.setLineDash(detection.ragu ? [6, 4] : []);
        context.strokeRect(x, y, width, height);
        context.setLineDash([]);
        context.fillStyle = color;
        const labelY = Math.max(0, y - 22);
        context.fillRect(x, labelY, context.measureText(label).width + 12, 20);
        context.fillStyle = "#102a43";
        context.fillText(label, x + 6, labelY + 14);
      });
    }

    drawBoxes();
    const resizeObserver = new ResizeObserver(drawBoxes);
    resizeObserver.observe(canvas);
    resizeObserver.observe(image);
    return () => resizeObserver.disconnect();
  }, [liveDetections, status, streamState]);

  useEffect(() => {
    if (status !== "camera") return undefined;

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previousOverflow;
    };
  }, [status]);

  useEffect(() => {
    if (status !== "camera") return undefined;

    let active = true;
    let timer;
    let requestController;
    const canvas = document.createElement("canvas");
    const context = canvas.getContext("2d", { alpha: false });
    let alertKey = null;
    let alertLevel = 0;
    let lastAlertAt = 0;
    let lastSpokenAt = 0;
    let previousDetections = [];
    let failures = 0;

    function renderBoxes(detections) {
      const video = videoRef.current;
      const canvas = boxesRef.current;
      if (!video || !canvas) return;

      const { width, height } = video.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      const context = canvas.getContext("2d");
      if (!context) return;

      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, width, height);
      if (!video.videoWidth || !video.videoHeight) return;

      const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
      const offsetX = (width - video.videoWidth * scale) / 2;
      const offsetY = (height - video.videoHeight * scale) / 2;
      context.font = "600 13px system-ui, sans-serif";
      context.lineWidth = 3;

      detections.forEach((detection) => {
        const [left, top, right, bottom] = detection.bbox || [];
        if (![left, top, right, bottom].every(Number.isFinite)) return;

        const x = offsetX + left * video.videoWidth * scale;
        const y = offsetY + top * video.videoHeight * scale;
        const boxWidth = (right - left) * video.videoWidth * scale;
        const boxHeight = (bottom - top) * video.videoHeight * scale;
        const color = detection.ragu ? "#60a5fa"
          : detection.level === "BAHAYA" ? "#ff4055"
          : detection.level === "WASPADA" ? "#ffbd35"
          : detection.level === "INFO" ? "#46dd91" : "#31c7e8";
        const gerak = labelGerak(detection);
        const label = `${labelObjek(detection)} | ${detection.level} | ${detection.distance.toFixed(1)} m${gerak ? ` | ${gerak}` : ""}${detection.ragu ? " | KANDIDAT" : ""}`;

        context.strokeStyle = color;
        context.setLineDash(detection.ragu ? [6, 4] : []);
        context.strokeRect(x, y, boxWidth, boxHeight);
        context.setLineDash([]);
        context.fillStyle = color;
        const labelY = Math.max(0, y - 24);
        context.fillRect(x, labelY, context.measureText(label).width + 12, 22);
        context.fillStyle = "#102a43";
        context.fillText(label, x + 6, labelY + 15);
      });
    }

    async function detectFrame() {
      const video = videoRef.current;
      if (!active) return;
      if (!video || !video.videoWidth || detectingRef.current) {
        timer = window.setTimeout(detectFrame, 250);
        return;
      }

      detectingRef.current = true;
      const scale = Math.min(1, CAPTURE_MAX_WIDTH / video.videoWidth);
      canvas.width = Math.round(video.videoWidth * scale);
      canvas.height = Math.round(video.videoHeight * scale);

      try {
        if (!context) throw new Error("Tidak dapat menyiapkan gambar kamera.");
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        const blob = await new Promise((resolve, reject) => {
          canvas.toBlob((value) => value
            ? resolve(value)
            : reject(new Error("Gagal mengambil gambar kamera.")), "image/jpeg", CAPTURE_JPEG_QUALITY);
        });
        if (!active) return;

        const body = new FormData();
        body.append("gambar", blob, "vest-care-live.jpg");
        body.append("mode_realtime", "true");
        body.append("sesi", sessionIdRef.current);
        body.append("ts_ms", String(Math.round(performance.now())));
        requestController = new AbortController();
        const response = await apiFetch(API_URL, {
          method: "POST",
          body,
          signal: requestController.signal,
        }, { timeoutMs: REALTIME_REQUEST_TIMEOUT_MS });
        const payload = await response.json().catch(() => ({}));
        if (!active) return;
        if (!response.ok) {
          throw new Error(errorMessage(
            payload,
            `Server deteksi mengembalikan ${response.status}.`,
          ));
        }
        failures = 0;

        const detections = smoothDetectionBoxes(
          normalizeDetections(payload, { includeUncertain: true }),
          previousDetections,
        );
        previousDetections = detections;
        buzzForCloseFront(detections, payload.suara);
        setLiveDetections(detections);
        renderBoxes(detections);
        onDetectionsRef.current(detections.filter((detection) => !detection.ragu));
        const alerts = detections.filter((detection) => !detection.ragu && detection.level !== "AMAN");
        const now = Date.now();
        const hasAudioPlan = Array.isArray(payload.suara?.segmen) && payload.suara.segmen.length > 0;

        if (alerts.length) {
          lastAlertAt = now;
          const top = alerts[0];
          const nextKey = `${top.object}:${top.arah}`;
          const nextLevel = { AMAN: 0, INFO: 1, WASPADA: 2, BAHAYA: 3 }[top.level] || 0;
          if (hasAudioPlan && (nextKey !== alertKey || nextLevel > alertLevel) && now - lastSpokenAt >= 1800) {
            alertKey = nextKey;
            alertLevel = nextLevel;
            lastSpokenAt = now;
            void playPlan(payload.suara);
          } else if (audioRef.current?.paused) {
            setMessage(`${alerts.length} rintangan terdeteksi. Peringatan ${top.level}.`);
          }
        } else if (detections.length) {
          lastAlertAt = now;
          const top = detections[0];
          const nextKey = `${top.object}:${top.arah}`;
          if (hasAudioPlan && (nextKey !== alertKey || alertLevel > 0) && now - lastSpokenAt >= 1800) {
            alertKey = nextKey;
            alertLevel = 0;
            lastSpokenAt = now;
            void playPlan(payload.suara);
          } else if (audioRef.current?.paused) {
            setMessage(`${detections.length} objek terdeteksi: ${top.object} ${top.arah}.`);
          }
        } else {
          if (now - lastAlertAt > 3500) {
            alertKey = null;
            alertLevel = 0;
          }
          if (audioRef.current?.paused) {
            setMessage("Kamera aktif. Tidak ada objek yang cukup yakin.");
          }
        }
        if (payload.supabase_error) {
          setMessage(`Deteksi berhasil, tetapi gagal disimpan ke Supabase: ${payload.supabase_error}`);
        }
      } catch (error) {
        if (active) {
          setMessage(error instanceof Error ? `Deteksi gagal: ${error.message}` : "Deteksi real-time gagal.");
          failures = Math.min(failures + 1, 4);
        }
      } finally {
        detectingRef.current = false;
        if (active) {
          const delay = failures
            ? Math.min(REALTIME_DETECTION_INTERVAL_MS * (2 ** failures), 2000)
            : REALTIME_DETECTION_INTERVAL_MS;
          timer = window.setTimeout(detectFrame, delay);
        }
      }
    }

    setMessage("Kamera aktif. Deteksi otomatis sedang berjalan.");
    void detectFrame();
    return () => {
      active = false;
      window.clearTimeout(timer);
      requestController?.abort();
      detectingRef.current = false;
    };
  }, [status]);

  function stopBrowserStream() {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }

  function openEsp32Camera() {
    stopBuzzer();
    stopBrowserStream();
    esp32FrameLoadedRef.current = false;
    setEsp32FrameUrl(null);
    setStreamState("connecting");
    setStatus("esp32");
    setMessage("Kamera ESP32 terhubung. Menunggu hasil deteksi API...");
    setLiveDetections([]);
    setPreview(null);
    setFile(null);
  }

  async function openBrowserCamera() {
    stopBuzzer();
    stopBrowserStream();
    if (!navigator.mediaDevices?.getUserMedia) {
      inputRef.current?.click();
      return false;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: { ideal: "environment" } },
        audio: false,
      });
      streamRef.current = stream;
      setStatus("camera");
      setMessage("");
      setLiveDetections([]);
      setPreview(null);
      setFile(null);
      return true;
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? `Kamera tidak dapat dibuka: ${error.message}` : "Kamera tidak dapat dibuka.");
      return false;
    }
  }

  async function esp32CameraAvailable() {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), 4000);
    try {
      const response = await apiFetch(ESP32_STATUS_URL, { signal: controller.signal });
      if (!response.ok) return false;
      const payload = await response.json().catch(() => ({}));
      return Boolean(payload?.tersedia);
    } catch {
      return false;
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function openCamera() {
    if (openingRef.current) return;
    openingRef.current = true;
    try {
      await unlockAudio();
      // Jangan memaksa mode ESP32: jika rompi belum mengirim frame, dashboard
      // otomatis memakai kamera perangkat agar tombol Deteksi tetap berfungsi.
      if (await esp32CameraAvailable()) {
        openEsp32Camera();
        return;
      }
      await openBrowserCamera();
    } finally {
      openingRef.current = false;
    }
  }

  async function switchToEsp32() {
    await unlockAudio();
    if (await esp32CameraAvailable()) {
      openEsp32Camera();
    } else {
      setMessage("Kamera ESP32 belum mengirim frame. Periksa daya dan koneksi perangkat.");
    }
  }

  async function switchToBrowser() {
    await unlockAudio();
    await openBrowserCamera();
  }

  function handleFileChange(event) {
    const selectedFile = event.target.files?.[0];
    if (!selectedFile) return;

    if (preview) URL.revokeObjectURL(preview);
    setFile(selectedFile);
    setPreview(URL.createObjectURL(selectedFile));
    setStatus("ready");
    setMessage("");
  }

  function closePreview() {
    stopBuzzer();
    stopAudio();
    stopBrowserStream();
    esp32FrameLoadedRef.current = false;
    setEsp32FrameUrl(null);
    setStreamState("connecting");
    setLiveDetections([]);
    onDetectionsRef.current([]);
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setFile(null);
    setStatus("idle");
    setMessage("");
    if (inputRef.current) inputRef.current.value = "";
  }

  async function submitDetection() {
    if (!file) return;

    await unlockAudio();
    setStatus("loading");
    setMessage("");
    const body = new FormData();
    body.append("gambar", file);
    body.append("sesi", "tanpa");

    try {
      const response = await apiFetch(API_URL, {
        method: "POST",
        body,
      }, { timeoutMs: REALTIME_REQUEST_TIMEOUT_MS });

      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(errorMessage(
          payload,
          `Server deteksi mengembalikan ${response.status}.`,
        ));
      }

      const detections = normalizeDetections(payload, { includeUncertain: true });
      buzzForCloseFront(detections, payload.suara);
      onDetections(detections.filter((detection) => !detection.ragu), { realtime: false });
      setLiveDetections(detections);
      setStatus("success");
      setMessage(detections.length
        ? `${detections.length} objek terdeteksi.`
        : "Tidak ada objek yang cukup yakin.");
      if (Array.isArray(payload.suara?.segmen) && payload.suara.segmen.length) {
        await playPlan(payload.suara);
      }
      if (payload.supabase_error) {
        setMessage(`Deteksi berhasil, tetapi gagal disimpan ke Supabase: ${payload.supabase_error}`);
      }
    } catch (error) {
      setStatus("error");
      setMessage(error instanceof Error ? error.message : "Deteksi gagal diproses.");
    }
  }

  const deviceKnown = typeof deviceOnline === "boolean";
  const esp32State = streamState === "error" ? "error" : deviceKnown && !deviceOnline ? "offline" : "online";
  const esp32Label = {
    online: "Perangkat online · terhubung ke API",
    offline: `Perangkat offline${lastSeen ? ` · terakhir aktif ${formatAgo(lastSeen)}` : ""}`,
    error: "Stream kamera terputus",
  }[esp32State];
  const keepOriginalMessage = /^(Koneksi|Deteksi gagal)/.test(message);
  const esp32Message = esp32State === "online" || keepOriginalMessage
    ? message
    : esp32State === "error"
      ? "Gambar dari kamera ESP32 tidak dapat dimuat. Periksa daya dan jaringan perangkat."
      : "Perangkat offline. Deteksi akan berjalan lagi setelah rompi terhubung kembali.";
  const dashboardAlarmLabel = dashboardAlertError
    ? `Alarm realtime: ${dashboardAlertError}`
    : dashboardAlarmActive
      ? dashboardAudioReady
        ? "Objek dekat · buzzer dan suara Ardi aktif"
        : "Objek dekat · klik halaman untuk mengizinkan audio"
      : dashboardAudioReady
        ? "Alarm otomatis siaga"
        : "Alarm otomatis siaga · audio menunggu izin browser";

  return (
    <>
      <div
        className={`vc-dashboard-alarm-indicator${dashboardAlarmActive ? " is-active" : ""}`}
        role="status"
        aria-live={dashboardAlarmActive ? "assertive" : "polite"}
      >
        <span className="vc-dashboard-alarm-dot" />
        <span>{dashboardAlarmLabel}</span>
      </div>
      <button
        type="button"
        className="vc-camera-fab"
        aria-label="Ambil foto untuk deteksi"
        onClick={openCamera}
      >
        <Icon name="camera" size={20} />
        <span>Deteksi</span>
      </button>
      <input
        ref={inputRef}
        className="hidden"
        type="file"
        accept="image/*"
        capture="environment"
        onChange={handleFileChange}
      />

      {preview && (
        <div className="vc-camera-backdrop" role="dialog" aria-modal="true" aria-label="Pratinjau foto">
          <div className="vc-camera-dialog">
            <div className="flex items-center justify-between mb-4">
              <h2 className="mb-0 text-lg font-bold text-slate-800">Deteksi dari kamera</h2>
              <button type="button" className="vc-camera-close" onClick={closePreview} aria-label="Tutup">×</button>
            </div>
            <img className="vc-camera-preview" src={preview} alt="Pratinjau foto yang dipilih" />
            {message && <p className={`vc-camera-message ${status === "error" ? "is-error" : ""}`}>{message}</p>}
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" className="vc-camera-secondary" onClick={openCamera}>Ambil ulang</button>
              <button type="button" className="vc-camera-primary" onClick={submitDetection} disabled={status === "loading"}>
                {status === "loading" ? "Memproses..." : "Kirim untuk deteksi"}
              </button>
            </div>
          </div>
        </div>
      )}
      {status === "error" && (
        <div className="vc-camera-backdrop" role="dialog" aria-modal="true" aria-label="Kamera tidak tersedia">
          <div className="vc-camera-dialog">
            <div className="flex items-center justify-between mb-4">
              <h2 className="mb-0 text-lg font-bold text-slate-800">Kamera tidak tersedia</h2>
              <button type="button" className="vc-camera-close" onClick={closePreview} aria-label="Tutup">×</button>
            </div>
            <p className="vc-camera-message is-error" role="alert">
              {message || "Kamera tidak dapat dibuka."}
            </p>
            <p className="text-sm text-slate-600">
              Anda tetap dapat mengirim foto dari galeri untuk dideteksi.
            </p>
            <div className="flex justify-end gap-2 mt-4">
              <button type="button" className="vc-camera-secondary" onClick={() => inputRef.current?.click()}>
                Pilih foto
              </button>
              <button type="button" className="vc-camera-secondary" onClick={closePreview}>Tutup</button>
              <button type="button" className="vc-camera-primary" onClick={openCamera}>Coba lagi</button>
            </div>
          </div>
        </div>
      )}
      {status === "camera" && (
        <div className="vc-camera-backdrop vc-camera-backdrop--fullscreen" role="dialog" aria-modal="true" aria-label="Kamera">
          <div className="vc-camera-dialog vc-camera-dialog--fullscreen">
            <div className="vc-camera-header flex items-center justify-between mb-4">
              <h2 className="mb-0 text-lg font-bold text-slate-800">Ambil foto deteksi</h2>
              <button type="button" className="vc-camera-close" onClick={closePreview} aria-label="Tutup">×</button>
            </div>
            <div className="vc-camera-stage vc-camera-stage--fullscreen">
              <video ref={videoRef} className="vc-camera-preview" autoPlay playsInline muted />
              <canvas ref={boxesRef} className="vc-camera-boxes" aria-hidden="true" />
              <span className="vc-camera-count" role="status">
                {liveDetections.length} objek terdeteksi
              </span>
            </div>
            {message && <p className={`vc-camera-message ${message.startsWith("Deteksi gagal:") ? "is-error" : ""}`} role="status">{message}</p>}
            {liveDetections.length > 0 && (
              <ul className="vc-camera-results">
                {liveDetections.map((detection, index) => (
                  <li key={Number.isFinite(detection.id) ? `id-${detection.id}` : `${detection.object}-${detection.arah}-${index}`}>
                    <strong>{detection.level} | {labelObjek(detection)} {detection.arah}{detection.ragu ? " | KANDIDAT" : ""}</strong>
                    <span>
                      {detection.distance.toFixed(1)} m | confidence {Math.round(detection.confidence)}%
                      {labelGerak(detection) ? ` | ${labelGerak(detection)}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <div className="vc-camera-footer flex justify-end gap-2 mt-4">
              <button type="button" className="vc-camera-secondary" onClick={switchToEsp32}>
                Kamera ESP32
              </button>
              <button type="button" className="vc-camera-secondary" onClick={closePreview}>Batal</button>
              <span className="vc-camera-live-status">● Deteksi otomatis aktif</span>
            </div>
          </div>
        </div>
      )}
      {status === "esp32" && (
        <div className="vc-camera-backdrop vc-camera-backdrop--fullscreen" role="dialog" aria-modal="true" aria-label="Kamera ESP32-S3">
          <div className="vc-camera-dialog vc-camera-dialog--fullscreen" data-state={esp32State}>
            <div className="vc-camera-header flex items-center justify-between mb-4">
              <h2 className="mb-0 text-lg font-bold text-slate-800">Kamera ESP32-S3 VestCare</h2>
              <button type="button" className="vc-camera-close" onClick={closePreview} aria-label="Tutup">×</button>
            </div>
            <div className="vc-camera-stage vc-camera-stage--fullscreen">
              <img
                ref={esp32ImageRef}
                className="vc-camera-preview"
                src={esp32FrameUrl || undefined}
                alt="Live stream kamera ESP32-S3"
                onLoad={() => {
                  esp32FrameLoadedRef.current = true;
                  setStreamState("live");
                  setMessage((current) => /^(Belum ada frame|Koneksi kamera)/.test(current) ? "" : current);
                }}
                onError={() => {
                  esp32FrameLoadedRef.current = false;
                  setStreamState("error");
                }}
              />
              <canvas ref={boxesRef} className="vc-camera-boxes" aria-hidden="true" />
              {streamState === "error" && (
                <div className="vc-camera-offline" role="alert">
                  <strong>Stream tidak tersedia</strong>
                  <span>Kamera ESP32 belum mengirim gambar.</span>
                  <button type="button" className="vc-camera-secondary" onClick={switchToBrowser}>
                    Gunakan kamera perangkat
                  </button>
                </div>
              )}
              <span className="vc-camera-count" role="status" data-state={esp32State}>
                {liveDetections.length} objek terdeteksi
              </span>
            </div>
            {esp32Message && (
              <p className={`vc-camera-message ${esp32State !== "online" && !keepOriginalMessage ? "is-error" : ""}`} role="status">
                {esp32Message}
              </p>
            )}
            {liveDetections.length > 0 && (
              <ul className="vc-camera-results">
                {liveDetections.map((detection, index) => (
                  <li key={Number.isFinite(detection.id) ? `id-${detection.id}` : `${detection.object}-${detection.arah}-${index}`}>
                    <strong>{detection.level} | {labelObjek(detection)} {detection.arah}{detection.ragu ? " | KANDIDAT" : ""}</strong>
                    <span>
                      {detection.distance.toFixed(1)} m | confidence {Math.round(detection.confidence)}%
                      {labelGerak(detection) ? ` | ${labelGerak(detection)}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <div className="vc-camera-footer flex justify-end gap-2 mt-4">
              <button type="button" className="vc-camera-secondary" onClick={switchToBrowser}>
                Kamera perangkat
              </button>
              <button type="button" className="vc-camera-secondary" onClick={closePreview}>Batal</button>
              <span className="vc-camera-live-status" data-state={esp32State} role="status">
                <i className="vc-camera-live-dot" aria-hidden="true" />
                {esp32Label}
              </span>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
